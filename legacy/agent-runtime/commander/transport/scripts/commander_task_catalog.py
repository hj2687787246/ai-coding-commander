from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from commander.transport.scripts.commander_harness import (
    build_catalog_refresh_summary,
    load_json,
    normalize_runtime_root,
    resolve_task_paths,
    utc_now,
)


CATALOG_SCHEMA_VERSION = "commander-task-catalog-v1"
_TASK_SOURCE_FILENAMES = (
    "packet.json",
    "worker_report.json",
    "report.json",
    "lifecycle.json",
    "status.json",
    "checkpoint.json",
    "events.jsonl",
    "worker_brief.md",
)
_ACTIVE_LIKE_STATUSES = {"active", "awaiting_report", "ready_to_close", "needs_commander_decision", "pending_user", "stale"}
_ACTIVE_LIKE_PHASES = {"awaiting_report", "ready_to_close", "needs_commander_decision", "pending_user", "stale"}
_TERMINAL_LIFECYCLE_STATUSES = {"closed", "archived", "canceled"}


def _normalize_string(value: Any) -> str:
    return str(value or "").strip()


def _first_non_empty_string(*values: Any) -> str:
    for value in values:
        normalized = _normalize_string(value)
        if normalized:
            return normalized
    return ""


def _first_non_empty_optional_string(*values: Any) -> str | None:
    resolved = _first_non_empty_string(*values)
    return resolved or None


def _normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized_items: list[str] = []
    for item in value:
        normalized_item = _normalize_string(item)
        if normalized_item:
            normalized_items.append(normalized_item)
    return normalized_items


def _coerce_bool(*values: Any) -> bool:
    for value in values:
        if value is not None:
            return bool(value)
    return False


def _load_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = load_json(path)
    return payload if isinstance(payload, dict) else {}


def _load_event_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "event_count": 0,
            "last_event_type": "",
            "last_event_at": "",
        }

    event_count = 0
    last_event_type = ""
    last_event_at = ""
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            event_count += 1
            event = json.loads(line)
            if isinstance(event, dict):
                last_event_type = _first_non_empty_string(event.get("event_type")) or last_event_type
                last_event_at = _first_non_empty_string(event.get("timestamp")) or last_event_at

    return {
        "event_count": event_count,
        "last_event_type": last_event_type,
        "last_event_at": last_event_at,
    }


def _has_task_artifacts(task_dir: Path) -> bool:
    for filename in _TASK_SOURCE_FILENAMES:
        if (task_dir / filename).exists():
            return True
    return False


def _is_active_like_task(entry: dict[str, Any]) -> bool:
    lifecycle_status = _normalize_string(entry.get("lifecycle_status"))
    if lifecycle_status in _TERMINAL_LIFECYCLE_STATUSES:
        return False
    status = _normalize_string(entry.get("status"))
    current_phase = _normalize_string(entry.get("current_phase"))
    return status in _ACTIVE_LIKE_STATUSES or current_phase in _ACTIVE_LIKE_PHASES


def discover_task_ids(runtime_root: Path) -> list[str]:
    tasks_root = runtime_root / "tasks"
    if not tasks_root.exists():
        return []
    task_ids: list[str] = []
    for task_dir in sorted(path for path in tasks_root.iterdir() if path.is_dir()):
        if _has_task_artifacts(task_dir):
            task_ids.append(task_dir.name)
    return task_ids


