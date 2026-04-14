from __future__ import annotations

from pathlib import Path

from commander.transport.scripts.commander_bootstrap_current_objective import (
    bootstrap_current_objective,
    load_objective_template,
)
from commander.transport.scripts.commander_harness import normalize_runtime_root
from commander.transport.scripts.commander_objective_plan import (
    load_objective_plan,
    promote_next_objective_phase,
)
from commander.transport.scripts.commander_phase_plan import promote_next_phase_goal


def test_current_objective_template_bootstraps_runtime_backlog(tmp_path: Path) -> None:
    runtime_root = normalize_runtime_root(tmp_path / "runtime")

    payload = bootstrap_current_objective(runtime_root)

    assert payload["status"] == "created"
    summary = payload["objective_summary"]
    assert summary["objective_id"] == "objective-5-6-langgraph-runtime"
    assert summary["promotable_phase_id"] == "phase-5-6-host-runtime-integration"
    assert summary["remaining_phase_count"] == 4

    objective_plan = load_objective_plan(runtime_root, summary["objective_id"])
    assert [phase["status"] for phase in objective_plan["phases"]] == [
        "pending",
        "pending",
        "pending",
        "pending",
    ]


def test_current_objective_template_promotes_first_local_script_goal(
    tmp_path: Path,
) -> None:
    runtime_root = normalize_runtime_root(tmp_path / "runtime")
    bootstrap_current_objective(runtime_root)

    phase_promotion = promote_next_objective_phase(runtime_root)
    assert phase_promotion["status"] == "promoted"
    assert phase_promotion["phase_summary"]["phase_id"] == (
        "phase-5-6-host-runtime-integration"
    )

    goal_promotion = promote_next_phase_goal(runtime_root)
    assert goal_promotion["status"] == "promoted"
    assert goal_promotion["worker_provider_id"] == "local-script"

    task_packet = goal_promotion["worker_task_packet"]
    assert task_packet["task_id"] == "task-5-6-visible-host-smoke"
    assert task_packet["provider_input"]["command"][:4] == [
        ".\\.venv\\Scripts\\python.exe",
        "-m",
        "commander.transport.scripts.commander_host_control",
        "daemon-status",
    ]


def test_current_objective_bootstrap_is_idempotent_without_force(
    tmp_path: Path,
) -> None:
    runtime_root = normalize_runtime_root(tmp_path / "runtime")

    first = bootstrap_current_objective(runtime_root)
    second = bootstrap_current_objective(runtime_root)

    assert first["status"] == "created"
    assert second["status"] == "already_exists"
    assert second["objective_summary"]["objective_id"] == (
        "objective-5-6-langgraph-runtime"
    )


def test_current_objective_template_contains_full_stage_not_single_step() -> None:
    template = load_objective_template()

    assert len(template["phases"]) == 4
    phase_ids = {phase["phase_id"] for phase in template["phases"]}
    assert phase_ids == {
        "phase-5-6-host-runtime-integration",
        "phase-5-7-spec-kit-sdd",
        "phase-5-8-hermes-memory-feedback",
        "phase-5-9-provider-tool-governance",
    }
