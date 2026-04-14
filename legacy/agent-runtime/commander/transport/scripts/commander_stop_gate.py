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
    describe_active_subagent_blocker,
    normalize_runtime_root,
    refresh_status,
    resolve_task_paths,
    utc_now,
)
from commander.transport.scripts.commander_objective_plan import (
    list_active_objective_plan_summaries,
)
from commander.transport.scripts.commander_phase_plan import (
    list_active_phase_plan_summaries,
)
from commander.transport.scripts.commander_task_catalog import discover_task_ids


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_TASK_CARD_PATH = PROJECT_ROOT / "commander" / "state" / "当前任务卡.md"
STOP_ALLOWED_HANDOFFS = {"request_user_decision", "return_final_result"}
WAITING_HANDOFFS = {"wait_external_result"}
TERMINAL_LIFECYCLE_STATUSES = {"archived", "canceled"}
TERMINAL_PHASES = {"archived", "canceled"}


def _normalize_string(value: Any) -> str:
    return str(value or "").strip()


def _parse_task_card(task_card_path: Path) -> dict[str, Any]:
    if not task_card_path.exists():
        return {
            "path": str(task_card_path),
            "exists": False,
            "active_tasks": [],
            "claims_no_active_work": False,
        }

    content = task_card_path.read_text(encoding="utf-8")
    in_active_section = False
    current_task: dict[str, Any] | None = None
    active_tasks: list[dict[str, Any]] = []
    claims_no_active_work = False
    status_pattern = re.compile(r"-\s*当前状态：\s*`?([^`\n]+)`?")

    def flush_current_task() -> None:
        nonlocal current_task
        if current_task is not None:
            active_tasks.append(current_task)
            current_task = None

    for line in content.splitlines():
        stripped = line.strip()
        if line.startswith("## "):
            flush_current_task()
            in_active_section = stripped == "## 5. 当前活跃任务"
            continue
        if not in_active_section:
            continue
        if line.startswith("### "):
            flush_current_task()
            match = re.search(r"`([^`]+)`", line)
            title = match.group(1).strip() if match else stripped.lstrip("#").strip()
            current_task = {
                "title": title,
                "status": "",
            }
            continue
        if stripped.rstrip("。.") == "当前无活跃任务":
            claims_no_active_work = True
            continue
        if current_task is not None:
            status_match = status_pattern.match(stripped)
            if status_match:
                current_task["status"] = status_match.group(1).strip()

    flush_current_task()
    return {
        "path": str(task_card_path),
        "exists": True,
        "active_tasks": active_tasks,
        "claims_no_active_work": claims_no_active_work,
    }


def _is_runtime_task_terminal(snapshot: dict[str, Any]) -> bool:
    lifecycle_status = _normalize_string(snapshot.get("lifecycle_status"))
    current_phase = _normalize_string(snapshot.get("current_phase"))
    cleanup_eligible = bool(snapshot.get("cleanup_eligible"))
    if lifecycle_status in TERMINAL_LIFECYCLE_STATUSES:
        return True
    if current_phase in TERMINAL_PHASES:
        return True
    if lifecycle_status == "closed" or current_phase == "closed":
        return cleanup_eligible is False
    return False


