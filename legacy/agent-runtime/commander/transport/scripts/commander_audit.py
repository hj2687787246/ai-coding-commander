from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from commander.graph.policies import (
    build_commander_role_guard_report,
    collect_repo_status_paths,
)
from commander.transport.scripts.commander_harness import (
    DEFAULT_RUNTIME_ROOT,
    normalize_runtime_root,
    reconcile_worker_slots,
    refresh_status,
    resolve_task_paths,
    utc_now,
)
from commander.transport.scripts.commander_task_catalog import discover_task_ids, load_task_catalog


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_TASK_CARD_PATH = PROJECT_ROOT / "commander" / "state" / "当前任务卡.md"
WORKER_DRIFT_HEALTH_STATES = {"lease_expired", "multiple_leased_workers", "released_binding_drift", "closed_binding_drift"}
ATTENTION_GRADE_NEEDS_USER = "needs_user"
ATTENTION_GRADE_NEEDS_COMMANDER = "needs_commander"
ATTENTION_GRADE_PRIORITY = {
    ATTENTION_GRADE_NEEDS_USER: 0,
    ATTENTION_GRADE_NEEDS_COMMANDER: 1,
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit commander doc/runtime/catalog drift and lifecycle hygiene.")
    parser.add_argument("--runtime-root", default=None, help="Override runtime root. Defaults to .runtime/commander")
    parser.add_argument("--task-card-path", default=str(DEFAULT_TASK_CARD_PATH), help="Override current task card path")
    return parser.parse_args(argv)


def _parse_task_card(task_card_path: Path) -> dict[str, Any]:
    if not task_card_path.exists():
        return {
            "path": str(task_card_path),
            "exists": False,
            "active_titles": [],
            "claims_no_active_work": False,
        }

    content = task_card_path.read_text(encoding="utf-8")
    in_active_section = False
    active_titles: list[str] = []
    claims_no_active_work = False
    for line in content.splitlines():
        if line.startswith("## "):
            in_active_section = line.strip() == "## 5. 当前活跃任务"
            continue
        if in_active_section and line.startswith("### "):
            match = re.search(r"`([^`]+)`", line)
            if match:
                active_titles.append(match.group(1).strip())
            continue
        if in_active_section and line.strip().rstrip("。.") == "当前无活跃任务":
            claims_no_active_work = True

    return {
        "path": str(task_card_path),
        "exists": True,
        "active_titles": active_titles,
        "claims_no_active_work": claims_no_active_work,
    }


def _build_attention_entry(
    snapshot: dict[str, Any],
    *,
    attention_kind: str,
    action_owner: str,
    reason: str,
) -> dict[str, Any]:
    worker_binding = snapshot.get("worker_binding") if isinstance(snapshot.get("worker_binding"), dict) else {}
    improvement_candidate = snapshot.get("improvement_candidate") if isinstance(snapshot.get("improvement_candidate"), dict) else {}
    catalog_refresh = snapshot.get("catalog_refresh") if isinstance(snapshot.get("catalog_refresh"), dict) else {}
    return {
        "task_id": snapshot.get("task_id"),
        "title": snapshot.get("title"),
        "current_phase": snapshot.get("current_phase"),
        "lifecycle_status": snapshot.get("lifecycle_status"),
        "controller_handoff": snapshot.get("controller_handoff"),
        "recommended_action": snapshot.get("recommended_action"),
        "next_minimal_action": snapshot.get("next_minimal_action"),
        "attention_kind": attention_kind,
        "attention_reason": reason,
        "action_owner": action_owner,
        "attention_grade": ATTENTION_GRADE_NEEDS_USER if action_owner == "user" else ATTENTION_GRADE_NEEDS_COMMANDER,
        "worker_binding_health": worker_binding.get("binding_health"),
        "improvement_candidate_status": improvement_candidate.get("status"),
        "catalog_refresh_status": catalog_refresh.get("status"),
        "updated_at": snapshot.get("updated_at"),
    }


def build_audit_report(
    runtime_root: str | Path | None = None,
    *,
    task_card_path: str | Path | None = None,
    repo_status_paths: list[str] | None = None,
    enforce_role_guard: bool | None = None,
) -> dict[str, Any]:
    resolved_runtime_root = normalize_runtime_root(runtime_root)
    resolved_task_card_path = Path(task_card_path).resolve() if task_card_path is not None else DEFAULT_TASK_CARD_PATH
    role_guard_enabled = (
        bool(enforce_role_guard)
        if enforce_role_guard is not None
        else resolved_runtime_root == DEFAULT_RUNTIME_ROOT
    )
    role_guard = build_commander_role_guard_report(
        repo_status_paths
        if repo_status_paths is not None
        else (
            collect_repo_status_paths(PROJECT_ROOT) if role_guard_enabled else []
        ),
        enabled=role_guard_enabled,
    )
    task_card = _parse_task_card(resolved_task_card_path)
    task_ids = discover_task_ids(resolved_runtime_root)

    runtime_tasks = []
    for task_id in task_ids:
        runtime_tasks.append(refresh_status(resolve_task_paths(resolved_runtime_root, task_id)))
    worker_reconcile = reconcile_worker_slots(resolved_runtime_root, dry_run=True)

    catalog = load_task_catalog(resolved_runtime_root)
    catalog_by_task_id = {entry["task_id"]: entry for entry in catalog["tasks"]}
    warnings: list[dict[str, Any]] = []
    attention_views: dict[str, list[dict[str, Any]]] = {
        "pending_close": [],
        "stale": [],
        "pending_candidate_review": [],
        "worker_drift": [],
        "catalog_refresh_failed": [],
        "catalog_drift": [],
        "pending_user": [],
    }
    recovery_queue_by_task_id: dict[str, dict[str, Any]] = {}

    def register_attention(snapshot: dict[str, Any], *, attention_kind: str, action_owner: str, reason: str) -> None:
        entry = _build_attention_entry(
            snapshot,
            attention_kind=attention_kind,
            action_owner=action_owner,
            reason=reason,
        )
        attention_views[attention_kind].append(entry)
        task_id = str(entry["task_id"])
        existing = recovery_queue_by_task_id.get(task_id)
        if existing is None:
            entry["attention_kinds"] = [attention_kind]
            recovery_queue_by_task_id[task_id] = entry
            return

        merged_kinds = sorted({*existing.get("attention_kinds", []), attention_kind})
        existing["attention_kinds"] = merged_kinds
        new_priority = ATTENTION_GRADE_PRIORITY[entry["attention_grade"]]
        existing_priority = ATTENTION_GRADE_PRIORITY[existing["attention_grade"]]
        if new_priority < existing_priority:
            entry["attention_kinds"] = merged_kinds
            recovery_queue_by_task_id[task_id] = entry

    active_runtime_tasks = [item for item in runtime_tasks if item.get("lifecycle_status") in {"active", "stale", "closed"}]
    attention_runtime_tasks = [
        item["task_id"]
        for item in runtime_tasks
        if item.get("current_phase") in {"ready_to_close", "closed", "stale"}
    ]
    worker_binding_attention_tasks = [
        item["task_id"]
        for item in runtime_tasks
        if item.get("worker_binding", {}).get("binding_health")
        in WORKER_DRIFT_HEALTH_STATES
    ]
    catalog_refresh_failed_tasks = [
        {
            "task_id": item["task_id"],
            "reason": item.get("catalog_refresh", {}).get("reason"),
            "error_type": item.get("catalog_refresh", {}).get("error_type"),
            "error_message": item.get("catalog_refresh", {}).get("error_message"),
        }
        for item in runtime_tasks
        if item.get("catalog_refresh", {}).get("status") == "failed"
    ]

    if task_card["claims_no_active_work"] and active_runtime_tasks:
        warnings.append(
            {
                "kind": "task_card_runtime_drift",
                "message": "Task card claims there is no active work, but runtime still has live tasks.",
                "runtime_task_ids": [item["task_id"] for item in active_runtime_tasks],
            }
        )

    if len(task_card["active_titles"]) > 3:
        warnings.append(
            {
                "kind": "task_card_over_capacity",
                "message": "Current task card lists more than 3 active items.",
                "active_titles": task_card["active_titles"],
            }
        )

    for snapshot in runtime_tasks:
        task_id = snapshot["task_id"]
        current_phase = snapshot.get("current_phase")
        lifecycle_status = snapshot.get("lifecycle_status")
        worker_binding_health = snapshot.get("worker_binding", {}).get("binding_health")
        improvement_candidate = snapshot.get("improvement_candidate")
        if not isinstance(improvement_candidate, dict):
            improvement_candidate = {}
        catalog_refresh = snapshot.get("catalog_refresh")
        if not isinstance(catalog_refresh, dict):
            catalog_refresh = {}
        improvement_candidate_status = improvement_candidate.get("status")
        catalog_refresh_status = catalog_refresh.get("status")

        if current_phase in {"ready_to_close", "closed"}:
            register_attention(
                snapshot,
                attention_kind="pending_close",
                action_owner="commander",
                reason=f"Task is currently in phase={current_phase!r} and needs commander close/archive follow-up.",
            )
        if lifecycle_status == "stale" or current_phase == "stale":
            register_attention(
                snapshot,
                attention_kind="stale",
                action_owner="commander",
                reason="Task is stale and should be reconciled before continuing new work.",
            )
        if improvement_candidate_status == "candidate":
            register_attention(
                snapshot,
                attention_kind="pending_candidate_review",
                action_owner="commander",
                reason="Improvement candidate is still awaiting commander review.",
            )
        if worker_binding_health in WORKER_DRIFT_HEALTH_STATES:
            register_attention(
                snapshot,
                attention_kind="worker_drift",
                action_owner="commander",
                reason=f"Task exposes worker binding drift: {worker_binding_health}.",
            )
        active_subagents_summary = snapshot.get("active_subagents_summary")
        if isinstance(active_subagents_summary, dict) and active_subagents_summary.get("has_open_subagents"):
            open_count = int(active_subagents_summary.get("open_count") or 0)
            running_count = int(active_subagents_summary.get("running_count") or 0)
            blocked_count = int(active_subagents_summary.get("blocked_count") or 0)
            waiting_close_count = int(active_subagents_summary.get("completed_waiting_close_count") or 0)
            if running_count:
                warnings.append(
                    {
                        "kind": "active_subagents_running",
                        "task_id": task_id,
                        "message": "Task still has running sub-agents and cannot be treated as closed work.",
                        "reason": "active_subagents_are_still_running",
                        "next_action": "Wait for running sub-agents to finish or reassign them before closing the task.",
                        "count": running_count,
                        "open_count": open_count,
                    }
                )
            if blocked_count:
                warnings.append(
                    {
                        "kind": "active_subagents_blocked",
                        "task_id": task_id,
                        "message": "Task still has blocked sub-agents and cannot be treated as closed work.",
                        "reason": "active_subagents_are_blocked",
                        "next_action": "Unblock or close blocked sub-agents before closing the task.",
                        "count": blocked_count,
                        "open_count": open_count,
                    }
                )
            if waiting_close_count:
                warnings.append(
                    {
                        "kind": "active_subagents_completed_waiting_close",
                        "task_id": task_id,
                        "message": "Task still has completed sub-agents waiting for close and result recovery.",
                        "reason": "active_subagents_have_completed_results_pending_close",
                        "next_action": "Recover the completed results and close the sub-agents before closing the task.",
                        "count": waiting_close_count,
                        "open_count": open_count,
                    }
                )
        if current_phase == "pending_user" or snapshot.get("needs_user_decision"):
            register_attention(
                snapshot,
                attention_kind="pending_user",
                action_owner="user",
                reason="Task is waiting on an explicit user decision before it can continue.",
            )
        if catalog_refresh_status == "failed":
            register_attention(
                snapshot,
                attention_kind="catalog_refresh_failed",
                action_owner="commander",
                reason="DB-backed commander task catalog refresh failed for this task snapshot.",
            )

        catalog_entry = catalog_by_task_id.get(task_id)
        if catalog_entry is None:
            warnings.append(
                {
                    "kind": "runtime_catalog_missing_entry",
                    "task_id": task_id,
                    "message": "Runtime task exists but catalog entry is missing.",
                }
            )
            register_attention(
                snapshot,
                attention_kind="catalog_drift",
                action_owner="commander",
                reason="Runtime task exists but catalog entry is missing.",
            )
            continue
        expected_status = snapshot.get("lifecycle_status")
        if expected_status not in {"closed", "archived", "stale", "canceled"}:
            expected_status = snapshot.get("worker_status") or snapshot.get("current_phase")
        runtime_values = {
            "status": expected_status,
            "current_phase": snapshot.get("current_phase"),
            "controller_handoff": snapshot.get("controller_handoff"),
            "lifecycle_status": snapshot.get("lifecycle_status"),
            "catalog_refresh_status": snapshot.get("catalog_refresh", {}).get("status"),
        }
        drift_fields: list[str] = []
        for field, runtime_value in runtime_values.items():
            catalog_value = catalog_entry.get(field)
            if runtime_value != catalog_value:
                drift_fields.append(field)
                warnings.append(
                    {
                        "kind": "runtime_catalog_mismatch",
                        "task_id": task_id,
                        "field": field,
                        "runtime_value": runtime_value,
                        "catalog_value": catalog_value,
                    }
                )
        if drift_fields:
            register_attention(
                snapshot,
                attention_kind="catalog_drift",
                action_owner="commander",
                reason=f"Catalog projection differs from runtime for fields: {', '.join(sorted(drift_fields))}.",
            )

    if worker_reconcile["stale_worker_ids"]:
        warnings.append(
            {
                "kind": "worker_pool_stale_leases",
                "message": "Worker pool has expired leased workers that should be reconciled.",
                "worker_ids": worker_reconcile["stale_worker_ids"],
            }
        )

    if worker_reconcile["orphan_task_ids"]:
        warnings.append(
            {
                "kind": "worker_pool_orphan_tasks",
                "message": "Tasks still expect worker progress, but their worker lease has expired.",
                "task_ids": worker_reconcile["orphan_task_ids"],
            }
        )

    if worker_reconcile.get("duplicate_binding_task_ids"):
        warnings.append(
            {
                "kind": "worker_pool_duplicate_bindings",
                "message": "One or more tasks still have multiple leased workers bound at the same time.",
                "task_ids": worker_reconcile["duplicate_binding_task_ids"],
            }
        )

    if worker_binding_attention_tasks:
        warnings.append(
            {
                "kind": "task_worker_binding_drift",
                "message": "One or more tasks expose worker binding drift in status/checkpoint projections.",
                "task_ids": worker_binding_attention_tasks,
            }
        )

    if catalog_refresh_failed_tasks:
        warnings.append(
            {
                "kind": "catalog_refresh_failed",
                "message": "One or more tasks failed to refresh the DB-backed commander task catalog.",
                "tasks": catalog_refresh_failed_tasks,
            }
        )
    if role_guard["violation_count"]:
        warnings.append(
            {
                "kind": "commander_write_violation",
                "message": "Commander-local repo changes escaped the allowed commander doc surfaces; code writes must be delegated to a worker sub-agent or reconciled.",
                "paths": role_guard["violation_paths"],
            }
        )

    for items in attention_views.values():
        items.sort(key=lambda item: (str(item.get("updated_at", "")), str(item.get("task_id", ""))), reverse=True)
    recovery_queue = sorted(
        recovery_queue_by_task_id.values(),
        key=lambda item: (
            ATTENTION_GRADE_PRIORITY[item["attention_grade"]],
            str(item.get("task_id", "")),
        ),
    )

    return {
        "generated_at": utc_now(),
        "runtime_root": str(resolved_runtime_root),
        "task_card": task_card,
        "runtime_task_count": len(runtime_tasks),
        "runtime_attention_task_ids": attention_runtime_tasks,
        "runtime_worker_attention_worker_ids": worker_reconcile["stale_worker_ids"],
        "runtime_orphan_task_ids": worker_reconcile["orphan_task_ids"],
        "runtime_duplicate_binding_task_ids": worker_reconcile.get("duplicate_binding_task_ids", []),
        "runtime_worker_binding_attention_task_ids": worker_binding_attention_tasks,
        "runtime_catalog_refresh_failed_task_ids": [item["task_id"] for item in catalog_refresh_failed_tasks],
        "catalog_task_count": catalog["task_count"],
        "role_guard": role_guard,
        "attention_views": attention_views,
        "recovery_queue_count": len(recovery_queue),
        "recovery_queue": recovery_queue,
        "warning_count": len(warnings),
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = build_audit_report(args.runtime_root, task_card_path=args.task_card_path)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
