from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from commander.transport.scripts.commander_harness import (
    SchemaValidationError,
    load_json,
    load_schema,
    normalize_runtime_root,
    utc_now,
    validate_instance,
    write_json,
)
from commander.transport.scripts.commander_phase_plan import (
    PHASE_STATUS_BLOCKED,
    PHASE_STATUS_COMPLETED,
    PHASE_STATUS_PENDING_USER,
    build_phase_plan_summary,
    create_phase_plan,
    reconcile_phase_plan,
    resolve_phase_plan_path,
    validate_phase_goal_blueprint,
)
from commander.transport.scripts.commander_spec_kit import normalize_spec_refs


COMMANDER_ROOT = Path(__file__).resolve().parents[2]
OBJECTIVE_PLAN_SCHEMA_PATH = (
    COMMANDER_ROOT / "transport" / "schemas" / "commander_objective_plan.schema.json"
)
OBJECTIVE_STATUS_ACTIVE = "active"
OBJECTIVE_STATUS_BLOCKED = "blocked"
OBJECTIVE_STATUS_PENDING_USER = "pending_user"
OBJECTIVE_STATUS_COMPLETED = "completed"
OBJECTIVE_STATUS_ARCHIVED = "archived"
PHASE_ENTRY_STATUS_PENDING = "pending"
PHASE_ENTRY_STATUS_ACTIVE = "active"
PHASE_ENTRY_STATUS_DONE = "done"
PHASE_ENTRY_STATUS_BLOCKED = "blocked"
PHASE_ENTRY_STATUS_CANCELED = "canceled"


def resolve_objective_plan_dir(runtime_root: Path) -> Path:
    return runtime_root / "objectives"


def resolve_objective_plan_path(runtime_root: Path, objective_id: str) -> Path:
    return resolve_objective_plan_dir(runtime_root) / f"{objective_id}.json"


def _load_objective_plan_schema() -> dict[str, Any]:
    return load_schema(OBJECTIVE_PLAN_SCHEMA_PATH)


def _phase_ids(phases: list[dict[str, Any]]) -> set[str]:
    return {
        phase["phase_id"]
        for phase in phases
        if isinstance(phase, dict) and isinstance(phase.get("phase_id"), str)
    }


def _normalize_phase_entry(
    phase: dict[str, Any],
    *,
    objective_key: str,
) -> dict[str, Any]:
    normalized = dict(phase)
    theme_key = normalized.get("theme_key")
    if not isinstance(theme_key, str) or not theme_key.strip():
        theme_key = objective_key
    normalized["theme_key"] = theme_key.strip()
    phase_key = normalized.get("phase_key")
    if not isinstance(phase_key, str) or not phase_key.strip():
        phase_key = normalized["theme_key"]
    normalized["phase_key"] = phase_key.strip()
    parallel_dispatch_limit = normalized.get("parallel_dispatch_limit")
    if not isinstance(parallel_dispatch_limit, int) or parallel_dispatch_limit < 1:
        parallel_dispatch_limit = 1
    normalized["parallel_dispatch_limit"] = parallel_dispatch_limit
    goals = normalized.get("goals")
    if not isinstance(goals, list):
        goals = []
    normalized["goals"] = [
        validate_phase_goal_blueprint(
            goal,
            phase_key=normalized["phase_key"],
            path=f"$.phases[{normalized.get('phase_id', 'unknown')}].goals[{index}]",
        )
        for index, goal in enumerate(goals)
        if isinstance(goal, dict)
    ]
    for key in ("notes", "spec_refs"):
        if key in normalized and normalized[key] is None:
            normalized[key] = []
    if "spec_refs" in normalized:
        normalized["spec_refs"] = normalize_spec_refs(normalized.get("spec_refs"))
    return normalized