def build_task_catalog_entry(runtime_root: Path, task_id: str) -> dict[str, Any]:
    paths = resolve_task_paths(runtime_root, task_id)
    packet = _load_json_file(paths.packet_path)
    worker_report = _load_json_file(paths.worker_report_path)
    report = _load_json_file(paths.report_path)
    lifecycle = _load_json_file(paths.lifecycle_path)
    status = _load_json_file(paths.status_path)
    checkpoint = _load_json_file(paths.checkpoint_path)
    event_summary = _load_event_summary(paths.events_path)
    catalog_refresh = build_catalog_refresh_summary(paths)
    status_catalog_refresh = status.get("catalog_refresh") if isinstance(status.get("catalog_refresh"), dict) else {}

    resolved_task_id = _first_non_empty_string(
        packet.get("task_id"),
        status.get("task_id"),
        checkpoint.get("task_id"),
        lifecycle.get("task_id"),
        report.get("task_id"),
        worker_report.get("task_id"),
        task_id,
    )
    controller_handoff = _first_non_empty_string(status.get("controller_handoff"), checkpoint.get("controller_handoff"))
    worker_status = _first_non_empty_string(status.get("worker_status"), checkpoint.get("worker_status"), report.get("status"))
    lifecycle_status = _first_non_empty_string(
        status.get("lifecycle_status"),
        checkpoint.get("lifecycle_status"),
        lifecycle.get("lifecycle_status"),
        "active" if packet else "",
    )
    if lifecycle_status in {"closed", "archived", "stale", "canceled"}:
        status_value = lifecycle_status
    else:
        status_value = _first_non_empty_string(
            worker_status,
            report.get("status"),
            checkpoint.get("current_phase"),
            status.get("status"),
            packet.get("status"),
        )
    updated_at = _first_non_empty_string(
        status.get("updated_at"),
        checkpoint.get("updated_at"),
        lifecycle.get("updated_at"),
        packet.get("updated_at"),
        report.get("updated_at"),
        event_summary.get("last_event_at"),
        utc_now(),
    )

    return {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "task_id": resolved_task_id,
        "title": _first_non_empty_string(status.get("title"), checkpoint.get("title"), packet.get("title")),
        "goal": _first_non_empty_string(packet.get("goal")),
        "status": status_value,
        "current_phase": _first_non_empty_string(status.get("current_phase"), checkpoint.get("current_phase")),
        "worker_profile": _first_non_empty_string(
            status.get("worker_profile"),
            checkpoint.get("worker_profile"),
            packet.get("worker_profile"),
        ),
        "preferred_worker_profile": _first_non_empty_optional_string(
            status.get("preferred_worker_profile"),
            checkpoint.get("preferred_worker_profile"),
            packet.get("preferred_worker_profile"),
        ),
        "tool_profile": _first_non_empty_string(status.get("tool_profile"), checkpoint.get("tool_profile"), packet.get("tool_profile")),
        "allowed_tools": _normalize_string_list(
            status.get("allowed_tools") or checkpoint.get("allowed_tools") or packet.get("allowed_tools")
        ),
        "dispatch_kind": _first_non_empty_string(
            status.get("dispatch_kind"),
            checkpoint.get("dispatch_kind"),
            packet.get("dispatch_kind"),
        ),
        "source_task_id": _first_non_empty_optional_string(
            status.get("source_task_id"),
            checkpoint.get("source_task_id"),
            packet.get("source_task_id"),
        ),
        "parent_task_id": _first_non_empty_optional_string(
            status.get("parent_task_id"),
            checkpoint.get("parent_task_id"),
            packet.get("parent_task_id"),
        ),
        "task_owner": _first_non_empty_string(
            status.get("task_owner"),
            checkpoint.get("task_owner"),
            packet.get("task_owner"),
        ),
        "closure_policy": _first_non_empty_string(
            status.get("closure_policy"),
            checkpoint.get("closure_policy"),
            packet.get("closure_policy"),
        ),
        "result_grade": _first_non_empty_string(
            status.get("result_grade"),
            checkpoint.get("result_grade"),
            report.get("result_grade"),
        ),
        "next_action_owner": _first_non_empty_string(
            status.get("next_action_owner"),
            checkpoint.get("next_action_owner"),
            report.get("next_action_owner"),
        ),
        "continuation_mode": _first_non_empty_string(
            status.get("continuation_mode"),
            checkpoint.get("continuation_mode"),
            report.get("continuation_mode"),
        ),
        "decision_reason": _first_non_empty_optional_string(
            status.get("decision_reason"),
            checkpoint.get("decision_reason"),
            report.get("decision_reason"),
            report.get("user_decision_reason"),
        ),
        "controller_handoff": controller_handoff,
        "commander_recommendation": _first_non_empty_string(
            status.get("commander_recommendation"),
            checkpoint.get("commander_recommendation"),
        ),
        "recommended_action": _first_non_empty_string(status.get("recommended_action"), checkpoint.get("recommended_action")),
        "next_minimal_action": _first_non_empty_string(status.get("next_minimal_action"), checkpoint.get("next_minimal_action")),
        "lifecycle_status": lifecycle_status,
        "cleanup_eligible": _coerce_bool(
            status.get("cleanup_eligible"),
            checkpoint.get("cleanup_eligible"),
            lifecycle.get("cleanup_eligible"),
        ),
        "catalog_refresh_status": _first_non_empty_string(catalog_refresh.get("status"), status_catalog_refresh.get("status")),
        "catalog_refresh_reason": _first_non_empty_optional_string(
            catalog_refresh.get("reason"),
            status_catalog_refresh.get("reason"),
        ),
        "catalog_refresh_event_type": _first_non_empty_optional_string(
            catalog_refresh.get("event_type"),
            status_catalog_refresh.get("event_type"),
        ),
        "catalog_refresh_attempted_at": _first_non_empty_optional_string(
            catalog_refresh.get("attempted_at"),
            status_catalog_refresh.get("attempted_at"),
        ),
        "catalog_refresh_last_success_at": _first_non_empty_optional_string(
            catalog_refresh.get("last_success_at"),
            status_catalog_refresh.get("last_success_at"),
        ),
        "catalog_refresh_last_success_event_type": _first_non_empty_optional_string(
            catalog_refresh.get("last_success_event_type"),
            status_catalog_refresh.get("last_success_event_type"),
        ),
        "catalog_refresh_failure_count": int(catalog_refresh.get("failure_count") or 0),
        "catalog_refresh_error_type": _first_non_empty_optional_string(
            catalog_refresh.get("error_type"),
            status_catalog_refresh.get("error_type"),
        ),
        "catalog_refresh_error_message": _first_non_empty_optional_string(
            catalog_refresh.get("error_message"),
            status_catalog_refresh.get("error_message"),
        ),
        "closed_at": _first_non_empty_optional_string(
            status.get("closed_at"),
            checkpoint.get("closed_at"),
            lifecycle.get("closed_at"),
        ),
        "archived_at": _first_non_empty_optional_string(
            status.get("archived_at"),
            checkpoint.get("archived_at"),
            lifecycle.get("archived_at"),
        ),
        "stale_at": _first_non_empty_optional_string(
            status.get("stale_at"),
            checkpoint.get("stale_at"),
            lifecycle.get("stale_at"),
        ),
        "worker_status": worker_status,
        "needs_commander_decision": _coerce_bool(
            status.get("needs_commander_decision"),
            checkpoint.get("needs_commander_decision"),
            report.get("needs_commander_decision"),
        ),
        "needs_user_decision": _coerce_bool(
            status.get("needs_user_decision"),
            checkpoint.get("needs_user_decision"),
            report.get("needs_user_decision"),
        ),
        "ready_for_user_delivery": _coerce_bool(
            status.get("ready_for_user_delivery"),
            checkpoint.get("ready_for_user_delivery"),
            report.get("ready_for_user_delivery"),
        ),
        "has_packet": paths.packet_path.exists(),
        "has_report": paths.report_path.exists(),
        "event_count": int(status.get("event_count") or event_summary["event_count"] or 0),
        "last_event_type": _first_non_empty_string(status.get("last_event_type"), event_summary.get("last_event_type")),
        "last_event_at": _first_non_empty_string(status.get("last_event_at"), event_summary.get("last_event_at")),
        "updated_at": updated_at,
    }


