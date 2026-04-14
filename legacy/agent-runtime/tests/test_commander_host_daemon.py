from __future__ import annotations

from pathlib import Path

from commander.transport.scripts.commander_harness import normalize_runtime_root
from commander.transport.scripts.commander_harness import resolve_task_paths
from commander.transport.scripts.commander_phase_plan import (
    create_phase_plan,
    promote_next_phase_goal,
)
from commander.transport.scripts.commander_host_control import build_host_control_snapshot
from commander.transport.scripts.commander_host_daemon import (
    HOST_DAEMON_STATUS_ATTENTION_REQUIRED,
    HOST_DAEMON_STATUS_IDLE,
    HOST_DAEMON_STATUS_WAITING_EXTERNAL,
    HOST_DAEMON_STATUS_WAITING_USER,
    build_host_daemon_summary,
    load_host_daemon_logs,
    process_host_daemon_commands_once,
    request_resume_host_daemon,
    request_stop_host_daemon,
    run_host_daemon_cycle,
    start_host_daemon,
)


def make_phase_goal(
    goal_id: str,
    task_id: str,
    *,
    worker_provider_id: str = "local-script",
    owned_paths: list[str] | None = None,
) -> dict[str, object]:
    goal_owned_paths = owned_paths or []
    return {
        "goal_id": goal_id,
        "theme_key": "langgraph-runtime",
        "title": f"Goal {goal_id}",
        "objective": f"Implement {goal_id}",
        "task_id": task_id,
        "worker_provider_id": worker_provider_id,
        "packet_template": {
            "must_read": ["README.md"],
            "bounds": ["commander only"],
            "validation": ["python -m pytest -q tests/test_commander_host_daemon.py"],
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


def test_run_host_daemon_cycle_tracks_waiting_external_result(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    start_host_daemon(
        runtime_root,
        spawn_fn=lambda _command, _cwd: 4321,
        wait_timeout_seconds=0.5,
        poll_interval_seconds=0.1,
        wait_sleep_seconds=0.25,
    )

    def fake_runner(**_kwargs: object) -> dict[str, object]:
        return {
            "driver_status": "waiting_external_result",
            "stop_reason": "wait_timeout_or_missing_report",
            "objective_id": "objective-1",
            "task_id": "task-1",
            "objective_round_count": 1,
            "final_handoff_result": {
                "driver_status": "waiting_external_result",
                "stop_reason": "wait_timeout_or_missing_report",
                "wait_monitor": {"wait_reason": "external_worker_running"},
            },
        }

    result = run_host_daemon_cycle(runtime_root, objective_runner=fake_runner)
    summary = build_host_daemon_summary(runtime_root)

    assert result["daemon_state"]["status"] == HOST_DAEMON_STATUS_WAITING_EXTERNAL
    assert summary["status"] == HOST_DAEMON_STATUS_WAITING_EXTERNAL
    assert summary["wait_context"]["wait_reason"] == "external_worker_running"
    assert result["sleep_seconds"] == 0.25


def test_run_host_daemon_cycle_preserves_auto_launch_wait_context(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    start_host_daemon(
        runtime_root,
        spawn_fn=lambda _command, _cwd: 4321,
        wait_timeout_seconds=0.5,
        poll_interval_seconds=0.1,
        wait_sleep_seconds=0.25,
    )

    def fake_runner(**_kwargs: object) -> dict[str, object]:
        return {
            "driver_status": "waiting_external_result",
            "stop_reason": "wait_timeout_or_missing_report",
            "objective_id": "objective-auto-launch",
            "task_id": "task-auto-launch",
            "objective_round_count": 1,
            "final_handoff_result": {
                "driver_status": "waiting_external_result",
                "stop_reason": "wait_timeout_or_missing_report",
                "wait_monitor": {
                    "wait_reason": "external_worker_running",
                    "auto_launch_supported": True,
                    "launch_status": "launched",
                    "launch_result": {"pid": 9876, "returncode": 0},
                    "launch_error": None,
                },
            },
        }

    result = run_host_daemon_cycle(runtime_root, objective_runner=fake_runner)
    summary = build_host_daemon_summary(runtime_root)
    snapshot = build_host_control_snapshot(runtime_root)

    assert result["daemon_state"]["status"] == HOST_DAEMON_STATUS_WAITING_EXTERNAL
    assert summary["wait_context"]["auto_launch_supported"] is True
    assert summary["wait_context"]["launch_status"] == "launched"
    assert summary["wait_context"]["launch_result"]["pid"] == 9876
    assert snapshot["host_daemon"]["wait_context"]["launch_status"] == "launched"


def test_run_host_daemon_cycle_prefers_active_phase_task_over_stale_runtime_task(
    tmp_path: Path,
) -> None:
    runtime_root = normalize_runtime_root(tmp_path / "runtime")
    create_phase_plan(
        runtime_root,
        phase_id="phase-m2",
        phase_key="langgraph-runtime",
        phase_title="Milestone 2",
        objective="Resolve the active phase task from the phase plan.",
        goals=[make_phase_goal("goal-1", "task-current-phase")],
    )
    promote_next_phase_goal(runtime_root, phase_id="phase-m2")
    start_host_daemon(
        runtime_root,
        task_id="task-stale-runtime",
        spawn_fn=lambda _command, _cwd: 2468,
        wait_timeout_seconds=0.1,
        poll_interval_seconds=0.05,
    )
    captured_kwargs: dict[str, object] = {}

    def fake_runner(**kwargs: object) -> dict[str, object]:
        captured_kwargs.update(kwargs)
        return {
            "driver_status": "waiting_external_result",
            "stop_reason": "wait_timeout_or_missing_report",
            "objective_id": None,
            "task_id": kwargs.get("task_id"),
            "objective_round_count": 1,
            "final_handoff_result": {
                "driver_status": "waiting_external_result",
                "stop_reason": "wait_timeout_or_missing_report",
                "wait_monitor": {"wait_reason": "external_worker_running"},
            },
        }

    result = run_host_daemon_cycle(runtime_root, objective_runner=fake_runner)
    summary = build_host_daemon_summary(runtime_root)

    assert captured_kwargs["task_id"] == "task-current-phase"
    assert result["daemon_state"]["runtime_config"]["task_id"] == "task-current-phase"
    assert summary["runtime_config"]["task_id"] == "task-current-phase"


def test_run_host_daemon_cycle_prefills_parallel_slots_while_waiting_external(
    tmp_path: Path,
) -> None:
    runtime_root = normalize_runtime_root(tmp_path / "runtime")
    create_phase_plan(
        runtime_root,
        phase_id="phase-m2",
        phase_key="langgraph-runtime",
        phase_title="Milestone 2",
        objective="Prefill an additional compatible goal while the first worker is waiting.",
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
        ],
    )
    promote_next_phase_goal(runtime_root, phase_id="phase-m2")
    start_host_daemon(
        runtime_root,
        spawn_fn=lambda _command, _cwd: 1357,
        wait_timeout_seconds=0.1,
        poll_interval_seconds=0.05,
        wait_sleep_seconds=0.25,
    )
    captured_kwargs: dict[str, object] = {}

    def fake_runner(**kwargs: object) -> dict[str, object]:
        captured_kwargs.update(kwargs)
        return {
            "driver_status": "waiting_external_result",
            "stop_reason": "wait_timeout_or_missing_report",
            "objective_id": None,
            "task_id": kwargs.get("task_id"),
            "objective_round_count": 1,
            "final_handoff_result": {
                "driver_status": "waiting_external_result",
                "stop_reason": "wait_timeout_or_missing_report",
                "wait_monitor": {"wait_reason": "external_worker_running"},
            },
        }

    result = run_host_daemon_cycle(runtime_root, objective_runner=fake_runner)
    summary = build_host_daemon_summary(runtime_root)
    snapshot = build_host_control_snapshot(runtime_root)
    phase_snapshot = snapshot["phase"]

    assert result["phase_prefill"]["status"] == "promoted_parallel_goals"
    assert result["phase_prefill"]["promoted_goal_ids"] == ["goal-2"]
    assert captured_kwargs["task_id"] == "task-goal-1"
    assert phase_snapshot["current_goal_ids"] == ["goal-1", "goal-2"]
    assert phase_snapshot["current_task_ids"] == ["task-goal-1", "task-goal-2"]
    assert phase_snapshot["active_goal_count"] == 2
    assert phase_snapshot["available_parallel_slots"] == 0
    assert resolve_task_paths(runtime_root, "task-goal-2").packet_path.exists()
    assert summary["status"] == HOST_DAEMON_STATUS_WAITING_EXTERNAL


def test_run_host_daemon_cycle_passes_resume_payload_and_waits_for_user(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    start_host_daemon(
        runtime_root,
        spawn_fn=lambda _command, _cwd: 1234,
    )
    request_resume_host_daemon(
        runtime_root,
        note="user answered",
        last_open_offer={"offer_id": "goal-1"},
        latest_user_reply_text="ok",
    )
    processed = process_host_daemon_commands_once(runtime_root)
    captured_kwargs: dict[str, object] = {}

    def fake_runner(**kwargs: object) -> dict[str, object]:
        captured_kwargs.update(kwargs)
        return {
            "driver_status": "stopped",
            "stop_reason": "user_handoff",
            "objective_id": "objective-2",
            "task_id": "task-2",
            "objective_round_count": 1,
            "final_handoff_result": {
                "driver_status": "stopped",
                "stop_reason": "user_handoff",
            },
        }

    result = run_host_daemon_cycle(runtime_root, objective_runner=fake_runner)
    summary = build_host_daemon_summary(runtime_root)

    assert processed["processed_command_count"] == 1
    assert captured_kwargs["latest_user_reply_text"] == "ok"
    assert captured_kwargs["last_open_offer"] == {"offer_id": "goal-1"}
    assert result["daemon_state"]["status"] == HOST_DAEMON_STATUS_WAITING_USER
    assert summary["status"] == HOST_DAEMON_STATUS_WAITING_USER


def test_run_host_daemon_cycle_tracks_idle_and_attention_states(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    start_host_daemon(
        runtime_root,
        spawn_fn=lambda _command, _cwd: 5678,
        idle_sleep_seconds=0.2,
        attention_sleep_seconds=0.4,
    )

    def idle_runner(**_kwargs: object) -> dict[str, object]:
        return {
            "driver_status": "stopped",
            "stop_reason": "terminal",
            "objective_id": None,
            "task_id": None,
            "objective_round_count": 1,
            "final_handoff_result": {
                "driver_status": "stopped",
                "stop_reason": "terminal",
            },
        }

    idle_result = run_host_daemon_cycle(runtime_root, objective_runner=idle_runner)
    assert idle_result["daemon_state"]["status"] == HOST_DAEMON_STATUS_IDLE
    assert idle_result["sleep_seconds"] == 0.2

    def attention_runner(**_kwargs: object) -> dict[str, object]:
        return {
            "driver_status": "paused_no_progress",
            "stop_reason": "commander_internal",
            "objective_id": "objective-3",
            "task_id": "task-3",
            "objective_round_count": 1,
            "final_handoff_result": {
                "driver_status": "paused_no_progress",
                "stop_reason": "commander_internal",
            },
        }

    attention_result = run_host_daemon_cycle(
        runtime_root,
        objective_runner=attention_runner,
    )
    summary = build_host_daemon_summary(runtime_root)

    assert attention_result["daemon_state"]["status"] == HOST_DAEMON_STATUS_ATTENTION_REQUIRED
    assert attention_result["sleep_seconds"] == 0.4
    assert summary["status"] == HOST_DAEMON_STATUS_ATTENTION_REQUIRED


def test_host_control_snapshot_surfaces_daemon_state_and_logs(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    start_host_daemon(
        runtime_root,
        spawn_fn=lambda _command, _cwd: 9999,
    )
    request_stop_host_daemon(runtime_root, reason="test stop")
    logs = load_host_daemon_logs(runtime_root, limit=10)
    snapshot = build_host_control_snapshot(runtime_root)

    assert snapshot["host_daemon"]["pid"] == 9999
    assert snapshot["host_daemon"]["pending_command_count"] == 1
    assert logs["line_count"] >= 2
    assert any(
        entry.get("message") == "Queued daemon command: stop"
        for entry in logs["entries"]
    )
