from __future__ import annotations

import json
import sys
from pathlib import Path

from commander.transport.scripts.commander_host_control import (
    build_host_control_snapshot,
    resume_host_waits,
    run_host_task,
)
from commander.transport.scripts.commander_host_runtime import create_host_session
from commander.transport.scripts.commander_objective_plan import create_objective_plan
from commander.transport.scripts.commander_phase_plan import create_phase_plan


PYTHON_EXE = Path(sys.executable)


def write_task_card(path: Path) -> None:
    path.write_text(
        "# Current Task Card\n\n## 5. Active Tasks\n\nNo active tasks.\n",
        encoding="utf-8",
    )


def test_build_host_control_snapshot_surfaces_runtime_layers(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    create_host_session(
        runtime_root,
        thread_id="thread-status",
        task_id="host-task",
        provider_id="codex",
        provider_label="Codex Worker Window",
        host_adapter_id="external-window",
        launch_prompt="launch host task",
        provider_notes=[],
        launch_bundle_paths={"packet_path": "packet.json"},
        dispatch_idempotency_key="dispatch-status",
        worker_id="warm-codex-host",
        worker_profile="code-worker",
        tool_profile="control_plane_safe_write",
        allowed_tools=["shell_command", "apply_patch"],
        forbidden_paths=["config/rag.yml"],
        owned_paths=["commander/graph"],
        reuse_allowed=True,
        dispatch_kind="fresh",
        closure_policy="close_when_validated",
    )
    create_phase_plan(
        runtime_root,
        phase_id="phase-host",
        phase_key="langgraph-runtime",
        phase_title="Host Phase",
        objective="Test host status snapshot.",
        goals=[
            {
                "goal_id": "phase-host-goal-1",
                "theme_key": "langgraph-runtime",
                "title": "Host phase goal",
                "objective": "Keep one phase goal pending for visibility.",
                "task_id": "phase-host-task",
                "worker_provider_id": "codex",
                "packet_template": {
                    "must_read": ["README.md"],
                    "bounds": ["commander only"],
                    "validation": ["pytest"],
                    "forbidden_paths": ["config/rag.yml"],
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
        ],
    )
    create_objective_plan(
        runtime_root,
        objective_id="objective-host",
        objective_key="langgraph-runtime",
        objective_title="Host Objective",
        objective="Test objective visibility.",
        phases=[
            {
                "phase_id": "phase-host-2",
                "phase_key": "langgraph-runtime",
                "theme_key": "langgraph-runtime",
                "phase_title": "Host Objective Phase",
                "objective": "Test phase visibility.",
                "goals": [],
            }
        ],
    )

    snapshot = build_host_control_snapshot(runtime_root, task_id="host-task")

    assert snapshot["host_runtime"]["session_count"] == 1
    assert snapshot["host_runtime"]["registry"]["active_session_count"] == 1
    assert snapshot["host_runtime"]["session_cards"][0]["worker_id"] == "warm-codex-host"
    assert snapshot["host_runtime"]["session_cards"][0]["owned_paths"] == ["commander/graph"]
    assert snapshot["objective"]["objective_id"] == "objective-host"
    assert snapshot["phase"]["phase_id"] == "phase-host"
    assert snapshot["tasks"] == []


def test_run_host_task_executes_local_script_packet_inline(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    task_card_path = tmp_path / "current_task_card.md"
    packet_path = tmp_path / "task-packet.json"
    write_task_card(task_card_path)
    packet = {
        "schema_version": "commander-harness-v1",
        "task_id": "host-control-inline-task",
        "title": "Host control inline task",
        "goal": "Exercise run_host_task via the visible host control entry.",
        "must_read": ["README.md"],
        "bounds": ["commander only"],
        "validation": ["python -m pytest -q tests/test_commander_host_control.py"],
        "forbidden_paths": ["config/rag.yml"],
        "worker_profile": "code-worker",
        "preferred_worker_profile": None,
        "tool_profile": "default",
        "allowed_tools": ["shell_command"],
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
        "status": "dispatched",
        "provider_input": {
            "command": [str(PYTHON_EXE), "-c", "print('host control ok')"],
            "success_summary": "Host control local-script completed inline.",
            "recommended_next_step": "Archive the task.",
        },
    }
    packet_path.write_text(
        json.dumps(packet, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    result = run_host_task(
        thread_id="test-host-control-inline",
        runtime_root=str(runtime_root),
        task_card_path=str(task_card_path),
        task_id="host-control-inline-task",
        checkpoint_db=str(tmp_path / "graph" / "checkpoints.sqlite"),
        packet_file=str(packet_path),
        worker_provider_id="local-script",
        max_rounds=4,
    )

    assert result["driver_status"] == "stopped"
    assert result["stop_reason"] == "terminal"
    assert result["final_state"]["worker_dispatch"]["status"] == "completed_inline"
    assert result["final_state"]["task_archive"]["status"]["lifecycle_status"] == "archived"


def test_build_host_control_snapshot_includes_wait_monitor_for_waiting_task(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    task_card_path = tmp_path / "current_task_card.md"
    packet_path = tmp_path / "waiting-task-packet.json"
    write_task_card(task_card_path)
    packet = {
        "schema_version": "commander-harness-v1",
        "task_id": "host-control-wait-task",
        "title": "Host control wait task",
        "goal": "Exercise visible wait diagnostics for an external worker.",
        "must_read": ["README.md"],
        "bounds": ["commander only"],
        "validation": ["python -m pytest -q tests/test_commander_host_control.py"],
        "forbidden_paths": ["config/rag.yml"],
        "worker_profile": "code-worker",
        "preferred_worker_profile": None,
        "tool_profile": "default",
        "allowed_tools": ["shell_command"],
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
        "status": "dispatched",
    }
    packet_path.write_text(
        json.dumps(packet, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    result = run_host_task(
        thread_id="test-host-control-waiting",
        runtime_root=str(runtime_root),
        task_card_path=str(task_card_path),
        task_id="host-control-wait-task",
        checkpoint_db=str(tmp_path / "graph" / "checkpoints.sqlite"),
        packet_file=str(packet_path),
        worker_provider_id="codex",
        max_rounds=4,
    )
    snapshot = build_host_control_snapshot(
        runtime_root,
        task_id="host-control-wait-task",
    )

    assert result["driver_status"] == "waiting_external_result"
    assert snapshot["waits"][0]["task_id"] == "host-control-wait-task"
    assert snapshot["waits"][0]["wait_reason"] == "external_worker_running"
    assert snapshot["waits"][0]["session_status"] == "waiting_worker"
    assert snapshot["wait_summary"]["wait_count"] == 1
    assert snapshot["wait_summary"]["provider_counts"]["codex"] == 1


def test_build_host_control_snapshot_surfaces_auto_launch_status(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    task_card_path = tmp_path / "current_task_card.md"
    packet_path = tmp_path / "auto-launch-task-packet.json"
    marker_path = tmp_path / "auto-launch-marker.txt"
    write_task_card(task_card_path)
    packet = {
        "schema_version": "commander-harness-v1",
        "task_id": "host-control-auto-launch-task",
        "title": "Host control auto launch task",
        "goal": "Surface auto launch state in host control snapshots.",
        "must_read": ["README.md"],
        "bounds": ["commander only"],
        "validation": ["python -m pytest -q tests/test_commander_host_control.py"],
        "forbidden_paths": ["config/rag.yml"],
        "worker_profile": "code-worker",
        "preferred_worker_profile": None,
        "tool_profile": "default",
        "allowed_tools": ["shell_command"],
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
        "status": "dispatched",
        "provider_input": {
            "launcher": {
                "command": [
                    str(PYTHON_EXE),
                    "-c",
                    (
                        "from pathlib import Path; "
                        f"Path({str(marker_path)!r}).write_text('launched', encoding='utf-8')"
                    ),
                ],
                "cwd": ".",
                "detached": False,
            }
        },
    }
    packet_path.write_text(
        json.dumps(packet, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    result = run_host_task(
        thread_id="test-host-control-auto-launch",
        runtime_root=str(runtime_root),
        task_card_path=str(task_card_path),
        task_id="host-control-auto-launch-task",
        checkpoint_db=str(tmp_path / "graph" / "checkpoints.sqlite"),
        packet_file=str(packet_path),
        worker_provider_id="codex",
        max_rounds=4,
    )
    snapshot = build_host_control_snapshot(
        runtime_root,
        task_id="host-control-auto-launch-task",
    )

    assert result["driver_status"] == "waiting_external_result"
    assert marker_path.read_text(encoding="utf-8") == "launched"
    assert snapshot["host_runtime"]["session_pool"]["auto_launch_enabled_count"] == 1
    assert snapshot["host_runtime"]["session_pool"]["failed_launch_count"] == 0
    assert snapshot["waits"][0]["auto_launch_supported"] is True
    assert snapshot["waits"][0]["launch_status"] == "launched"
    assert snapshot["waits"][0]["launch_result"]["returncode"] == 0


def test_build_host_control_snapshot_aggregates_parallel_waits(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    task_card_path = tmp_path / "current_task_card.md"
    write_task_card(task_card_path)

    for task_id in ("parallel-wait-a", "parallel-wait-b"):
        packet_path = tmp_path / f"{task_id}.json"
        packet = {
            "schema_version": "commander-harness-v1",
            "task_id": task_id,
            "title": f"Wait task {task_id}",
            "goal": "Exercise parallel wait visibility.",
            "must_read": ["README.md"],
            "bounds": ["commander only"],
            "validation": ["python -m pytest -q tests/test_commander_host_control.py"],
            "forbidden_paths": ["config/rag.yml"],
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
            "status": "dispatched",
        }
        packet_path.write_text(
            json.dumps(packet, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        result = run_host_task(
            thread_id=f"thread-{task_id}",
            runtime_root=str(runtime_root),
            task_card_path=str(task_card_path),
            task_id=task_id,
            checkpoint_db=str(tmp_path / "graph" / "checkpoints.sqlite"),
            packet_file=str(packet_path),
            worker_provider_id="codex",
            max_rounds=4,
        )
        assert result["driver_status"] == "waiting_external_result"

    snapshot = build_host_control_snapshot(runtime_root)

    assert snapshot["wait_summary"]["wait_count"] == 2
    assert snapshot["wait_summary"]["provider_counts"]["codex"] == 2
    assert {item["task_id"] for item in snapshot["waits"]} == {
        "parallel-wait-a",
        "parallel-wait-b",
    }


def test_run_host_task_passes_intent_binding_inputs(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    task_card_path = tmp_path / "current_task_card.md"
    packet_path = tmp_path / "intent-binding-task-packet.json"
    write_task_card(task_card_path)
    packet = {
        "schema_version": "commander-harness-v1",
        "task_id": "host-control-intent-task",
        "title": "Host control intent task",
        "goal": "Exercise host control passthrough for intent binding.",
        "must_read": ["README.md"],
        "bounds": ["commander only"],
        "validation": ["python -m pytest -q tests/test_commander_host_control.py"],
        "forbidden_paths": ["config/rag.yml"],
        "worker_profile": "code-worker",
        "preferred_worker_profile": None,
        "tool_profile": "default",
        "allowed_tools": ["shell_command"],
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
        "status": "dispatched",
        "provider_input": {
            "command": [str(PYTHON_EXE), "-c", "print('intent ok')"],
            "success_summary": "Intent passthrough local-script completed inline.",
            "recommended_next_step": "Archive the task.",
        },
    }
    packet_path.write_text(
        json.dumps(packet, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    result = run_host_task(
        thread_id="test-host-control-intent",
        runtime_root=str(runtime_root),
        task_card_path=str(task_card_path),
        task_id="host-control-intent-task",
        checkpoint_db=str(tmp_path / "graph" / "checkpoints.sqlite"),
        packet_file=str(packet_path),
        worker_provider_id="local-script",
        last_open_offer={
            "offer_id": "goal-intent",
            "summary": "Continue the next host-control goal",
            "proposed_action": "Run the host-control task",
        },
        latest_user_reply_text="可以",
        max_rounds=4,
    )

    assert result["driver_status"] == "stopped"
    assert result["final_state"]["intent_binding"]["offer_confirmed"] is True
    assert result["final_state"]["intent_binding"]["resolved_reply_target"] == "goal-intent"


def test_resume_host_waits_batches_visible_parallel_sessions(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    task_card_path = tmp_path / "current_task_card.md"
    write_task_card(task_card_path)

    for task_id in ("resume-wait-a", "resume-wait-b"):
        packet_path = tmp_path / f"{task_id}.json"
        packet = {
            "schema_version": "commander-harness-v1",
            "task_id": task_id,
            "title": f"Resume wait task {task_id}",
            "goal": "Exercise batch host wait resume.",
            "must_read": ["README.md"],
            "bounds": ["commander only"],
            "validation": ["python -m pytest -q tests/test_commander_host_control.py"],
            "forbidden_paths": ["config/rag.yml"],
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
            "status": "dispatched",
        }
        packet_path.write_text(
            json.dumps(packet, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        result = run_host_task(
            thread_id=f"thread-{task_id}",
            runtime_root=str(runtime_root),
            task_card_path=str(task_card_path),
            task_id=task_id,
            checkpoint_db=str(tmp_path / "graph" / "checkpoints.sqlite"),
            packet_file=str(packet_path),
            worker_provider_id="codex",
            max_rounds=4,
        )
        assert result["driver_status"] == "waiting_external_result"

    resume_payload = resume_host_waits(
        runtime_root=str(runtime_root),
        provider_id="codex",
        note="batch resume from host control",
    )
    snapshot = build_host_control_snapshot(runtime_root)

    assert resume_payload["resumed_session_count"] == 2
    assert snapshot["wait_summary"]["resume_requested_wait_count"] == 2
    assert {item["session_status"] for item in snapshot["waits"]} == {"resume_requested"}
