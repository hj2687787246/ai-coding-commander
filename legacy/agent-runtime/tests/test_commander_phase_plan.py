from __future__ import annotations

import json
from pathlib import Path

import pytest

from commander.transport.scripts.commander_harness import (
    normalize_runtime_root,
    load_json,
    resolve_task_paths,
)
from commander.transport.scripts.commander_phase_plan import (
    GOAL_STATUS_ACTIVE,
    GOAL_STATUS_PENDING,
    PHASE_STATUS_ACTIVE,
    SchemaValidationError,
    append_phase_goal,
    create_phase_plan,
    load_phase_plan,
    promote_next_phase_goal,
    promote_ready_phase_goals,
    rewrite_phase_goal,
)


def make_phase_goal(
    goal_id: str,
    task_id: str,
    *,
    theme_key: str = "langgraph-runtime",
    worker_provider_id: str = "local-script",
    spec_refs: list[dict[str, object]] | None = None,
    owned_paths: list[str] | None = None,
) -> dict[str, object]:
    goal_spec_refs = spec_refs or []
    goal_owned_paths = owned_paths or []
    return {
        "goal_id": goal_id,
        "theme_key": theme_key,
        "title": f"Goal {goal_id}",
        "objective": f"Implement {goal_id}",
        "task_id": task_id,
        "worker_provider_id": worker_provider_id,
        "spec_refs": list(goal_spec_refs),
        "packet_template": {
            "must_read": ["README.md"],
            "bounds": ["commander only"],
            "validation": ["python -m pytest -q tests/test_commander_phase_plan.py"],
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
        },
    }


def test_phase_plan_append_and_rewrite_require_same_theme(tmp_path: Path) -> None:
    runtime_root = normalize_runtime_root(tmp_path / "runtime")
    create_phase_plan(
        runtime_root,
        phase_id="phase-m2",
        phase_key="langgraph-runtime",
        phase_title="Milestone 2",
        objective="Keep phase goals machine-readable.",
        goals=[make_phase_goal("goal-1", "task-goal-1")],
    )

    appended = append_phase_goal(
        runtime_root,
        phase_id="phase-m2",
        goal_payload=make_phase_goal("goal-2", "task-goal-2"),
    )
    assert appended["status"] == PHASE_STATUS_ACTIVE
    assert [goal["goal_id"] for goal in appended["goals"]] == ["goal-1", "goal-2"]

    with pytest.raises(SchemaValidationError):
        append_phase_goal(
            runtime_root,
            phase_id="phase-m2",
            goal_payload=make_phase_goal(
                "goal-x",
                "task-goal-x",
                theme_key="other-theme",
            ),
        )

    rewritten = rewrite_phase_goal(
        runtime_root,
        phase_id="phase-m2",
        goal_id="goal-2",
        goal_payload={
            "theme_key": "langgraph-runtime",
            "title": "Goal 2 rewritten",
            "objective": "Rewrite inside the same phase theme.",
        },
    )
    goal_two = next(goal for goal in rewritten["goals"] if goal["goal_id"] == "goal-2")
    assert goal_two["title"] == "Goal 2 rewritten"
    assert goal_two["last_rewritten_at"] is not None

    with pytest.raises(SchemaValidationError):
        rewrite_phase_goal(
            runtime_root,
            phase_id="phase-m2",
            goal_id="goal-2",
            goal_payload={
                "theme_key": "different-theme",
                "title": "Should fail",
            },
        )


