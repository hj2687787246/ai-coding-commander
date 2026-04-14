from __future__ import annotations

from pathlib import Path

import pytest

from commander.transport.scripts.commander_harness import normalize_runtime_root
from commander.transport.scripts.commander_objective_plan import (
    PHASE_ENTRY_STATUS_ACTIVE,
    PHASE_ENTRY_STATUS_PENDING,
    SchemaValidationError,
    append_objective_phase,
    create_objective_plan,
    load_objective_plan,
    promote_next_objective_phase,
    rewrite_objective_phase,
)
from commander.transport.scripts.commander_phase_plan import load_phase_plan


def make_phase_goal(
    goal_id: str,
    task_id: str,
    *,
    theme_key: str = "langgraph-runtime",
    worker_provider_id: str = "local-script",
    provider_input: dict[str, object] | None = None,
    spec_refs: list[dict[str, object]] | None = None,
    owned_paths: list[str] | None = None,
) -> dict[str, object]:
    goal_spec_refs = spec_refs or []
    goal_owned_paths = owned_paths or []
    packet_template: dict[str, object] = {
        "must_read": ["README.md"],
        "bounds": ["commander only"],
        "validation": ["python -m pytest -q tests/test_commander_objective_plan.py"],
        "forbidden_paths": ["config/rag.yml"],
        "owned_paths": list(goal_owned_paths),
        "worker_profile": "code-worker",
        "preferred_worker_profile": None,
        "tool_profile": "control_plane_safe_write",
        "allowed_tools": ["apply_patch", "shell_command"],
        "reuse_allowed": True,
        "dispatch_kind": "fresh",
        "source_task_id": None,
        "parent_task_id": None,
        "task_owner": "commander",
        "closure_policy": "close_when_validated",
        "spec_refs": list(goal_spec_refs),
        "report_contract": {
            "allowed_statuses": ["done", "blocked", "need_split"],
            "required_fields": [
                "task_id",
                "status",
                "summary",
                "changed_files",
                "verification",
                "commit",
                "risks",
                "recommended_next_step",
                "needs_commander_decision",
                "result_grade",
                "next_action_owner",
                "continuation_mode",
            ],
        },
    }
    if provider_input is not None:
        packet_template["provider_input"] = provider_input
    return {
        "goal_id": goal_id,
        "theme_key": theme_key,
        "title": f"Goal {goal_id}",
        "objective": f"Implement {goal_id}",
        "task_id": task_id,
        "worker_provider_id": worker_provider_id,
        "spec_refs": list(goal_spec_refs),
        "packet_template": packet_template,
    }


def make_objective_phase(
    phase_id: str,
    task_id: str,
    *,
    theme_key: str = "langgraph-runtime",
    phase_key: str | None = None,
    worker_provider_id: str = "local-script",
    provider_input: dict[str, object] | None = None,
    spec_refs: list[dict[str, object]] | None = None,
    parallel_dispatch_limit: int = 1,
    owned_paths: list[str] | None = None,
) -> dict[str, object]:
    return {
        "phase_id": phase_id,
        "phase_key": phase_key or phase_id,
        "theme_key": theme_key,
        "phase_title": f"Phase {phase_id}",
        "parallel_dispatch_limit": parallel_dispatch_limit,
        "objective": f"Complete {phase_id}",
        "goals": [
            make_phase_goal(
                f"{phase_id}-goal-1",
                task_id,
                theme_key=theme_key,
                worker_provider_id=worker_provider_id,
                provider_input=provider_input,
                spec_refs=spec_refs,
                owned_paths=owned_paths,
            )
        ],
    }


