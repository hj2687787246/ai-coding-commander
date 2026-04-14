from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from commander.transport.scripts.commander_harness import (
    PACKET_SCHEMA_PATH,
    SchemaValidationError,
    load_json,
    load_schema,
    normalize_runtime_root,
    refresh_status,
    resolve_task_paths,
    utc_now,
    validate_instance,
    write_json,
)
from commander.transport.scripts.commander_dispatch import dispatch_task
from commander.transport.scripts.commander_spec_kit import (
    merge_spec_refs,
    normalize_spec_refs,
)


COMMANDER_ROOT = Path(__file__).resolve().parents[2]
PHASE_PLAN_SCHEMA_PATH = (
    COMMANDER_ROOT / "transport" / "schemas" / "commander_phase_plan.schema.json"
)
PHASE_STATUS_ACTIVE = "active"
PHASE_STATUS_BLOCKED = "blocked"
PHASE_STATUS_PENDING_USER = "pending_user"
PHASE_STATUS_COMPLETED = "completed"
PHASE_STATUS_ARCHIVED = "archived"
GOAL_STATUS_PENDING = "pending"
GOAL_STATUS_ACTIVE = "active"
GOAL_STATUS_DONE = "done"
GOAL_STATUS_BLOCKED = "blocked"
GOAL_STATUS_CANCELED = "canceled"
TERMINAL_TASK_LIFECYCLE = {"closed", "archived", "canceled"}


def resolve_phase_plan_dir(runtime_root: Path) -> Path:
    return runtime_root / "phases"


def resolve_phase_plan_path(runtime_root: Path, phase_id: str) -> Path:
    return resolve_phase_plan_dir(runtime_root) / f"{phase_id}.json"


def _goal_ids(goals: list[dict[str, Any]]) -> set[str]:
    return {
        goal["goal_id"]
        for goal in goals
        if isinstance(goal, dict) and isinstance(goal.get("goal_id"), str)
    }


def _load_phase_plan_schema() -> dict[str, Any]:
    return load_schema(PHASE_PLAN_SCHEMA_PATH)


def _packet_template_schema() -> dict[str, Any]:
    packet_schema = load_schema(PACKET_SCHEMA_PATH)
    properties = dict(packet_schema["properties"])
    required = [
        "must_read",
        "bounds",
        "validation",
        "forbidden_paths",
        "worker_profile",
        "tool_profile",
        "allowed_tools",
        "reuse_allowed",
        "dispatch_kind",
        "source_task_id",
        "parent_task_id",
        "task_owner",
        "closure_policy",
        "report_contract",
    ]
    return {
        "type": "object",
        "additionalProperties": False,
        "required": required,
        "properties": {
            key: value
            for key, value in properties.items()
            if key
            in {
                "must_read",
                "bounds",
                "validation",
                "forbidden_paths",
                "owned_paths",
                "worker_profile",
                "preferred_worker_profile",
                "tool_profile",
                "allowed_tools",
                "reuse_allowed",
                "dispatch_kind",
                "source_task_id",
                "parent_task_id",
                "task_owner",
                "closure_policy",
                "report_contract",
                "notes",
                "spec_refs",
                "context_tags",
                "provider_input",
            }
        },
    }


def _phase_goal_summary(goal: dict[str, Any]) -> dict[str, Any]:
    spec_refs = merge_spec_refs(
        goal.get("spec_refs"),
        goal.get("packet_template", {}).get("spec_refs")
        if isinstance(goal.get("packet_template"), dict)
        else None,
    )
    return {
        "goal_id": goal.get("goal_id"),
        "title": goal.get("title"),
        "status": goal.get("status"),
        "task_id": goal.get("task_id"),
        "worker_provider_id": goal.get("worker_provider_id"),
        "owned_paths": _goal_owned_paths(goal),
        "spec_ref_count": len(spec_refs),
        "spec_refs": spec_refs,
    }