def test_phase_plan_promotion_marks_next_goal_active(tmp_path: Path) -> None:
    runtime_root = normalize_runtime_root(tmp_path / "runtime")
    create_phase_plan(
        runtime_root,
        phase_id="phase-m2",
        phase_key="langgraph-runtime",
        phase_title="Milestone 2",
        objective="Promote the next goal automatically.",
        goals=[
            make_phase_goal(
                "goal-1",
                "task-goal-1",
                spec_refs=[
                    {
                        "spec_id": "task-5-7-spec-template",
                        "path": "commander/specs/task-5-7-spec-template.json",
                    }
                ],
            ),
            make_phase_goal("goal-2", "task-goal-2"),
        ],
    )

    promoted = promote_next_phase_goal(runtime_root, phase_id="phase-m2")
    task_paths = resolve_task_paths(runtime_root, "task-goal-1")

    assert promoted["status"] == "promoted"
    assert promoted["worker_provider_id"] == "local-script"
    assert promoted["worker_task_packet"]["task_id"] == "task-goal-1"
    assert task_paths.packet_path.exists()
    assert task_paths.worker_brief_path.exists()
    assert task_paths.worker_report_path.exists()
    assert task_paths.context_bundle_path.exists()
    assert promoted["phase_summary"]["current_goal_id"] == "goal-1"
    assert promoted["phase_summary"]["promotable_goal_id"] is None
    assert promoted["phase_summary"]["next_goal"]["goal_id"] == "goal-2"
    assert promoted["task_materialization"]["worker_report_created"] is True
    assert promoted["worker_task_packet"]["spec_refs"][0]["spec_id"] == "task-5-7-spec-template"
    assert promoted["worker_task_packet"]["spec_refs"][0]["path"] == "commander/specs/task-5-7-spec-template.json"
    assert promoted["phase_summary"]["active_goal"]["spec_ref_count"] == 1
    assert promoted["phase_summary"]["active_goal"]["spec_refs"][0]["spec_id"] == "task-5-7-spec-template"

    context_bundle = load_json(task_paths.context_bundle_path)
    spec_entry = next(
        entry for entry in context_bundle["entries"] if entry["context_id"] == "spec_artifacts"
    )
    assert any(
        Path(path).as_posix().endswith("commander/specs/task-5-7-spec-template.json")
        for path in spec_entry["paths"]
    )

    worker_brief = task_paths.worker_brief_path.read_text(encoding="utf-8")
    assert "## Spec References" in worker_brief
    assert "task-5-7-spec-template" in worker_brief

    phase_plan = load_phase_plan(runtime_root, "phase-m2")
    goal_statuses = {goal["goal_id"]: goal["status"] for goal in phase_plan["goals"]}
    assert goal_statuses == {
        "goal-1": GOAL_STATUS_ACTIVE,
        "goal-2": GOAL_STATUS_PENDING,
    }


