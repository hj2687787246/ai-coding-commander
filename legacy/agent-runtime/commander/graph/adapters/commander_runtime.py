from __future__ import annotations

from pathlib import Path
from typing import Any

from commander.transport.scripts.commander_audit import build_audit_report
from commander.transport.scripts.commander_harness import (
    load_json,
    normalize_runtime_root,
    refresh_status,
    resolve_task_paths,
)
from commander.transport.scripts.commander_objective_plan import (
    load_primary_active_objective_plan_summary,
    promote_next_objective_phase,
)
from commander.transport.scripts.commander_phase_plan import (
    load_primary_active_phase_plan_summary,
    promote_next_phase_goal,
)
from commander.transport.scripts.commander_resume import build_resume_anchor
from commander.transport.scripts.commander_stop_gate import build_stop_gate_report


def restore_commander_state(
    runtime_root: str | Path | None,
    *,
    task_id: str | None = None,
) -> dict[str, Any] | None:
    """Load the compact resume anchor for one runtime task when available.

    Side-effect note: refresh_status may rewrite status/checkpoint files, but it
    is designed as an idempotent snapshot refresh over the same task artifacts.
    """

    if not task_id:
        return None

    resolved_runtime_root = normalize_runtime_root(runtime_root)
    paths = resolve_task_paths(resolved_runtime_root, task_id)
    snapshot = refresh_status(paths)
    if paths.resume_anchor_path.exists():
        payload = load_json(paths.resume_anchor_path)
        return payload if isinstance(payload, dict) else None
    checkpoint = load_json(paths.checkpoint_path)
    return build_resume_anchor(checkpoint) if isinstance(checkpoint, dict) else snapshot


def restore_active_phase_plan(
    runtime_root: str | Path | None,
) -> dict[str, Any] | None:
    resolved_runtime_root = normalize_runtime_root(runtime_root)
    return load_primary_active_phase_plan_summary(resolved_runtime_root)


def restore_active_objective_plan(
    runtime_root: str | Path | None,
) -> dict[str, Any] | None:
    resolved_runtime_root = normalize_runtime_root(runtime_root)
    return load_primary_active_objective_plan_summary(resolved_runtime_root)


def audit_commander_state(
    runtime_root: str | Path | None,
    *,
    task_card_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build the commander runtime/doc drift audit report."""

    return build_audit_report(runtime_root, task_card_path=task_card_path)


def run_stop_gate(
    runtime_root: str | Path | None,
    *,
    task_id: str | None = None,
    task_card_path: str | Path | None = None,
) -> dict[str, Any]:
    """Run the stop gate without treating a blocked stop as an exception."""

    return build_stop_gate_report(
        runtime_root, task_id=task_id, task_card_path=task_card_path
    )


def promote_commander_phase_goal(
    runtime_root: str | Path | None,
    *,
    phase_id: str | None = None,
) -> dict[str, Any]:
    resolved_runtime_root = normalize_runtime_root(runtime_root)
    return promote_next_phase_goal(resolved_runtime_root, phase_id=phase_id)


def promote_commander_objective_phase(
    runtime_root: str | Path | None,
    *,
    objective_id: str | None = None,
) -> dict[str, Any]:
    resolved_runtime_root = normalize_runtime_root(runtime_root)
    return promote_next_objective_phase(
        resolved_runtime_root, objective_id=objective_id
    )