def _normalize_objective_plan(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    phases = normalized.get("phases")
    if not isinstance(phases, list):
        phases = []
    objective_key = str(normalized.get("objective_key") or "").strip()
    normalized["phases"] = [
        _normalize_phase_entry(phase, objective_key=objective_key)
        for phase in phases
        if isinstance(phase, dict)
    ]
    return normalized


def validate_objective_plan(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_objective_plan(payload)
    validate_instance(normalized, _load_objective_plan_schema())
    return normalized


def load_objective_plan(runtime_root: Path, objective_id: str) -> dict[str, Any]:
    payload = load_json(resolve_objective_plan_path(runtime_root, objective_id))
    if not isinstance(payload, dict):
        raise SchemaValidationError("Objective plan root must be an object")
    return validate_objective_plan(payload)


def write_objective_plan(runtime_root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    validated = validate_objective_plan(payload)
    write_json(
        resolve_objective_plan_path(runtime_root, validated["objective_id"]),
        validated,
    )
    return validated


def list_objective_plans(runtime_root: Path) -> list[dict[str, Any]]:
    objective_dir = resolve_objective_plan_dir(runtime_root)
    if not objective_dir.exists():
        return []
    plans: list[dict[str, Any]] = []
    for path in sorted(objective_dir.glob("*.json")):
        payload = load_json(path)
        if isinstance(payload, dict):
            plans.append(validate_objective_plan(payload))
    return plans


def _require_theme_match(
    objective_plan: dict[str, Any],
    phase_payload: dict[str, Any],
) -> None:
    objective_key = str(objective_plan.get("objective_key") or "").strip()
    phase_theme_key = str(phase_payload.get("theme_key") or objective_key).strip()
    if phase_theme_key != objective_key:
        raise SchemaValidationError(
            f"Phase theme_key {phase_theme_key!r} does not match active objective_key {objective_key!r}"
        )


def create_objective_plan(
    runtime_root: Path,
    *,
    objective_id: str,
    objective_key: str,
    objective_title: str,
    objective: str,
    phases: list[dict[str, Any]],
    objective_theme: str | None = None,
) -> dict[str, Any]:
    now = utc_now()
    normalized_phases: list[dict[str, Any]] = []
    seen_phase_ids: set[str] = set()
    for phase in phases:
        normalized = _normalize_phase_entry(phase, objective_key=objective_key)
        phase_id = normalized.get("phase_id")
        if phase_id in seen_phase_ids:
            raise SchemaValidationError(
                f"Duplicate phase_id in objective plan: {phase_id!r}"
            )
        seen_phase_ids.add(phase_id)
        normalized.setdefault("status", PHASE_ENTRY_STATUS_PENDING)
        normalized.setdefault("phase_plan_id", normalized["phase_id"])
        normalized.setdefault("notes", [])
        normalized.setdefault("activated_at", None)
        normalized.setdefault("completed_at", None)
        normalized.setdefault("last_rewritten_at", None)
        normalized_phases.append(normalized)

    payload = {
        "schema_version": "commander-harness-v1",
        "objective_id": objective_id,
        "objective_key": objective_key,
        "objective_title": objective_title,
        "objective_theme": objective_theme,
        "objective": objective,
        "status": OBJECTIVE_STATUS_ACTIVE,
        "current_phase_id": None,
        "current_phase_plan_id": None,
        "phases": normalized_phases,
        "created_at": now,
        "updated_at": now,
    }
    return write_objective_plan(runtime_root, payload)


def append_objective_phase(
    runtime_root: Path,
    *,
    objective_id: str,
    phase_payload: dict[str, Any],
) -> dict[str, Any]:
    objective_plan = load_objective_plan(runtime_root, objective_id)
    _require_theme_match(objective_plan, phase_payload)
    phase = _normalize_phase_entry(
        phase_payload, objective_key=objective_plan["objective_key"]
    )
    phase_id = phase["phase_id"]
    if phase_id in _phase_ids(objective_plan["phases"]):
        raise SchemaValidationError(
            f"Phase already exists in objective plan: {phase_id!r}"
        )
    phase.setdefault("status", PHASE_ENTRY_STATUS_PENDING)
    phase.setdefault("phase_plan_id", phase["phase_id"])
    phase.setdefault("notes", [])
    phase.setdefault("activated_at", None)
    phase.setdefault("completed_at", None)
    phase.setdefault("last_rewritten_at", None)
    objective_plan["phases"].append(phase)
    objective_plan["updated_at"] = utc_now()
    if objective_plan["status"] == OBJECTIVE_STATUS_COMPLETED:
        objective_plan["status"] = OBJECTIVE_STATUS_ACTIVE
    return write_objective_plan(runtime_root, objective_plan)


def rewrite_objective_phase(
    runtime_root: Path,
    *,
    objective_id: str,
    phase_id: str,
    phase_payload: dict[str, Any],
) -> dict[str, Any]:
    objective_plan = load_objective_plan(runtime_root, objective_id)
    _require_theme_match(objective_plan, phase_payload)
    rewritten = False
    for index, phase in enumerate(objective_plan["phases"]):
        if phase.get("phase_id") != phase_id:
            continue
        if phase.get("status") == PHASE_ENTRY_STATUS_ACTIVE and phase.get(
            "phase_plan_id"
        ):
            raise SchemaValidationError(
                f"Phase {phase_id!r} is already active; rewrite the live phase via commander_phase_plan instead."
            )
        updated_phase = dict(phase)
        for key in (
            "phase_key",
            "phase_title",
            "objective",
            "phase_theme",
            "theme_key",
            "goals",
            "notes",
        ):
            if key in phase_payload:
                updated_phase[key] = phase_payload[key]
        updated_phase["last_rewritten_at"] = utc_now()
        objective_plan["phases"][index] = _normalize_phase_entry(
            updated_phase, objective_key=objective_plan["objective_key"]
        )
        rewritten = True
        break
    if not rewritten:
        raise SchemaValidationError(
            f"Phase not found in objective plan: {phase_id!r}"
        )
    objective_plan["updated_at"] = utc_now()
    return write_objective_plan(runtime_root, objective_plan)


def _phase_entry_summary(
    phase: dict[str, Any],
    *,
    phase_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    status = phase_summary.get("status") if isinstance(phase_summary, dict) else phase.get(
        "status"
    )
    current_task_id = (
        phase_summary.get("current_task_id")
        if isinstance(phase_summary, dict)
        else None
    )
    remaining_goal_count = (
        phase_summary.get("remaining_goal_count")
        if isinstance(phase_summary, dict)
        else None
    )
    active_goal_count = (
        phase_summary.get("active_goal_count")
        if isinstance(phase_summary, dict)
        else None
    )
    active_task_ids = (
        phase_summary.get("current_task_ids")
        if isinstance(phase_summary, dict)
        else None
    )
    spec_refs = None
    if isinstance(phase_summary, dict):
        active_goal = phase_summary.get("active_goal")
        if not isinstance(active_goal, dict):
            active_goal = phase_summary.get("next_goal")
        if isinstance(active_goal, dict):
            spec_refs = active_goal.get("spec_refs")
    if spec_refs is None:
        goals = phase.get("goals")
        if isinstance(goals, list):
            first_goal = next((goal for goal in goals if isinstance(goal, dict)), None)
            if isinstance(first_goal, dict):
                spec_refs = first_goal.get("spec_refs")
                if spec_refs is None:
                    packet_template = first_goal.get("packet_template")
                    if isinstance(packet_template, dict):
                        spec_refs = packet_template.get("spec_refs")
    return {
        "phase_id": phase.get("phase_id"),
        "phase_key": phase.get("phase_key"),
        "theme_key": phase.get("theme_key"),
        "phase_title": phase.get("phase_title"),
        "status": status,
        "parallel_dispatch_limit": phase.get("parallel_dispatch_limit"),
        "phase_plan_id": phase.get("phase_plan_id"),
        "current_task_id": current_task_id,
        "active_task_ids": active_task_ids if isinstance(active_task_ids, list) else [],
        "active_goal_count": active_goal_count,
        "remaining_goal_count": remaining_goal_count,
        "spec_ref_count": len(spec_refs) if isinstance(spec_refs, list) else 0,
        "spec_refs": spec_refs if isinstance(spec_refs, list) else [],
    }


def _phase_summary_for_entry(
    runtime_root: Path,
    phase: dict[str, Any],
) -> dict[str, Any] | None:
    phase_plan_id = phase.get("phase_plan_id")
    if not isinstance(phase_plan_id, str) or not phase_plan_id.strip():
        return None
    phase_plan_path = resolve_phase_plan_path(runtime_root, phase_plan_id)
    if not phase_plan_path.exists():
        return None
    phase_plan = reconcile_phase_plan(runtime_root, phase_id=phase_plan_id)
    return build_phase_plan_summary(phase_plan)


def reconcile_objective_plan(
    runtime_root: Path,
    *,
    objective_id: str,
) -> dict[str, Any]:
    objective_plan = load_objective_plan(runtime_root, objective_id)
    current_phase_id = objective_plan.get("current_phase_id")
    current_phase_plan_id = objective_plan.get("current_phase_plan_id")
    current_phase_summary: dict[str, Any] | None = None

    if (
        isinstance(current_phase_id, str)
        and current_phase_id
        and isinstance(current_phase_plan_id, str)
        and current_phase_plan_id
    ):
        phase_plan_path = resolve_phase_plan_path(runtime_root, current_phase_plan_id)
        if phase_plan_path.exists():
            phase_plan = reconcile_phase_plan(runtime_root, phase_id=current_phase_plan_id)
            current_phase_summary = build_phase_plan_summary(phase_plan)
            phase_status = str(current_phase_summary.get("status") or "").strip()
            for phase in objective_plan["phases"]:
                if phase.get("phase_id") != current_phase_id:
                    continue
                if phase_status == PHASE_STATUS_COMPLETED:
                    phase["status"] = PHASE_ENTRY_STATUS_DONE
                    phase["completed_at"] = utc_now()
                    objective_plan["current_phase_id"] = None
                    objective_plan["current_phase_plan_id"] = None
                    current_phase_summary = None
                elif phase_status == PHASE_STATUS_BLOCKED:
                    phase["status"] = PHASE_ENTRY_STATUS_BLOCKED
                elif phase_status == PHASE_STATUS_PENDING_USER:
                    phase["status"] = PHASE_ENTRY_STATUS_BLOCKED
                else:
                    phase["status"] = PHASE_ENTRY_STATUS_ACTIVE
                break

    if objective_plan.get("current_phase_id") is None:
        active_phase = next(
            (
                phase
                for phase in objective_plan["phases"]
                if phase.get("status") == PHASE_ENTRY_STATUS_ACTIVE
            ),
            None,
        )
        if isinstance(active_phase, dict):
            objective_plan["current_phase_id"] = active_phase["phase_id"]
            objective_plan["current_phase_plan_id"] = active_phase.get("phase_plan_id")

    open_phases = [
        phase
        for phase in objective_plan["phases"]
        if phase.get("status") not in {PHASE_ENTRY_STATUS_DONE, PHASE_ENTRY_STATUS_CANCELED}
    ]
    if not open_phases:
        objective_plan["status"] = OBJECTIVE_STATUS_COMPLETED
    elif objective_plan["status"] == OBJECTIVE_STATUS_COMPLETED:
        objective_plan["status"] = OBJECTIVE_STATUS_ACTIVE
    else:
        objective_plan["status"] = OBJECTIVE_STATUS_ACTIVE

    objective_plan["updated_at"] = utc_now()
    return write_objective_plan(runtime_root, objective_plan)


def build_objective_plan_summary(
    runtime_root: Path,
    objective_plan: dict[str, Any],
) -> dict[str, Any]:
    phases = objective_plan.get("phases", [])
    current_phase_summary: dict[str, Any] | None = None
    current_phase_id = objective_plan.get("current_phase_id")
    summarized_phases: list[dict[str, Any]] = []
    for phase in phases:
        phase_summary = _phase_summary_for_entry(runtime_root, phase)
        if phase.get("phase_id") == current_phase_id:
            current_phase_summary = phase_summary
        summarized_phases.append(_phase_entry_summary(phase, phase_summary=phase_summary))

    pending_phase = next(
        (phase for phase in phases if phase.get("status") == PHASE_ENTRY_STATUS_PENDING),
        None,
    )
    active_phase = next(
        (phase for phase in phases if phase.get("status") == PHASE_ENTRY_STATUS_ACTIVE),
        None,
    )
    remaining_phase_count = sum(
        1
        for phase in phases
        if phase.get("status")
        not in {PHASE_ENTRY_STATUS_DONE, PHASE_ENTRY_STATUS_CANCELED}
    )
    if active_phase is not None:
        next_action = f"Continue active objective phase {active_phase.get('phase_id')}"
    elif pending_phase is not None:
        next_action = f"Promote pending objective phase {pending_phase.get('phase_id')}"
    elif objective_plan.get("status") == OBJECTIVE_STATUS_COMPLETED:
        next_action = "Objective is complete"
    else:
        next_action = "Inspect objective state"
    current_phase_status = (
        current_phase_summary.get("status")
        if isinstance(current_phase_summary, dict)
        else (
            active_phase.get("status")
            if isinstance(active_phase, dict)
            else None
        )
    )
    return {
        "objective_id": objective_plan.get("objective_id"),
        "objective_key": objective_plan.get("objective_key"),
        "objective_title": objective_plan.get("objective_title"),
        "objective_theme": objective_plan.get("objective_theme"),
        "objective": objective_plan.get("objective"),
        "status": objective_plan.get("status"),
        "current_phase_id": objective_plan.get("current_phase_id"),
        "current_phase_plan_id": objective_plan.get("current_phase_plan_id"),
        "remaining_phase_count": remaining_phase_count,
        "pending_phase_count": sum(
            1 for phase in phases if phase.get("status") == PHASE_ENTRY_STATUS_PENDING
        ),
        "has_remaining_phases": remaining_phase_count > 0,
        "promotable_phase_id": (
            pending_phase.get("phase_id")
            if isinstance(pending_phase, dict) and active_phase is None
            else None
        ),
        "current_phase_status": current_phase_status,
        "current_phase": (
            _phase_entry_summary(active_phase, phase_summary=current_phase_summary)
            if isinstance(active_phase, dict)
            else None
        ),
        "next_phase": (
            _phase_entry_summary(pending_phase)
            if isinstance(pending_phase, dict)
            else None
        ),
        "phases": summarized_phases,
        "next_action": next_action,
        "updated_at": objective_plan.get("updated_at"),
    }


def list_active_objective_plan_summaries(runtime_root: Path) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for plan in list_objective_plans(runtime_root):
        reconciled = reconcile_objective_plan(runtime_root, objective_id=plan["objective_id"])
        summary = build_objective_plan_summary(runtime_root, reconciled)
        if summary["status"] in {
            OBJECTIVE_STATUS_ACTIVE,
            OBJECTIVE_STATUS_BLOCKED,
            OBJECTIVE_STATUS_PENDING_USER,
        }:
            summaries.append(summary)
    summaries.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    return summaries


def load_primary_active_objective_plan_summary(
    runtime_root: Path,
) -> dict[str, Any] | None:
    summaries = list_active_objective_plan_summaries(runtime_root)
    return summaries[0] if summaries else None


def promote_next_objective_phase(
    runtime_root: Path,
    *,
    objective_id: str | None = None,
) -> dict[str, Any]:
    summary = (
        load_primary_active_objective_plan_summary(runtime_root)
        if objective_id is None
        else build_objective_plan_summary(
            runtime_root,
            reconcile_objective_plan(runtime_root, objective_id=objective_id),
        )
    )
    if not isinstance(summary, dict):
        return {
            "status": "no_active_objective",
            "objective_summary": None,
            "phase_summary": None,
        }

    resolved_objective_id = str(summary["objective_id"])
    objective_plan = load_objective_plan(runtime_root, resolved_objective_id)
    if summary.get("current_phase"):
        current_phase = next(
            phase
            for phase in objective_plan["phases"]
            if phase["phase_id"] == summary["current_phase"]["phase_id"]
        )
        phase_summary = _phase_summary_for_entry(runtime_root, current_phase)
        return {
            "status": "already_active",
            "objective_summary": summary,
            "phase_summary": phase_summary,
        }

    promotable_phase_id = summary.get("promotable_phase_id")
    if not isinstance(promotable_phase_id, str) or not promotable_phase_id:
        objective_plan["status"] = OBJECTIVE_STATUS_COMPLETED
        objective_plan["updated_at"] = utc_now()
        written = write_objective_plan(runtime_root, objective_plan)
        return {
            "status": "objective_completed",
            "objective_summary": build_objective_plan_summary(runtime_root, written),
            "phase_summary": None,
        }

    target_phase: dict[str, Any] | None = None
    for phase in objective_plan["phases"]:
        if phase["phase_id"] != promotable_phase_id:
            continue
        phase["status"] = PHASE_ENTRY_STATUS_ACTIVE
        phase["activated_at"] = utc_now()
        target_phase = phase
        break
    if target_phase is None:
        raise SchemaValidationError(
            f"Promotable phase not found: {promotable_phase_id!r}"
        )

    phase_plan_id = str(target_phase.get("phase_plan_id") or target_phase["phase_id"]).strip()
    phase_plan_path = resolve_phase_plan_path(runtime_root, phase_plan_id)
    if phase_plan_path.exists():
        phase_plan = reconcile_phase_plan(runtime_root, phase_id=phase_plan_id)
    else:
        phase_plan = create_phase_plan(
            runtime_root,
            phase_id=phase_plan_id,
            phase_key=str(target_phase["phase_key"]),
            phase_title=str(target_phase["phase_title"]),
            objective=str(target_phase["objective"]),
            phase_theme=(
                str(target_phase["phase_theme"]).strip()
                if isinstance(target_phase.get("phase_theme"), str)
                else None
            ),
            parallel_dispatch_limit=int(target_phase.get("parallel_dispatch_limit") or 1),
            goals=[
                goal
                for goal in target_phase.get("goals", [])
                if isinstance(goal, dict)
            ],
        )

    target_phase["phase_plan_id"] = phase_plan_id
    objective_plan["current_phase_id"] = target_phase["phase_id"]
    objective_plan["current_phase_plan_id"] = phase_plan_id
    objective_plan["status"] = OBJECTIVE_STATUS_ACTIVE
    objective_plan["updated_at"] = utc_now()
    written = write_objective_plan(runtime_root, objective_plan)
    return {
        "status": "promoted",
        "objective_summary": build_objective_plan_summary(runtime_root, written),
        "phase_summary": build_phase_plan_summary(phase_plan),
    }


def _load_json_file(path: str | None) -> dict[str, Any]:
    if path is None:
        raise SchemaValidationError("JSON input path is required")
    payload = load_json(Path(path))
    if not isinstance(payload, dict):
        raise SchemaValidationError(f"JSON payload must be an object: {path}")
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage commander objective plans.")
    parser.add_argument(
        "--runtime-root",
        default=None,
        help="Override runtime root. Defaults to .runtime/commander",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create")
    create_parser.add_argument("--objective-id", required=True)
    create_parser.add_argument("--objective-key", required=True)
    create_parser.add_argument("--objective-title", required=True)
    create_parser.add_argument("--objective", required=True)
    create_parser.add_argument("--objective-theme", default=None)
    create_parser.add_argument(
        "--plan-file", required=True, help="JSON array file for initial phases"
    )

    append_parser = subparsers.add_parser("append-phase")
    append_parser.add_argument("--objective-id", required=True)
    append_parser.add_argument("--phase-file", required=True)

    rewrite_parser = subparsers.add_parser("rewrite-phase")
    rewrite_parser.add_argument("--objective-id", required=True)
    rewrite_parser.add_argument("--phase-id", required=True)
    rewrite_parser.add_argument("--phase-file", required=True)

    promote_parser = subparsers.add_parser("promote-next-phase")
    promote_parser.add_argument("--objective-id", default=None)

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--objective-id", default=None)

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    runtime_root = normalize_runtime_root(args.runtime_root)

    if args.command == "create":
        phases_payload = load_json(Path(args.plan_file))
        if not isinstance(phases_payload, list):
            raise SchemaValidationError(
                "Initial plan file must contain a JSON array of phases"
            )
        payload = create_objective_plan(
            runtime_root,
            objective_id=args.objective_id,
            objective_key=args.objective_key,
            objective_title=args.objective_title,
            objective=args.objective,
            phases=[phase for phase in phases_payload if isinstance(phase, dict)],
            objective_theme=args.objective_theme,
        )
    elif args.command == "append-phase":
        payload = append_objective_phase(
            runtime_root,
            objective_id=args.objective_id,
            phase_payload=_load_json_file(args.phase_file),
        )
    elif args.command == "rewrite-phase":
        payload = rewrite_objective_phase(
            runtime_root,
            objective_id=args.objective_id,
            phase_id=args.phase_id,
            phase_payload=_load_json_file(args.phase_file),
        )
    elif args.command == "promote-next-phase":
        payload = promote_next_objective_phase(
            runtime_root, objective_id=args.objective_id
        )
    else:
        if args.objective_id:
            payload = build_objective_plan_summary(
                runtime_root,
                reconcile_objective_plan(runtime_root, objective_id=args.objective_id),
            )
        else:
            payload = {
                "active_objective_plans": list_active_objective_plan_summaries(
                    runtime_root
                ),
            }

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