def classify_runtime_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    task_id = _normalize_string(snapshot.get("task_id"))
    controller_handoff = _normalize_string(snapshot.get("controller_handoff"))
    current_phase = _normalize_string(snapshot.get("current_phase"))
    next_minimal_action = _normalize_string(snapshot.get("next_minimal_action"))
    conversation_stop_required = bool(snapshot.get("conversation_stop_required"))
    host_wait = snapshot.get("host_wait") if isinstance(snapshot.get("host_wait"), dict) else None
    active_subagents_summary = snapshot.get("active_subagents_summary")
    if not isinstance(active_subagents_summary, dict):
        active_subagents_summary = {}
    active_subagent_blocker = describe_active_subagent_blocker(active_subagents_summary)

    if active_subagent_blocker is not None:
        return {
            "task_id": task_id,
            "stop_allowed": False,
            "outcome": f"active_subagents_{active_subagent_blocker['state']}",
            "reason": active_subagent_blocker["reason"],
            "next_action": _normalize_string(active_subagent_blocker.get("next_action"))
            or "Reconcile or close active_subagents before closing the task.",
            "current_phase": current_phase,
            "controller_handoff": controller_handoff,
            "host_wait": host_wait,
            "active_subagents_summary": active_subagents_summary,
        }

    if conversation_stop_required and controller_handoff in STOP_ALLOWED_HANDOFFS:
        return {
            "task_id": task_id,
            "stop_allowed": True,
            "outcome": controller_handoff,
            "reason": _normalize_string(snapshot.get("conversation_stop_reason")) or "explicit_controller_handoff",
            "next_action": next_minimal_action,
            "current_phase": current_phase,
            "controller_handoff": controller_handoff,
            "host_wait": host_wait,
        }

    if controller_handoff in WAITING_HANDOFFS:
        return {
            "task_id": task_id,
            "stop_allowed": False,
            "outcome": "wait_external_result",
            "reason": _normalize_string(host_wait.get("wait_reason"))
            or "external_worker_result_is_pending",
            "next_action": _normalize_string(host_wait.get("next_action"))
            or next_minimal_action
            or "Wait for the worker result or reconcile worker state.",
            "current_phase": current_phase,
            "controller_handoff": controller_handoff,
            "host_wait": host_wait,
            "active_subagents_summary": active_subagents_summary,
        }

    if _is_runtime_task_terminal(snapshot):
        return {
            "task_id": task_id,
            "stop_allowed": True,
            "outcome": "runtime_task_terminal",
            "reason": "task_is_terminal_or_retained_until_cleanup",
            "next_action": next_minimal_action,
            "current_phase": current_phase,
            "controller_handoff": controller_handoff,
            "host_wait": host_wait,
            "active_subagents_summary": active_subagents_summary,
        }

    return {
        "task_id": task_id,
        "stop_allowed": False,
        "outcome": "must_continue",
        "reason": "task_requires_commander_continuation",
        "next_action": next_minimal_action or _normalize_string(snapshot.get("recommended_action")) or "Continue the commander task.",
        "current_phase": current_phase,
        "controller_handoff": controller_handoff,
        "host_wait": host_wait,
        "active_subagents_summary": active_subagents_summary,
    }