def _normalize_goal(goal: dict[str, Any], *, phase_key: str) -> dict[str, Any]:
    normalized = dict(goal)
    theme_key = normalized.get("theme_key")
    if not isinstance(theme_key, str) or not theme_key.strip():
        theme_key = phase_key
    normalized["theme_key"] = theme_key.strip()
    for key in (
        "notes",
        "must_read",
        "bounds",
        "validation",
        "forbidden_paths",
        "owned_paths",
        "allowed_tools",
    ):
        if key in normalized and normalized[key] is None:
            normalized[key] = []
    if "spec_refs" in normalized:
        normalized["spec_refs"] = normalize_spec_refs(normalized.get("spec_refs"))
    packet_template = normalized.get("packet_template")
    if isinstance(packet_template, dict):
        for key in ("owned_paths",):
            if key in packet_template and packet_template[key] is None:
                packet_template[key] = []
        if "spec_refs" in packet_template:
            if packet_template["spec_refs"] is None:
                packet_template["spec_refs"] = []
            packet_template["spec_refs"] = normalize_spec_refs(packet_template.get("spec_refs"))
    return normalized


def validate_phase_goal_blueprint(
    goal: dict[str, Any],
    *,
    phase_key: str,
    path: str = "$.goal",
) -> dict[str, Any]:
    normalized = _normalize_goal(goal, phase_key=phase_key)
    required_fields = (
        "goal_id",
        "theme_key",
        "title",
        "objective",
        "task_id",
        "worker_provider_id",
        "packet_template",
    )
    missing_fields = [
        field
        for field in required_fields
        if field not in normalized
        or normalized[field] is None
        or (isinstance(normalized[field], str) and not normalized[field].strip())
    ]
    if missing_fields:
        raise SchemaValidationError(
            f"{path} is missing required goal blueprint fields: {', '.join(missing_fields)}"
        )
    validate_instance(
        normalized["packet_template"],
        _packet_template_schema(),
        path=f"{path}.packet_template",
    )
    return normalized