def load_task_catalog(runtime_root: str | Path | None = None, *, task_id: str | None = None) -> dict[str, Any]:
    normalized_runtime_root = normalize_runtime_root(runtime_root)
    if task_id:
        tasks = [build_task_catalog_entry(normalized_runtime_root, task_id)]
    else:
        tasks = [build_task_catalog_entry(normalized_runtime_root, item) for item in discover_task_ids(normalized_runtime_root)]

    tasks = sorted(
        tasks,
        key=lambda item: (str(item.get("updated_at", "")), str(item.get("task_id", ""))),
        reverse=True,
    )
    return {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "generated_at": utc_now(),
        "runtime_root": str(normalized_runtime_root),
        "task_count": len(tasks),
        "tasks": tasks,
    }


def build_task_catalog_summary(
    runtime_root: str | Path | None = None,
    *,
    task_id: str | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    catalog = load_task_catalog(runtime_root, task_id=task_id)
    tasks = catalog["tasks"]
    limit = max(int(limit), 1)
    prioritized_tasks = sorted(
        tasks,
        key=lambda item: (
            _is_active_like_task(item),
            str(item.get("updated_at") or ""),
            str(item.get("task_id") or ""),
        ),
        reverse=True,
    )
    summary_tasks: list[dict[str, Any]] = []
    for item in prioritized_tasks[:limit]:
        summary_tasks.append(
            {
                "task_id": item.get("task_id"),
                "title": item.get("title"),
                "status": item.get("status"),
                "current_phase": item.get("current_phase"),
                "lifecycle_status": item.get("lifecycle_status"),
                "controller_handoff": item.get("controller_handoff"),
                "recommended_action": item.get("recommended_action"),
                "next_minimal_action": item.get("next_minimal_action"),
                "result_grade": item.get("result_grade"),
                "worker_profile": item.get("worker_profile"),
                "task_owner": item.get("task_owner"),
                "updated_at": item.get("updated_at"),
            }
        )
    active_count = sum(1 for item in tasks if _is_active_like_task(item))
    return {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "generated_at": catalog["generated_at"],
        "runtime_root": catalog["runtime_root"],
        "task_count": catalog["task_count"],
        "active_like_task_count": active_count,
        "tasks": summary_tasks,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a read-only commander task catalog from task snapshots.")
    parser.add_argument("--runtime-root", default=None, help="Override runtime root. Defaults to .runtime/commander")
    parser.add_argument("--task-id", default=None, help="Return a single task catalog entry")
    parser.add_argument("--summary", action="store_true", help="Return a compact overview instead of full task entries.")
    parser.add_argument("--limit", type=int, default=5, help="When --summary is used, limit the number of task entries.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.summary:
        catalog = build_task_catalog_summary(args.runtime_root, task_id=args.task_id, limit=args.limit)
    else:
        catalog = load_task_catalog(args.runtime_root, task_id=args.task_id)
    print(json.dumps(catalog, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
