from __future__ import annotations

import sys
from pathlib import Path

from commander.graph.runners.run_until_objective_handoff import (
    run_until_objective_handoff,
)
from commander.transport.scripts.commander_harness import (
    load_json,
    normalize_runtime_root,
    resolve_task_paths,
)
from commander.transport.scripts.commander_objective_plan import (
    create_objective_plan,
    load_objective_plan,
)


PYTHON_EXE = Path(sys.executable)


def write_task_card(path: Path) -> None:
    path.write_text(
        "# Current Task Card\n\n## 5. Active Tasks\n\nNo active tasks.\n",
        encoding="utf-8",
    )


def make_phase_goal(
    goal_id: str,
    task_id: str,
    *,
    worker_provider_id: str = "local-script",
    provider_input: dict[str, object] | None = None,
) -> dict[str, object]:
    tool_profile = (
        "default" if worker_provider_id == "local-script" else "control_plane_safe_write"
    )
    allowed_tools = ["shell_command"] if worker_provider_id == "local-script" else [
        "apply_patch",
        "shell_command",
    ]
    packet_template: dict[str, object] = {
        "must_read": ["README.md"],
        "bounds": ["commander only"],
        "validation": ["python -m pytest -q tests/test_commander_objective_runner.py"],
        "forbidden_paths": ["config/rag.yml"],
        "worker_profile": "code-worker",
        "preferred_worker_profile": None,
        "tool_profile": tool_profile,
        "allowed_tools": allowed_tools,
        "reuse_allowed": True,
        "dispatch_kind": "fresh",
        "source_task_id": None,
        "parent_task_id": None,
        "task_owner": "commander",
        "closure_policy": "close_when_validated",
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
        "theme_key": "langgraph-runtime",
        "title": f"Goal {goal_id}",
        "objective": f"Implement {goal_id}",
        "task_id": task_id,
        "worker_provider_id": worker_provider_id,
        "packet_template": packet_template,
    }


def make_objective_phase(
    phase_id: str,
    task_id: str,
    *,
    worker_provider_id: str = "local-script",
    provider_input: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "phase_id": phase_id,
        "phase_key": phase_id,
        "theme_key": "langgraph-runtime",
        "phase_title": f"Phase {phase_id}",
        "objective": f"Complete {phase_id}",
        "goals": [
            make_phase_goal(
                f"{phase_id}-goal-1",
                task_id,
                worker_provider_id=worker_provider_id,
                provider_input=provider_input,
            )
        ],
    }


def test_run_until_objective_handoff_continues_across_two_inline_phases(
    tmp_path: Path,
) -> None:
    task_card_path = tmp_path / "current_task_card.md"
    runtime_root = normalize_runtime_root(tmp_path / "runtime")
    write_task_card(task_card_path)

    create_objective_plan(
        runtime_root,
        objective_id="objective-m2",
        objective_key="langgraph-runtime",
        objective_title="LangGraph Milestone 2",
        objective="Keep going until the full objective is done.",
        phases=[
            make_objective_phase(
                "phase-1",
                "phase-1-task",
                provider_input={
                    "command": [str(PYTHON_EXE), "-c", "print('phase 1 ok')"],
                    "success_summary": "Phase 1 completed inline.",
                    "recommended_next_step": "Archive the task.",
                },
            ),
            make_objective_phase(
                "phase-2",
                "phase-2-task",
                provider_input={
                    "command": [str(PYTHON_EXE), "-c", "print('phase 2 ok')"],
                    "success_summary": "Phase 2 completed inline.",
                    "recommended_next_step": "Archive the task.",
                },
            ),
        ],
    )

    result = run_until_objective_handoff(
        thread_id="test-objective-inline",
        runtime_root=str(runtime_root),
        task_card_path=str(task_card_path),
        objective_id="objective-m2",
        checkpoint_db=str(tmp_path / "graph" / "checkpoints.sqlite"),
        max_objective_rounds=4,
        max_graph_rounds=8,
    )

    objective_plan = load_objective_plan(runtime_root, "objective-m2")

    assert result["driver_status"] == "stopped"
    assert result["stop_reason"] == "terminal"
    assert result["objective_round_count"] >= 1
    assert result["final_objective_summary"]["status"] == "completed"
    assert result["final_objective_summary"]["remaining_phase_count"] == 0
    assert result["final_handoff_result"]["final_state"]["task_archive"]["status"][
        "lifecycle_status"
    ] == "archived"
    assert [phase["status"] for phase in objective_plan["phases"]] == ["done", "done"]


def test_run_until_objective_handoff_stops_at_external_wait_boundary(
    tmp_path: Path,
) -> None:
    task_card_path = tmp_path / "current_task_card.md"
    runtime_root = normalize_runtime_root(tmp_path / "runtime")
    write_task_card(task_card_path)

    create_objective_plan(
        runtime_root,
        objective_id="objective-ext",
        objective_key="langgraph-runtime",
        objective_title="External wait objective",
        objective="Stop only at the true external wait boundary.",
        phases=[
            make_objective_phase(
                "phase-ext",
                "phase-ext-task",
                worker_provider_id="codex",
            )
        ],
    )

    result = run_until_objective_handoff(
        thread_id="test-objective-external",
        runtime_root=str(runtime_root),
        task_card_path=str(task_card_path),
        objective_id="objective-ext",
        checkpoint_db=str(tmp_path / "graph" / "checkpoints.sqlite"),
        max_objective_rounds=3,
        max_graph_rounds=4,
    )

    assert result["driver_status"] == "waiting_external_result"
    assert result["stop_reason"] == "wait_timeout_or_missing_report"
    assert result["final_objective_summary"]["status"] == "active"
    assert result["final_objective_summary"]["remaining_phase_count"] == 1
    assert result["final_handoff_result"]["final_state"]["worker_dispatch"]["status"] == "waiting_worker"
    assert "compaction_event" not in result["final_handoff_result"]
    assert result["compaction_event"]["source"] == "run_until_objective_handoff"
    assert result["compaction_event"]["objective_id"] == "objective-ext"

    paths = resolve_task_paths(runtime_root, "phase-ext-task")
    compaction_event = load_json(paths.compaction_event_path)

    assert compaction_event["event_id"] == result["compaction_event"]["event_id"]
    assert compaction_event["objective_id"] == "objective-ext"
    assert compaction_event["source"] == "run_until_objective_handoff"
    assert compaction_event["driver_status"] == "waiting_external_result"
    assert compaction_event["artifact"]["kind"] == "graph_handoff_payload"