def _normalize_phase_plan(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    parallel_dispatch_limit = normalized.get("parallel_dispatch_limit")
    if not isinstance(parallel_dispatch_limit, int) or parallel_dispatch_limit < 1:
        parallel_dispatch_limit = 1
    normalized["parallel_dispatch_limit"] = parallel_dispatch_limit
    current_goal_ids = normalized.get("current_goal_ids")
    if not isinstance(current_goal_ids, list):
        current_goal_ids = []
    normalized["current_goal_ids"] = [
        str(goal_id).strip()
        for goal_id in current_goal_ids
        if isinstance(goal_id, str) and goal_id.strip()
    ]
    current_task_ids = normalized.get("current_task_ids")
    if not isinstance(current_task_ids, list):
        current_task_ids = []
    normalized["current_task_ids"] = [
        str(task_id).strip()
        for task_id in current_task_ids
        if isinstance(task_id, str) and task_id.strip()
    ]
    if not normalized["current_goal_ids"]:
        current_goal_id = normalized.get("current_goal_id")
        if isinstance(current_goal_id, str) and current_goal_id.strip():
            normalized["current_goal_ids"] = [current_goal_id.strip()]
    if not normalized["current_task_ids"]:
        current_task_id = normalized.get("current_task_id")
        if isinstance(current_task_id, str) and current_task_id.strip():
            normalized["current_task_ids"] = [current_task_id.strip()]
    normalized["current_goal_id"] = (
        normalized["current_goal_ids"][0] if normalized["current_goal_ids"] else None
    )
    normalized["current_task_id"] = (
        normalized["current_task_ids"][0] if normalized["current_task_ids"] else None
    )
    goals = normalized.get("goals")
    if not isinstance(goals, list):
        goals = []
    normalized["goals"] = [
        _normalize_goal(goal, phase_key=str(normalized.get("phase_key") or "").strip())
        for goal in goals
        if isinstance(goal, dict)
    ]
    return normalized


def _normalize_owned_path(path: str) -> str:
    return path.replace("\\", "/").strip().rstrip("/").casefold()


def _goal_owned_paths(goal: dict[str, Any]) -> list[str]:
    packet_template = goal.get("packet_template")
    if not isinstance(packet_template, dict):
        return []
    owned_paths = packet_template.get("owned_paths")
    if not isinstance(owned_paths, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for item in owned_paths:
        if not isinstance(item, str) or not item.strip():
            continue
        normalized_item = _normalize_owned_path(item)
        if not normalized_item or normalized_item in seen:
            continue
        seen.add(normalized_item)
        normalized.append(normalized_item)
    return normalized


def _owned_path_conflicts(left: list[str], right: list[str]) -> bool:
    for left_path in left:
        for right_path in right:
            if (
                left_path == right_path
                or left_path.startswith(f"{right_path}/")
                or right_path.startswith(f"{left_path}/")
            ):
                return True
    return False


def _phase_parallel_dispatch_limit(phase_plan: dict[str, Any]) -> int:
    value = phase_plan.get("parallel_dispatch_limit")
    if isinstance(value, int) and value >= 1:
        return value
    return 1


def _active_phase_goals(phase_plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        goal for goal in phase_plan.get("goals", []) if goal.get("status") == GOAL_STATUS_ACTIVE
    ]


def _set_phase_current_targets(phase_plan: dict[str, Any]) -> None:
    active_goals = _active_phase_goals(phase_plan)
    phase_plan["current_goal_ids"] = [goal["goal_id"] for goal in active_goals]
    phase_plan["current_task_ids"] = [goal["task_id"] for goal in active_goals]
    phase_plan["current_goal_id"] = (
        phase_plan["current_goal_ids"][0] if phase_plan["current_goal_ids"] else None
    )
    phase_plan["current_task_id"] = (
        phase_plan["current_task_ids"][0] if phase_plan["current_task_ids"] else None
    )


def _ready_parallel_goals(phase_plan: dict[str, Any]) -> list[dict[str, Any]]:
    active_goals = _active_phase_goals(phase_plan)
    parallel_limit = _phase_parallel_dispatch_limit(phase_plan)
    available_slots = max(parallel_limit - len(active_goals), 0)
    if available_slots <= 0:
        return []

    claimed_owned_paths = [_goal_owned_paths(goal) for goal in active_goals]
    if active_goals and any(not paths for paths in claimed_owned_paths):
        return []

    pending_goals = [
        goal for goal in phase_plan.get("goals", []) if goal.get("status") == GOAL_STATUS_PENDING
    ]
    selected: list[dict[str, Any]] = []
    selected_owned_paths: list[list[str]] = list(claimed_owned_paths)

    for goal in pending_goals:
        if len(selected) >= available_slots:
            break
        owned_paths = _goal_owned_paths(goal)
        if not owned_paths:
            continue
        if any(
            not other_paths or _owned_path_conflicts(owned_paths, other_paths)
            for other_paths in selected_owned_paths
        ):
            continue
        selected.append(goal)
        selected_owned_paths.append(owned_paths)

    if active_goals or selected or len(selected) >= available_slots:
        return selected

    for goal in pending_goals:
        if _goal_owned_paths(goal):
            continue
        return [goal]

    return selected


def validate_phase_plan(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_phase_plan(payload)
    validate_instance(normalized, _load_phase_plan_schema())
    for goal in normalized["goals"]:
        validate_phase_goal_blueprint(
            goal,
            phase_key=str(normalized.get("phase_key") or "").strip(),
            path=f"$.goals[{goal['goal_id']}]",
        )
    return normalized


def load_phase_plan(runtime_root: Path, phase_id: str) -> dict[str, Any]:
    payload = load_json(resolve_phase_plan_path(runtime_root, phase_id))
    if not isinstance(payload, dict):
        raise SchemaValidationError("Phase plan root must be an object")
    return validate_phase_plan(payload)


def write_phase_plan(runtime_root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    validated = validate_phase_plan(payload)
    write_json(resolve_phase_plan_path(runtime_root, validated["phase_id"]), validated)
    return validated


def list_phase_plans(runtime_root: Path) -> list[dict[str, Any]]:
    phase_dir = resolve_phase_plan_dir(runtime_root)
    if not phase_dir.exists():
        return []
    plans: list[dict[str, Any]] = []
    for path in sorted(phase_dir.glob("*.json")):
        payload = load_json(path)
        if isinstance(payload, dict):
            plans.append(validate_phase_plan(payload))
    return plans


def _require_theme_match(phase_plan: dict[str, Any], goal_payload: dict[str, Any]) -> None:
    phase_key = str(phase_plan.get("phase_key") or "").strip()
    goal_theme_key = str(goal_payload.get("theme_key") or phase_key).strip()
    if goal_theme_key != phase_key:
        raise SchemaValidationError(
            f"Goal theme_key {goal_theme_key!r} does not match active phase_key {phase_key!r}"
        )


def create_phase_plan(
    runtime_root: Path,
    *,
    phase_id: str,
    phase_key: str,
    phase_title: str,
    objective: str,
    goals: list[dict[str, Any]],
    phase_theme: str | None = None,
    parallel_dispatch_limit: int = 1,
) -> dict[str, Any]:
    now = utc_now()
    normalized_goals = []
    seen_goal_ids: set[str] = set()
    for goal in goals:
        normalized = _normalize_goal(goal, phase_key=phase_key)
        goal_id = normalized.get("goal_id")
        if goal_id in seen_goal_ids:
            raise SchemaValidationError(f"Duplicate goal_id in phase plan: {goal_id!r}")
        seen_goal_ids.add(goal_id)
        normalized.setdefault("status", GOAL_STATUS_PENDING)
        normalized.setdefault("notes", [])
        normalized.setdefault("activated_at", None)
        normalized.setdefault("completed_at", None)
        normalized.setdefault("completion_task_id", None)
        normalized.setdefault("last_rewritten_at", None)
        normalized_goals.append(normalized)

    payload = {
        "schema_version": "commander-harness-v1",
        "phase_id": phase_id,
        "phase_key": phase_key,
        "phase_title": phase_title,
        "phase_theme": phase_theme,
        "objective": objective,
        "status": PHASE_STATUS_ACTIVE,
        "parallel_dispatch_limit": max(int(parallel_dispatch_limit), 1),
        "current_goal_id": None,
        "current_task_id": None,
        "current_goal_ids": [],
        "current_task_ids": [],
        "goals": normalized_goals,
        "created_at": now,
        "updated_at": now,
    }
    return write_phase_plan(runtime_root, payload)


def append_phase_goal(
    runtime_root: Path,
    *,
    phase_id: str,
    goal_payload: dict[str, Any],
) -> dict[str, Any]:
    phase_plan = load_phase_plan(runtime_root, phase_id)
    _require_theme_match(phase_plan, goal_payload)
    goal = _normalize_goal(goal_payload, phase_key=phase_plan["phase_key"])
    goal_id = goal["goal_id"]
    if goal_id in _goal_ids(phase_plan["goals"]):
        raise SchemaValidationError(f"Goal already exists in phase plan: {goal_id!r}")
    goal.setdefault("status", GOAL_STATUS_PENDING)
    goal.setdefault("notes", [])
    goal.setdefault("activated_at", None)
    goal.setdefault("completed_at", None)
    goal.setdefault("completion_task_id", None)
    goal.setdefault("last_rewritten_at", None)
    phase_plan["goals"].append(goal)
    phase_plan["updated_at"] = utc_now()
    if phase_plan["status"] == PHASE_STATUS_COMPLETED:
        phase_plan["status"] = PHASE_STATUS_ACTIVE
    return write_phase_plan(runtime_root, phase_plan)


def rewrite_phase_goal(
    runtime_root: Path,
    *,
    phase_id: str,
    goal_id: str,
    goal_payload: dict[str, Any],
) -> dict[str, Any]:
    phase_plan = load_phase_plan(runtime_root, phase_id)
    _require_theme_match(phase_plan, goal_payload)
    rewritten = False
    for index, goal in enumerate(phase_plan["goals"]):
        if goal.get("goal_id") != goal_id:
            continue
        updated_goal = dict(goal)
        for key in (
            "title",
            "objective",
            "worker_provider_id",
            "packet_template",
            "notes",
            "theme_key",
            "task_id",
        ):
            if key in goal_payload:
                updated_goal[key] = goal_payload[key]
        updated_goal["last_rewritten_at"] = utc_now()
        phase_plan["goals"][index] = _normalize_goal(
            updated_goal, phase_key=phase_plan["phase_key"]
        )
        rewritten = True
        break
    if not rewritten:
        raise SchemaValidationError(f"Goal not found in phase plan: {goal_id!r}")
    phase_plan["updated_at"] = utc_now()
    return write_phase_plan(runtime_root, phase_plan)


def _classify_goal_completion(task_snapshot: dict[str, Any]) -> str:
    lifecycle_status = str(task_snapshot.get("lifecycle_status") or "").strip()
    result_grade = str(task_snapshot.get("result_grade") or "").strip()
    worker_status = str(task_snapshot.get("worker_status") or "").strip()
    if lifecycle_status in TERMINAL_TASK_LIFECYCLE and result_grade == "closed":
        return GOAL_STATUS_DONE
    if worker_status in {"blocked", "need_split"} or result_grade in {"blocked", "partial"}:
        return GOAL_STATUS_BLOCKED
    if lifecycle_status == "canceled":
        return GOAL_STATUS_CANCELED
    return GOAL_STATUS_DONE


def reconcile_phase_plan(
    runtime_root: Path,
    *,
    phase_id: str,
) -> dict[str, Any]:
    phase_plan = load_phase_plan(runtime_root, phase_id)
    for goal in phase_plan["goals"]:
        if goal.get("status") != GOAL_STATUS_ACTIVE:
            continue
        task_id = goal.get("task_id")
        if not isinstance(task_id, str) or not task_id.strip():
            continue
        paths = resolve_task_paths(runtime_root, task_id)
        if not paths.task_dir.exists():
            continue
        task_snapshot = refresh_status(paths)
        lifecycle_status = str(task_snapshot.get("lifecycle_status") or "").strip()
        if lifecycle_status not in TERMINAL_TASK_LIFECYCLE:
            continue
        goal["status"] = _classify_goal_completion(task_snapshot)
        goal["completed_at"] = utc_now()
        goal["completion_task_id"] = task_id

    _set_phase_current_targets(phase_plan)

    active_goals = _active_phase_goals(phase_plan)
    pending_goals = [goal for goal in phase_plan["goals"] if goal.get("status") == GOAL_STATUS_PENDING]
    open_goals = [
        goal
        for goal in phase_plan["goals"]
        if goal.get("status") not in {GOAL_STATUS_DONE, GOAL_STATUS_CANCELED}
    ]
    if not open_goals:
        phase_plan["status"] = PHASE_STATUS_COMPLETED
    elif phase_plan["status"] == PHASE_STATUS_COMPLETED and open_goals:
        phase_plan["status"] = PHASE_STATUS_ACTIVE
    elif pending_goals or active_goals:
        phase_plan["status"] = PHASE_STATUS_ACTIVE
    phase_plan["updated_at"] = utc_now()
    return write_phase_plan(runtime_root, phase_plan)


def build_phase_plan_summary(phase_plan: dict[str, Any]) -> dict[str, Any]:
    goals = phase_plan.get("goals", [])
    active_goals = [goal for goal in goals if goal.get("status") == GOAL_STATUS_ACTIVE]
    ready_goals = _ready_parallel_goals(phase_plan)
    pending_goal = next((goal for goal in goals if goal.get("status") == GOAL_STATUS_PENDING), None)
    active_goal = active_goals[0] if active_goals else None
    remaining_goal_count = sum(
        1
        for goal in goals
        if goal.get("status") not in {GOAL_STATUS_DONE, GOAL_STATUS_CANCELED}
    )
    parallel_dispatch_limit = _phase_parallel_dispatch_limit(phase_plan)
    available_parallel_slots = max(parallel_dispatch_limit - len(active_goals), 0)
    if active_goal is not None and ready_goals:
        next_action = f"Continue active phase goals and promote ready parallel goals starting with {ready_goals[0].get('goal_id')}"
    elif active_goal is not None:
        next_action = f"Continue active phase goal {active_goal.get('goal_id')}"
    elif ready_goals:
        next_action = f"Promote pending phase goal {ready_goals[0].get('goal_id')}"
    elif pending_goal is not None:
        next_action = f"Inspect pending phase goal {pending_goal.get('goal_id')}"
    elif phase_plan.get("status") == PHASE_STATUS_COMPLETED:
        next_action = "Phase is complete"
    else:
        next_action = "Inspect phase state"
    return {
        "phase_id": phase_plan.get("phase_id"),
        "phase_key": phase_plan.get("phase_key"),
        "phase_title": phase_plan.get("phase_title"),
        "phase_theme": phase_plan.get("phase_theme"),
        "status": phase_plan.get("status"),
        "parallel_dispatch_limit": parallel_dispatch_limit,
        "current_goal_id": phase_plan.get("current_goal_id"),
        "current_task_id": phase_plan.get("current_task_id"),
        "current_goal_ids": phase_plan.get("current_goal_ids", []),
        "current_task_ids": phase_plan.get("current_task_ids", []),
        "active_goal_count": len(active_goals),
        "available_parallel_slots": available_parallel_slots,
        "remaining_goal_count": remaining_goal_count,
        "pending_goal_count": sum(1 for goal in goals if goal.get("status") == GOAL_STATUS_PENDING),
        "has_remaining_goals": remaining_goal_count > 0,
        "promotable_goal_id": ready_goals[0].get("goal_id") if ready_goals else None,
        "promotable_goal_ids": [goal.get("goal_id") for goal in ready_goals],
        "active_goal": _phase_goal_summary(active_goal) if isinstance(active_goal, dict) else None,
        "active_goals": [_phase_goal_summary(goal) for goal in active_goals],
        "next_goal": _phase_goal_summary(ready_goals[0]) if ready_goals else (_phase_goal_summary(pending_goal) if isinstance(pending_goal, dict) else None),
        "goals": [_phase_goal_summary(goal) for goal in goals],
        "next_action": next_action,
        "updated_at": phase_plan.get("updated_at"),
    }


def list_active_phase_plan_summaries(runtime_root: Path) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for plan in list_phase_plans(runtime_root):
        reconciled = reconcile_phase_plan(runtime_root, phase_id=plan["phase_id"])
        summary = build_phase_plan_summary(reconciled)
        if summary["status"] in {PHASE_STATUS_ACTIVE, PHASE_STATUS_BLOCKED, PHASE_STATUS_PENDING_USER}:
            summaries.append(summary)
    summaries.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    return summaries


def load_primary_active_phase_plan_summary(runtime_root: Path) -> dict[str, Any] | None:
    summaries = list_active_phase_plan_summaries(runtime_root)
    return summaries[0] if summaries else None


def _build_worker_task_packet(goal: dict[str, Any]) -> dict[str, Any]:
    packet_template = dict(goal["packet_template"])
    spec_refs = merge_spec_refs(goal.get("spec_refs"), packet_template.get("spec_refs"))
    packet = {
        "schema_version": "commander-harness-v1",
        "task_id": goal["task_id"],
        "title": goal["title"],
        "goal": goal["objective"],
        **packet_template,
        "status": "dispatched",
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    if spec_refs:
        packet["spec_refs"] = spec_refs
    validate_instance(packet, load_schema(PACKET_SCHEMA_PATH))
    return packet


def promote_next_phase_goal(
    runtime_root: Path,
    *,
    phase_id: str | None = None,
) -> dict[str, Any]:
    summary = (
        load_primary_active_phase_plan_summary(runtime_root)
        if phase_id is None
        else build_phase_plan_summary(reconcile_phase_plan(runtime_root, phase_id=phase_id))
    )
    if not isinstance(summary, dict):
        return {
            "status": "no_active_phase",
            "worker_task_packet": None,
            "worker_provider_id": None,
            "phase_summary": None,
        }

    resolved_phase_id = str(summary["phase_id"])
    phase_plan = load_phase_plan(runtime_root, resolved_phase_id)
    if summary.get("active_goal"):
        active_goal = next(
            goal for goal in phase_plan["goals"] if goal["goal_id"] == summary["active_goal"]["goal_id"]
        )
        task_packet = _build_worker_task_packet(active_goal)
        task_materialization = dispatch_task(
            runtime_root,
            task_packet,
            provider_id=active_goal["worker_provider_id"],
            idempotency_key=f"{resolved_phase_id}:{active_goal['goal_id']}",
        )
        return {
            "status": "already_active",
            "worker_task_packet": task_packet,
            "worker_provider_id": active_goal["worker_provider_id"],
            "phase_summary": summary,
            "task_materialization": task_materialization,
        }

    promotable_goal_id = summary.get("promotable_goal_id")
    if not isinstance(promotable_goal_id, str) or not promotable_goal_id:
        phase_plan["status"] = PHASE_STATUS_COMPLETED
        phase_plan["updated_at"] = utc_now()
        phase_plan = write_phase_plan(runtime_root, phase_plan)
        return {
            "status": "phase_completed",
            "worker_task_packet": None,
            "worker_provider_id": None,
            "phase_summary": build_phase_plan_summary(phase_plan),
        }

    target_goal: dict[str, Any] | None = None
    for goal in phase_plan["goals"]:
        if goal["goal_id"] != promotable_goal_id:
            continue
        goal["status"] = GOAL_STATUS_ACTIVE
        goal["activated_at"] = utc_now()
        target_goal = goal
        break
    if target_goal is None:
        raise SchemaValidationError(f"Promotable goal not found: {promotable_goal_id!r}")

    phase_plan["current_goal_id"] = target_goal["goal_id"]
    phase_plan["current_task_id"] = target_goal["task_id"]
    phase_plan["status"] = PHASE_STATUS_ACTIVE
    _set_phase_current_targets(phase_plan)
    phase_plan["updated_at"] = utc_now()
    written = write_phase_plan(runtime_root, phase_plan)
    task_packet = _build_worker_task_packet(target_goal)
    task_materialization = dispatch_task(
        runtime_root,
        task_packet,
        provider_id=target_goal["worker_provider_id"],
        idempotency_key=f"{resolved_phase_id}:{target_goal['goal_id']}",
    )
    return {
        "status": "promoted",
        "worker_task_packet": task_packet,
        "worker_provider_id": target_goal["worker_provider_id"],
        "phase_summary": build_phase_plan_summary(written),
        "task_materialization": task_materialization,
    }


def promote_ready_phase_goals(
    runtime_root: Path,
    *,
    phase_id: str | None = None,
    max_promotions: int | None = None,
) -> dict[str, Any]:
    summary = (
        load_primary_active_phase_plan_summary(runtime_root)
        if phase_id is None
        else build_phase_plan_summary(reconcile_phase_plan(runtime_root, phase_id=phase_id))
    )
    if not isinstance(summary, dict):
        return {
            "status": "no_active_phase",
            "promoted_goal_ids": [],
            "phase_summary": None,
            "dispatches": [],
        }

    resolved_phase_id = str(summary["phase_id"])
    phase_plan = load_phase_plan(runtime_root, resolved_phase_id)
    ready_goals = _ready_parallel_goals(phase_plan)
    if isinstance(max_promotions, int) and max_promotions >= 0:
        ready_goals = ready_goals[:max_promotions]
    if not ready_goals:
        return {
            "status": "no_parallel_promotion",
            "promoted_goal_ids": [],
            "phase_summary": build_phase_plan_summary(phase_plan),
            "dispatches": [],
        }

    now = utc_now()
    selected_goal_ids = {goal["goal_id"] for goal in ready_goals}
    for goal in phase_plan["goals"]:
        if goal.get("goal_id") not in selected_goal_ids:
            continue
        goal["status"] = GOAL_STATUS_ACTIVE
        goal["activated_at"] = now
    phase_plan["status"] = PHASE_STATUS_ACTIVE
    _set_phase_current_targets(phase_plan)
    phase_plan["updated_at"] = now
    written = write_phase_plan(runtime_root, phase_plan)

    dispatches: list[dict[str, Any]] = []
    for goal in ready_goals:
        task_packet = _build_worker_task_packet(goal)
        task_materialization = dispatch_task(
            runtime_root,
            task_packet,
            provider_id=goal["worker_provider_id"],
            idempotency_key=f"{resolved_phase_id}:{goal['goal_id']}",
        )
        dispatches.append(
            {
                "goal_id": goal["goal_id"],
                "task_id": goal["task_id"],
                "worker_provider_id": goal["worker_provider_id"],
                "worker_task_packet": task_packet,
                "task_materialization": task_materialization,
            }
        )
    return {
        "status": "promoted_parallel_goals",
        "promoted_goal_ids": [goal["goal_id"] for goal in ready_goals],
        "phase_summary": build_phase_plan_summary(written),
        "dispatches": dispatches,
    }


def _load_json_file(path: str | None) -> dict[str, Any]:
    if path is None:
        raise SchemaValidationError("JSON input path is required")
    payload = load_json(Path(path))
    if not isinstance(payload, dict):
        raise SchemaValidationError(f"JSON payload must be an object: {path}")
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage commander phase plans.")
    parser.add_argument("--runtime-root", default=None, help="Override runtime root. Defaults to .runtime/commander")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create")
    create_parser.add_argument("--phase-id", required=True)
    create_parser.add_argument("--phase-key", required=True)
    create_parser.add_argument("--phase-title", required=True)
    create_parser.add_argument("--objective", required=True)
    create_parser.add_argument("--phase-theme", default=None)
    create_parser.add_argument("--parallel-dispatch-limit", type=int, default=1)
    create_parser.add_argument("--plan-file", required=True, help="JSON array file for initial goals")

    append_parser = subparsers.add_parser("append-goal")
    append_parser.add_argument("--phase-id", required=True)
    append_parser.add_argument("--goal-file", required=True)

    rewrite_parser = subparsers.add_parser("rewrite-goal")
    rewrite_parser.add_argument("--phase-id", required=True)
    rewrite_parser.add_argument("--goal-id", required=True)
    rewrite_parser.add_argument("--goal-file", required=True)

    promote_parser = subparsers.add_parser("promote-next-goal")
    promote_parser.add_argument("--phase-id", default=None)

    prefill_parser = subparsers.add_parser("promote-ready-goals")
    prefill_parser.add_argument("--phase-id", default=None)
    prefill_parser.add_argument("--max-promotions", type=int, default=None)

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--phase-id", default=None)

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    runtime_root = normalize_runtime_root(args.runtime_root)

    if args.command == "create":
        goals_payload = load_json(Path(args.plan_file))
        if not isinstance(goals_payload, list):
            raise SchemaValidationError("Initial plan file must contain a JSON array of goals")
        payload = create_phase_plan(
            runtime_root,
            phase_id=args.phase_id,
            phase_key=args.phase_key,
            phase_title=args.phase_title,
            objective=args.objective,
            goals=[goal for goal in goals_payload if isinstance(goal, dict)],
            phase_theme=args.phase_theme,
            parallel_dispatch_limit=args.parallel_dispatch_limit,
        )
    elif args.command == "append-goal":
        payload = append_phase_goal(
            runtime_root,
            phase_id=args.phase_id,
            goal_payload=_load_json_file(args.goal_file),
        )
    elif args.command == "rewrite-goal":
        payload = rewrite_phase_goal(
            runtime_root,
            phase_id=args.phase_id,
            goal_id=args.goal_id,
            goal_payload=_load_json_file(args.goal_file),
        )
    elif args.command == "promote-next-goal":
        payload = promote_next_phase_goal(runtime_root, phase_id=args.phase_id)
    elif args.command == "promote-ready-goals":
        payload = promote_ready_phase_goals(
            runtime_root,
            phase_id=args.phase_id,
            max_promotions=args.max_promotions,
        )
    else:
        if args.phase_id:
            payload = build_phase_plan_summary(
                reconcile_phase_plan(runtime_root, phase_id=args.phase_id)
            )
        else:
            payload = {
                "active_phase_plans": list_active_phase_plan_summaries(runtime_root),
            }

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