def test_phase_plan_already_active_promote_materializes_missing_runtime_files(
    tmp_path: Path,
) -> None:
    runtime_root = normalize_runtime_root(tmp_path / "runtime")
    create_phase_plan(
        runtime_root,
        phase_id="phase-m2",
        phase_key="langgraph-runtime",
        phase_title="Milestone 2",
        objective="Repair missing runtime files for an already active goal.",
        goals=[make_phase_goal("goal-1", "task-goal-1")],
    )

    first_promote = promote_next_phase_goal(runtime_root, phase_id="phase-m2")
    task_paths = resolve_task_paths(runtime_root, "task-goal-1")
    task_paths.packet_path.unlink()
    task_paths.context_bundle_path.unlink()
    task_paths.worker_brief_path.unlink()
    report_payload = {
        "schema_version": "commander-harness-v1",
        "task_id": "task-goal-1",
        "status": "done",
        "summary": "Existing report should be preserved.",
        "changed_files": ["commander/transport/scripts/commander_phase_plan.py"],
        "verification": [],
        "commit": {"message": "keep existing report"},
        "risks": [],
        "recommended_next_step": "Leave the report untouched.",
        "needs_commander_decision": False,
        "result_grade": "closed",
        "next_action_owner": "commander",
        "continuation_mode": "close",
        "decision_reason": None,
        "split_suggestion": None,
        "needs_user_decision": False,
        "user_decision_reason": None,
        "ready_for_user_delivery": False,
        "harness_metadata": {"is_dispatch_draft": False},
    }
    task_paths.worker_report_path.write_text(
        json.dumps(report_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    second_promote = promote_next_phase_goal(runtime_root, phase_id="phase-m2")
    restored_report = load_json(task_paths.worker_report_path)

    assert first_promote["status"] == "promoted"
    assert second_promote["status"] == "already_active"
    assert task_paths.packet_path.exists()
    assert task_paths.context_bundle_path.exists()
    assert task_paths.worker_brief_path.exists()
    assert task_paths.worker_report_path.exists()
    assert restored_report == report_payload
    assert second_promote["task_materialization"]["worker_report_created"] is False


def test_phase_plan_parallel_promotion_dispatches_non_overlapping_goals(
    tmp_path: Path,
) -> None:
    runtime_root = normalize_runtime_root(tmp_path / "runtime")
    create_phase_plan(
        runtime_root,
        phase_id="phase-m2",
        phase_key="langgraph-runtime",
        phase_title="Milestone 2",
        objective="Dispatch multiple non-overlapping goals in parallel.",
        parallel_dispatch_limit=2,
        goals=[
            make_phase_goal(
                "goal-1",
                "task-goal-1",
                owned_paths=["commander/graph/nodes/a.py"],
            ),
            make_phase_goal(
                "goal-2",
                "task-goal-2",
                owned_paths=["commander/graph/nodes/b.py"],
            ),
            make_phase_goal(
                "goal-3",
                "task-goal-3",
                owned_paths=["commander/graph/nodes/c.py"],
            ),
        ],
    )
    promote_next_phase_goal(runtime_root, phase_id="phase-m2")

    parallel = promote_ready_phase_goals(runtime_root, phase_id="phase-m2")
    phase_plan = load_phase_plan(runtime_root, "phase-m2")

    assert parallel["status"] == "promoted_parallel_goals"
    assert parallel["promoted_goal_ids"] == ["goal-2"]
    assert phase_plan["current_goal_ids"] == ["goal-1", "goal-2"]
    assert phase_plan["current_task_ids"] == ["task-goal-1", "task-goal-2"]
    goal_statuses = {goal["goal_id"]: goal["status"] for goal in phase_plan["goals"]}
    assert goal_statuses == {
        "goal-1": GOAL_STATUS_ACTIVE,
        "goal-2": GOAL_STATUS_ACTIVE,
        "goal-3": GOAL_STATUS_PENDING,
    }
    assert resolve_task_paths(runtime_root, "task-goal-2").packet_path.exists()
    assert not resolve_task_paths(runtime_root, "task-goal-3").packet_path.exists()


def test_phase_plan_parallel_promotion_skips_overlapping_write_sets(
    tmp_path: Path,
) -> None:
    runtime_root = normalize_runtime_root(tmp_path / "runtime")
    create_phase_plan(
        runtime_root,
        phase_id="phase-m2",
        phase_key="langgraph-runtime",
        phase_title="Milestone 2",
        objective="Skip overlapping owned paths during parallel promotion.",
        parallel_dispatch_limit=2,
        goals=[
            make_phase_goal(
                "goal-1",
                "task-goal-1",
                owned_paths=["commander/graph"],
            ),
            make_phase_goal(
                "goal-2",
                "task-goal-2",
                owned_paths=["commander/graph/nodes"],
            ),
            make_phase_goal(
                "goal-3",
                "task-goal-3",
                owned_paths=["commander/transport"],
            ),
        ],
    )
    promote_next_phase_goal(runtime_root, phase_id="phase-m2")

    parallel = promote_ready_phase_goals(runtime_root, phase_id="phase-m2")
    phase_plan = load_phase_plan(runtime_root, "phase-m2")

    assert parallel["status"] == "promoted_parallel_goals"
    assert parallel["promoted_goal_ids"] == ["goal-3"]
    assert phase_plan["current_goal_ids"] == ["goal-1", "goal-3"]
    assert phase_plan["current_task_ids"] == ["task-goal-1", "task-goal-3"]
    assert resolve_task_paths(runtime_root, "task-goal-3").packet_path.exists()
    assert not resolve_task_paths(runtime_root, "task-goal-2").packet_path.exists()