def classify_task_card(task_card: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for task in task_card.get("active_tasks", []):
        if not isinstance(task, dict):
            continue
        status = _normalize_string(task.get("status"))
        title = _normalize_string(task.get("title"))
        if status in {"pending_user", "blocked"}:
            results.append(
                {
                    "task_id": title,
                    "stop_allowed": True,
                    "outcome": status,
                    "reason": f"task_card_status_is_{status}",
                    "next_action": "Return to the user only to resolve the explicit pending state.",
                    "source": "task_card",
                }
            )
            continue
        results.append(
            {
                "task_id": title,
                "stop_allowed": False,
                "outcome": "must_continue",
                "reason": "task_card_has_active_work",
                "next_action": "Continue the active commander task or dispatch the next non-overlapping worker slice.",
                "source": "task_card",
            }
        )
    return results


def classify_phase_plan_summary(summary: dict[str, Any]) -> dict[str, Any]:
    status = _normalize_string(summary.get("status"))
    phase_id = _normalize_string(summary.get("phase_id"))
    next_action = _normalize_string(summary.get("next_action"))
    remaining_goal_count = summary.get("remaining_goal_count")
    if status in {"blocked", "pending_user"}:
        return {
            "task_id": phase_id,
            "stop_allowed": True,
            "outcome": status,
            "reason": f"phase_plan_status_is_{status}",
            "next_action": next_action or "Return to the user to resolve the phase-level blocking condition.",
            "source": "phase_plan",
            "remaining_goal_count": remaining_goal_count,
        }
    if bool(summary.get("has_remaining_goals")):
        return {
            "task_id": phase_id,
            "stop_allowed": False,
            "outcome": "phase_goals_remaining",
            "reason": "active_phase_plan_has_remaining_goals",
            "next_action": next_action or "Promote the next phase goal.",
            "source": "phase_plan",
            "remaining_goal_count": remaining_goal_count,
            "current_goal_id": summary.get("current_goal_id"),
            "promotable_goal_id": summary.get("promotable_goal_id"),
        }
    return {
        "task_id": phase_id,
        "stop_allowed": True,
        "outcome": "phase_terminal",
        "reason": "phase_plan_has_no_remaining_goals",
        "next_action": next_action,
        "source": "phase_plan",
        "remaining_goal_count": remaining_goal_count,
    }


def classify_objective_plan_summary(
    summary: dict[str, Any],
    *,
    prefer_user_handoff: bool = False,
) -> dict[str, Any]:
    objective_id = _normalize_string(summary.get("objective_id"))
    next_action = _normalize_string(summary.get("next_action"))
    remaining_phase_count = summary.get("remaining_phase_count")
    current_phase_status = _normalize_string(summary.get("current_phase_status"))
    current_phase = summary.get("current_phase") if isinstance(summary.get("current_phase"), dict) else None
    next_phase = summary.get("next_phase") if isinstance(summary.get("next_phase"), dict) else None
    if current_phase_status in {"blocked", "pending_user"}:
        return {
            "task_id": objective_id,
            "stop_allowed": True,
            "outcome": current_phase_status,
            "reason": f"objective_current_phase_status_is_{current_phase_status}",
            "next_action": next_action or "Return to the user to resolve the current phase decision gate.",
            "source": "objective_plan",
            "remaining_phase_count": remaining_phase_count,
            "current_phase": current_phase,
            "next_phase": next_phase,
        }
    if prefer_user_handoff and bool(summary.get("has_remaining_phases")):
        return {
            "task_id": objective_id,
            "stop_allowed": True,
            "outcome": "objective_waits_on_user_handoff",
            "reason": "existing_user_handoff_takes_priority_over_future_objective_phases",
            "next_action": next_action,
            "source": "objective_plan",
            "remaining_phase_count": remaining_phase_count,
            "current_phase": current_phase,
            "next_phase": next_phase,
        }
    if bool(summary.get("has_remaining_phases")):
        return {
            "task_id": objective_id,
            "stop_allowed": False,
            "outcome": "objective_phases_remaining",
            "reason": "active_objective_plan_has_remaining_phases",
            "next_action": next_action or "Promote the next objective phase.",
            "source": "objective_plan",
            "remaining_phase_count": remaining_phase_count,
            "current_phase_id": summary.get("current_phase_id"),
            "promotable_phase_id": summary.get("promotable_phase_id"),
            "current_phase": current_phase,
            "next_phase": next_phase,
        }
    return {
        "task_id": objective_id,
        "stop_allowed": True,
        "outcome": "objective_terminal",
        "reason": "objective_plan_has_no_remaining_phases",
        "next_action": next_action,
        "source": "objective_plan",
        "remaining_phase_count": remaining_phase_count,
        "current_phase": current_phase,
        "next_phase": next_phase,
    }


def build_stop_gate_report(
    runtime_root: str | Path | None = None,
    *,
    task_id: str | None = None,
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
    runtime_results: list[dict[str, Any]] = []
    phase_plan_results = [
        classify_phase_plan_summary(summary)
        for summary in list_active_phase_plan_summaries(resolved_runtime_root)
    ]

    if task_id:
        snapshot = refresh_status(resolve_task_paths(resolved_runtime_root, task_id))
        runtime_results.append(classify_runtime_snapshot(snapshot))
    else:
        for discovered_task_id in discover_task_ids(resolved_runtime_root):
            snapshot = refresh_status(resolve_task_paths(resolved_runtime_root, discovered_task_id))
            result = classify_runtime_snapshot(snapshot)
            if result["stop_allowed"] is False or result["outcome"] in STOP_ALLOWED_HANDOFFS:
                runtime_results.append(result)

    task_card_results = classify_task_card(task_card)
    preexisting_user_gates = [
        item
        for item in [*runtime_results, *task_card_results, *phase_plan_results]
        if item["stop_allowed"] is True
        and item["outcome"]
        in {"request_user_decision", "return_final_result", "pending_user", "blocked"}
    ]
    objective_plan_results = [
        classify_objective_plan_summary(
            summary,
            prefer_user_handoff=bool(preexisting_user_gates),
        )
        for summary in list_active_objective_plan_summaries(resolved_runtime_root)
    ]
    role_guard_result = (
        {
            "task_id": "commander-role-guard",
            "stop_allowed": False,
            "outcome": "commander_write_violation",
            "reason": "commander_local_changes_escape_allowed_doc_surfaces",
            "next_action": "Delegate business-code changes to a worker sub-agent or reconcile/revert the commander-local diff before stopping.",
            "source": "role_guard",
            "violation_paths": role_guard["violation_paths"],
        }
        if role_guard["enabled"] and role_guard["violation_count"]
        else None
    )
    blockers = [
        item
        for item in [
            *runtime_results,
            *task_card_results,
            *phase_plan_results,
            *objective_plan_results,
            *([role_guard_result] if role_guard_result is not None else []),
        ]
        if item["stop_allowed"] is False
    ]
    user_gates = [
        item
        for item in [
            *runtime_results,
            *task_card_results,
            *phase_plan_results,
            *objective_plan_results,
        ]
        if item["stop_allowed"] is True
        and item["outcome"]
        in {"request_user_decision", "return_final_result", "pending_user", "blocked"}
    ]
    has_active_task_card = bool(task_card_results)
    has_runtime_interest = bool(runtime_results)
    has_phase_interest = bool(phase_plan_results)
    has_objective_interest = bool(objective_plan_results)

    if blockers:
        stop_allowed = False
        outcome = "must_continue"
        reason = "active_work_requires_continuation"
        next_actions = [item["next_action"] for item in blockers if item.get("next_action")]
    elif user_gates:
        stop_allowed = True
        outcome = "user_handoff_allowed"
        reason = "explicit_user_or_final_handoff"
        next_actions = [item["next_action"] for item in user_gates if item.get("next_action")]
    elif (
        not has_active_task_card
        and not has_runtime_interest
        and not has_phase_interest
        and not has_objective_interest
    ):
        stop_allowed = True
        outcome = "no_active_work"
        reason = "no_active_task_card_or_runtime_work"
        next_actions = []
    else:
        stop_allowed = True
        outcome = "all_tracked_work_terminal"
        reason = "tracked_runtime_work_is_terminal"
        next_actions = []

    if blockers:
        blocker_outcomes = {str(item.get("outcome") or "").strip() for item in blockers}
        if "wait_external_result" in blocker_outcomes and blocker_outcomes.issubset(
            {
                "wait_external_result",
                "must_continue",
                "phase_goals_remaining",
                "objective_phases_remaining",
            }
        ):
            continuation_mode = "wait_external_result"
        else:
            continuation_mode = "commander_internal"
    elif user_gates:
        continuation_mode = "user_handoff"
    else:
        continuation_mode = "terminal"

    return {
        "schema_version": "commander-stop-gate-v1",
        "generated_at": utc_now(),
        "runtime_root": str(resolved_runtime_root),
        "task_id": task_id,
        "task_card": task_card,
        "role_guard": role_guard,
        "stop_allowed": stop_allowed,
        "continuation_required": not stop_allowed,
        "continuation_mode": continuation_mode,
        "outcome": outcome,
        "reason": reason,
        "next_actions": next_actions,
        "role_guard_result": role_guard_result,
        "runtime_results": runtime_results,
        "task_card_results": task_card_results,
        "phase_plan_results": phase_plan_results,
        "objective_plan_results": objective_plan_results,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Decide whether the commander may stop at the user layer.")
    parser.add_argument("--runtime-root", default=None, help="Override runtime root. Defaults to .runtime/commander")
    parser.add_argument("--task-id", default=None, help="Optionally inspect one runtime task")
    parser.add_argument("--task-card-path", default=str(DEFAULT_TASK_CARD_PATH), help="Override current task card path")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_stop_gate_report(
        args.runtime_root,
        task_id=args.task_id,
        task_card_path=args.task_card_path,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["stop_allowed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