def test_objective_plan_append_and_rewrite_require_same_theme(tmp_path: Path) -> None:
    runtime_root = normalize_runtime_root(tmp_path / "runtime")
    create_objective_plan(
        runtime_root,
        objective_id="objective-m2",
        objective_key="langgraph-runtime",
        objective_title="Milestone objective",
        objective="Keep long-running work machine-readable.",
        phases=[make_objective_phase("phase-1", "phase-1-task")],
    )

    appended = append_objective_phase(
        runtime_root,
        objective_id="objective-m2",
        phase_payload=make_objective_phase("phase-2", "phase-2-task"),
    )
    assert appended["status"] == "active"
    assert [phase["phase_id"] for phase in appended["phases"]] == ["phase-1", "phase-2"]

    with pytest.raises(SchemaValidationError):
        append_objective_phase(
            runtime_root,
            objective_id="objective-m2",
            phase_payload=make_objective_phase(
                "phase-x",
                "phase-x-task",
                theme_key="other-theme",
            ),
        )

    rewritten = rewrite_objective_phase(
        runtime_root,
        objective_id="objective-m2",
        phase_id="phase-2",
        phase_payload={
            "theme_key": "langgraph-runtime",
            "phase_title": "Phase 2 rewritten",
            "objective": "Rewrite inside the same objective theme.",
        },
    )
    phase_two = next(
        phase for phase in rewritten["phases"] if phase["phase_id"] == "phase-2"
    )
    assert phase_two["phase_title"] == "Phase 2 rewritten"
    assert phase_two["last_rewritten_at"] is not None

    promoted = promote_next_objective_phase(runtime_root, objective_id="objective-m2")
    assert promoted["status"] == "promoted"

    with pytest.raises(SchemaValidationError):
        rewrite_objective_phase(
            runtime_root,
            objective_id="objective-m2",
            phase_id="phase-1",
            phase_payload={
                "theme_key": "langgraph-runtime",
                "phase_title": "Should fail on active phase",
            },
        )


def test_objective_plan_promotion_creates_phase_plan(tmp_path: Path) -> None:
    runtime_root = normalize_runtime_root(tmp_path / "runtime")
    create_objective_plan(
        runtime_root,
        objective_id="objective-m2",
        objective_key="langgraph-runtime",
        objective_title="Milestone objective",
        objective="Promote the next phase automatically.",
        phases=[
            make_objective_phase(
                "phase-1",
                "phase-1-task",
                spec_refs=[
                    {
                        "spec_id": "task-5-7-spec-template",
                        "path": "commander/specs/task-5-7-spec-template.json",
                    }
                ],
            ),
            make_objective_phase("phase-2", "phase-2-task"),
        ],
    )

    promoted = promote_next_objective_phase(runtime_root, objective_id="objective-m2")

    assert promoted["status"] == "promoted"
    assert promoted["objective_summary"]["current_phase_id"] == "phase-1"
    assert promoted["objective_summary"]["promotable_phase_id"] is None
    assert promoted["objective_summary"]["next_phase"]["phase_id"] == "phase-2"
    assert promoted["phase_summary"]["phase_id"] == "phase-1"
    assert promoted["phase_summary"]["promotable_goal_id"] == "phase-1-goal-1"
    assert promoted["phase_summary"]["next_goal"]["spec_ref_count"] == 1
    assert promoted["phase_summary"]["next_goal"]["spec_refs"][0]["spec_id"] == "task-5-7-spec-template"
    assert promoted["objective_summary"]["current_phase"]["spec_ref_count"] == 1
    assert promoted["objective_summary"]["current_phase"]["spec_refs"][0]["spec_id"] == "task-5-7-spec-template"

    objective_plan = load_objective_plan(runtime_root, "objective-m2")
    phase_statuses = {
        phase["phase_id"]: phase["status"] for phase in objective_plan["phases"]
    }
    assert phase_statuses == {
        "phase-1": PHASE_ENTRY_STATUS_ACTIVE,
        "phase-2": PHASE_ENTRY_STATUS_PENDING,
    }

    phase_plan = load_phase_plan(runtime_root, "phase-1")
    assert phase_plan["phase_title"] == "Phase phase-1"
    assert phase_plan["goals"][0]["goal_id"] == "phase-1-goal-1"


def test_objective_plan_promotion_preserves_parallel_dispatch_limit(
    tmp_path: Path,
) -> None:
    runtime_root = normalize_runtime_root(tmp_path / "runtime")
    create_objective_plan(
        runtime_root,
        objective_id="objective-m2",
        objective_key="langgraph-runtime",
        objective_title="Milestone objective",
        objective="Carry parallel dispatch settings into the phase runtime.",
        phases=[
            make_objective_phase(
                "phase-1",
                "phase-1-task",
                parallel_dispatch_limit=3,
                owned_paths=["commander/graph/nodes"],
            )
        ],
    )

    promoted = promote_next_objective_phase(runtime_root, objective_id="objective-m2")
    phase_plan = load_phase_plan(runtime_root, "phase-1")

    assert promoted["status"] == "promoted"
    assert promoted["objective_summary"]["current_phase"]["parallel_dispatch_limit"] == 3
    assert phase_plan["parallel_dispatch_limit"] == 3
    assert phase_plan["goals"][0]["packet_template"]["owned_paths"] == [
        "commander/graph/nodes"
    ]
