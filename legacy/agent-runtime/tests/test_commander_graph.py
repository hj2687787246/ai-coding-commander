from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
import pytest

import commander.graph.adapters.worker_providers.local_script as local_script_module
from commander.graph.adapters.worker_providers.base import WorkerLauncherPreset
from commander.graph.checkpoints import open_commander_checkpointer
from commander.graph.graph import build_commander_graph
from commander.graph.policies.launcher import LAUNCHER_PRESETS
from commander.graph.runners.resume import resume_once
from commander.graph.runners.run_until_handoff import run_until_handoff
from commander.graph.runners.run_once import build_config, run_once
from commander.graph.state import CommanderGraphState
from commander.transport.scripts.commander_dispatch import dispatch_task
from commander.transport.scripts.commander_harness import (
    build_task_worker_binding_summary,
    load_json,
    list_worker_slots,
    normalize_runtime_root,
    resolve_task_paths,
)
from commander.transport.scripts.commander_host_runtime import (
    ack_host_session_mailbox,
    append_host_session_mailbox_command,
    build_host_runtime_summary,
    read_host_session_mailbox_entries,
    release_host_session_for_reuse,
    retry_unacked_host_session_mailbox_commands,
)
from commander.transport.scripts.commander_phase_plan import (
    create_phase_plan,
    load_phase_plan,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON_EXE = Path(sys.executable)


def write_task_card(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")


def make_worker_task_packet(
    task_id: str = "worker-task-001",
    *,
    provider_input: dict[str, object] | None = None,
) -> dict[str, object]:
    packet: dict[str, object] = {
        "schema_version": "commander-harness-v1",
        "task_id": task_id,
        "title": "Graph dispatched worker task",
        "goal": "Exercise graph-native worker dispatch",
        "must_read": ["README.md"],
        "bounds": ["transport only"],
        "validation": ["python -m pytest -q tests/test_commander_graph.py"],
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
    if provider_input is not None:
        packet["provider_input"] = provider_input
    return packet


def make_worker_report(
    task_id: str,
    *,
    summary: str = "Worker completed the task.",
    changed_files: list[str] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": "commander-harness-v1",
        "task_id": task_id,
        "status": "done",
        "summary": summary,
        "changed_files": changed_files or ["commander/graph/graph.py"],
        "verification": [
            {
                "name": "pytest",
                "command": "python -m pytest -q tests/test_commander_graph.py",
                "result": "passed",
            }
        ],
        "commit": {"message": "Graph worker result"},
        "risks": [],
        "recommended_next_step": "Archive the task.",
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


def make_phase_goal(
    goal_id: str,
    task_id: str,
    *,
    theme_key: str = "langgraph-runtime",
    worker_provider_id: str = "local-script",
    provider_input: dict[str, object] | None = None,
) -> dict[str, object]:
    packet = make_worker_task_packet(task_id, provider_input=provider_input)
    if worker_provider_id == "local-script":
        packet["tool_profile"] = "default"
        packet["allowed_tools"] = ["shell_command"]
    packet_template_keys = (
        "must_read",
        "bounds",
        "validation",
        "forbidden_paths",
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
        "provider_input",
    )
    return {
        "goal_id": goal_id,
        "theme_key": theme_key,
        "title": f"Goal {goal_id}",
        "objective": f"Implement {goal_id}",
        "task_id": task_id,
        "worker_provider_id": worker_provider_id,
        "packet_template": {
            key: packet[key]
            for key in packet_template_keys
            if key in packet
        },
    }


def test_commander_graph_routes_active_task_to_internal_continuation(
    tmp_path: Path,
) -> None:
    task_card_path = tmp_path / "当前任务卡.md"
    write_task_card(
        task_card_path,
        "# 指挥官当前任务卡\n\n"
        "## 5. 当前活跃任务\n\n"
        "### `5.6 LangGraph 指挥官运行时项目化`\n\n"
        "- 当前状态：`active`\n",
    )

    result = run_once(
        thread_id="test-active-task",
        runtime_root=str(tmp_path / "runtime"),
        task_card_path=str(task_card_path),
    )

    assert result["route"] == "continue_internal"
    assert result["stop_allowed"] is False
    assert result["continuation_required"] is True
    assert result["continuation_mode"] == "commander_internal"
    assert result["stop_gate_report"]["outcome"] == "must_continue"
    assert result["next_actions"] == [
        "Continue the active commander task or dispatch the next non-overlapping worker slice."
    ]


def test_commander_graph_routes_no_active_work_to_delivery(tmp_path: Path) -> None:
    task_card_path = tmp_path / "当前任务卡.md"
    write_task_card(
        task_card_path,
        "# 指挥官当前任务卡\n\n## 5. 当前活跃任务\n\n当前无活跃任务。\n",
    )

    result = run_once(
        thread_id="test-no-active-task",
        runtime_root=str(tmp_path / "runtime"),
        task_card_path=str(task_card_path),
    )

    assert result["route"] == "deliver_result"
    assert result["stop_allowed"] is True
    assert result["continuation_required"] is False
    assert result["continuation_mode"] == "terminal"
    assert result["user_delivery"]["outcome"] == "no_active_work"
    assert result["user_delivery"]["continuation_required"] is False


def test_commander_graph_persists_state_by_thread_id(tmp_path: Path) -> None:
    task_card_path = tmp_path / "当前任务卡.md"
    write_task_card(
        task_card_path,
        "# 指挥官当前任务卡\n\n## 5. 当前活跃任务\n\n当前无活跃任务。\n",
    )
    checkpointer = InMemorySaver()
    graph = build_commander_graph(checkpointer=checkpointer)
    thread_id = "test-thread-persistence"
    state: CommanderGraphState = {
        "thread_id": thread_id,
        "runtime_root": str(tmp_path / "runtime"),
        "task_card_path": str(task_card_path),
    }
    result = graph.invoke(state, config=build_config(thread_id))
    persisted = graph.get_state(build_config(thread_id))

    assert result["thread_id"] == thread_id
    assert persisted.values["thread_id"] == thread_id
    assert persisted.values["route"] == "deliver_result"


def test_commander_graph_persists_state_across_sqlite_checkpointers(
    tmp_path: Path,
) -> None:
    task_card_path = tmp_path / "当前任务卡.md"
    write_task_card(
        task_card_path,
        "# 指挥官当前任务卡\n\n## 5. 当前活跃任务\n\n当前无活跃任务。\n",
    )
    thread_id = "test-sqlite-thread-persistence"
    checkpoint_db = tmp_path / "graph" / "checkpoints.sqlite"
    state: CommanderGraphState = {
        "thread_id": thread_id,
        "runtime_root": str(tmp_path / "runtime"),
        "task_card_path": str(task_card_path),
    }

    with open_commander_checkpointer(checkpoint_db=checkpoint_db) as checkpointer:
        graph = build_commander_graph(checkpointer=checkpointer)
        graph.invoke(state, config=build_config(thread_id))

    with open_commander_checkpointer(checkpoint_db=checkpoint_db) as checkpointer:
        graph = build_commander_graph(checkpointer=checkpointer)
        persisted = graph.get_state(build_config(thread_id))

    assert persisted.values["thread_id"] == thread_id
    assert persisted.values["route"] == "deliver_result"


def test_commander_graph_resume_reports_existing_checkpoint(tmp_path: Path) -> None:
    task_card_path = tmp_path / "当前任务卡.md"
    write_task_card(
        task_card_path,
        "# 指挥官当前任务卡\n\n## 5. 当前活跃任务\n\n当前无活跃任务。\n",
    )
    thread_id = "test-resume-reports-checkpoint"
    checkpoint_db = tmp_path / "graph" / "checkpoints.sqlite"

    run_once(
        thread_id=thread_id,
        runtime_root=str(tmp_path / "runtime"),
        task_card_path=str(task_card_path),
        checkpoint_db=str(checkpoint_db),
    )
    resumed = resume_once(
        thread_id=thread_id,
        runtime_root=str(tmp_path / "runtime"),
        task_card_path=str(task_card_path),
        checkpoint_db=str(checkpoint_db),
    )

    assert resumed["resume"]["had_checkpoint"] is True
    assert resumed["resume"]["previous_route"] == "deliver_result"
    assert resumed["route"] == "deliver_result"


def test_commander_graph_assigns_worker_owner_when_packet_is_present(
    tmp_path: Path,
) -> None:
    task_card_path = tmp_path / "当前任务卡.md"
    runtime_root = tmp_path / "runtime"
    write_task_card(
        task_card_path,
        "# 指挥官当前任务卡\n\n"
        "## 5. 当前活跃任务\n\n"
        "### `worker orchestration`\n\n"
        "- 当前状态：`active`\n",
    )

    result = run_once(
        thread_id="test-worker-assignment",
        runtime_root=str(runtime_root),
        task_card_path=str(task_card_path),
        checkpoint_db=str(tmp_path / "graph" / "checkpoints.sqlite"),
        worker_task_packet=make_worker_task_packet(),
        worker_provider_id="codex",
    )
    binding = build_task_worker_binding_summary(
        normalize_runtime_root(runtime_root), "worker-task-001"
    )

    assert result["route"] == "assign_worker"
    assert result["worker_orchestration"]["status"] == "assigned"
    assert result["worker_dispatch"]["status"] == "waiting_worker"
    assert result["worker_dispatch"]["provider_id"] == "codex"
    assert Path(result["worker_dispatch"]["dispatch_payload"]["packet_path"]).exists()
    assert binding["leased_worker_count"] == 1


def test_commander_graph_blocks_duplicate_worker_owner(tmp_path: Path) -> None:
    task_card_path = tmp_path / "当前任务卡.md"
    runtime_root = tmp_path / "runtime"
    write_task_card(
        task_card_path,
        "# 指挥官当前任务卡\n\n"
        "## 5. 当前活跃任务\n\n"
        "### `worker orchestration`\n\n"
        "- 当前状态：`active`\n",
    )

    run_once(
        thread_id="test-worker-assignment-first",
        runtime_root=str(runtime_root),
        task_card_path=str(task_card_path),
        checkpoint_db=str(tmp_path / "graph" / "checkpoints.sqlite"),
        worker_task_packet=make_worker_task_packet("duplicate-worker-task"),
        worker_provider_id="codex",
    )
    result = run_once(
        thread_id="test-worker-assignment-second",
        runtime_root=str(runtime_root),
        task_card_path=str(task_card_path),
        checkpoint_db=str(tmp_path / "graph" / "checkpoints.sqlite"),
        worker_task_packet=make_worker_task_packet("duplicate-worker-task"),
        worker_provider_id="codex",
    )
    binding = build_task_worker_binding_summary(
        normalize_runtime_root(runtime_root), "duplicate-worker-task"
    )

    assert result["route"] == "assign_worker"
    assert result["worker_orchestration"]["status"] == "blocked"
    assert result["worker_dispatch"]["status"] == "not_dispatched"
    assert binding["leased_worker_count"] == 1


def test_run_until_handoff_waits_on_existing_worker_lease(
    tmp_path: Path,
) -> None:
    task_card_path = tmp_path / "current_task_card.md"
    runtime_root = tmp_path / "runtime"
    write_task_card(
        task_card_path,
        "# Current Task Card\n\n## 5. Active Tasks\n\nNo active tasks.\n",
    )

    run_once(
        thread_id="test-existing-lease-first",
        runtime_root=str(runtime_root),
        task_card_path=str(task_card_path),
        task_id="existing-lease-task",
        checkpoint_db=str(tmp_path / "graph" / "checkpoints.sqlite"),
        worker_task_packet=make_worker_task_packet("existing-lease-task"),
        worker_provider_id="codex",
    )

    result = run_until_handoff(
        thread_id="test-existing-lease-second",
        runtime_root=str(runtime_root),
        task_card_path=str(task_card_path),
        task_id="existing-lease-task",
        checkpoint_db=str(tmp_path / "graph" / "checkpoints.sqlite"),
        worker_task_packet=make_worker_task_packet("existing-lease-task"),
        worker_provider_id="codex",
        max_rounds=4,
        wait_timeout_seconds=0.1,
        poll_interval_seconds=0.05,
    )

    assert result["driver_status"] == "waiting_external_result"
    assert result["final_state"]["worker_orchestration"]["status"] == "blocked"
    assert result["final_state"]["worker_dispatch"]["status"] == "not_dispatched"
    assert result["final_state"]["continuation_mode"] == "wait_external_result"


def test_commander_graph_ingests_worker_report_payload(tmp_path: Path) -> None:
    task_card_path = tmp_path / "当前任务卡.md"
    runtime_root = tmp_path / "runtime"
    write_task_card(
        task_card_path,
        "# 指挥官当前任务卡\n\n"
        "## 5. 当前活跃任务\n\n"
        "### `worker orchestration`\n\n"
        "- 当前状态：`active`\n",
    )

    run_once(
        thread_id="test-worker-dispatch-before-ingest",
        runtime_root=str(runtime_root),
        task_card_path=str(task_card_path),
        checkpoint_db=str(tmp_path / "graph" / "checkpoints.sqlite"),
        worker_task_packet=make_worker_task_packet("worker-ingest-task"),
        worker_provider_id="codex",
    )
    report_payload = {
        "schema_version": "commander-harness-v1",
        "task_id": "worker-ingest-task",
        "status": "done",
        "summary": "Worker completed the task.",
        "changed_files": ["commander/graph/graph.py"],
        "verification": [
            {
                "name": "pytest",
                "command": "python -m pytest -q tests/test_commander_graph.py",
                "result": "passed",
            }
        ],
        "commit": {"message": "Graph worker result"},
        "risks": [],
        "recommended_next_step": "Close the task.",
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

    result = run_once(
        thread_id="test-worker-ingest",
        runtime_root=str(runtime_root),
        task_card_path=str(task_card_path),
        checkpoint_db=str(tmp_path / "graph" / "checkpoints.sqlite"),
        worker_report_payload=report_payload,
    )
    paths = resolve_task_paths(
        normalize_runtime_root(runtime_root), "worker-ingest-task"
    )
    status = load_json(paths.status_path)

    assert result["route"] == "ingest_worker"
    assert result["worker_ingest"]["worker_status"] == "done"
    assert result["worker_ingest"]["host_session_updates"][0]["session_status"] == "closed"
    assert result["task_closure"]["status"]["lifecycle_status"] == "closed"
    assert result["task_archive"]["status"]["lifecycle_status"] == "archived"
    assert status["lifecycle_status"] == "archived"
    assert status["worker_status"] == "done"


def test_commander_graph_prioritizes_report_ingest_before_delivery(tmp_path: Path) -> None:
    task_card_path = tmp_path / "当前任务卡.md"
    runtime_root = tmp_path / "runtime"
    write_task_card(
        task_card_path,
        "# 指挥官当前任务卡\n\n## 5. 当前活跃任务\n\n当前无活跃任务。\n",
    )

    run_once(
        thread_id="test-prioritize-ingest-dispatch",
        runtime_root=str(runtime_root),
        task_card_path=str(task_card_path),
        checkpoint_db=str(tmp_path / "graph" / "checkpoints.sqlite"),
        worker_task_packet=make_worker_task_packet("prioritize-ingest-task"),
        worker_provider_id="codex",
    )
    report_payload = {
        "schema_version": "commander-harness-v1",
        "task_id": "prioritize-ingest-task",
        "status": "done",
        "summary": "Worker completed the task.",
        "changed_files": ["commander/graph/graph.py"],
        "verification": [
            {
                "name": "pytest",
                "command": "python -m pytest -q tests/test_commander_graph.py",
                "result": "passed",
            }
        ],
        "commit": {"message": "Graph worker result"},
        "risks": [],
        "recommended_next_step": "Archive the task.",
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

    result = run_once(
        thread_id="test-prioritize-ingest",
        runtime_root=str(runtime_root),
        task_card_path=str(task_card_path),
        task_id="prioritize-ingest-task",
        checkpoint_db=str(tmp_path / "graph" / "checkpoints.sqlite"),
        worker_report_payload=report_payload,
    )

    assert result["route"] == "ingest_worker"
    assert result["worker_ingest"]["worker_status"] == "done"
    assert result["task_archive"]["status"]["lifecycle_status"] == "archived"


def test_commander_graph_routes_ready_for_user_delivery_to_user_handoff(
    tmp_path: Path,
) -> None:
    task_card_path = tmp_path / "当前任务卡.md"
    runtime_root = tmp_path / "runtime"
    write_task_card(
        task_card_path,
        "# 指挥官当前任务卡\n\n"
        "## 5. 当前活跃任务\n\n"
        "### `worker orchestration`\n\n"
        "- 当前状态：`active`\n",
    )

    run_once(
        thread_id="test-user-handoff-dispatch",
        runtime_root=str(runtime_root),
        task_card_path=str(task_card_path),
        checkpoint_db=str(tmp_path / "graph" / "checkpoints.sqlite"),
        worker_task_packet=make_worker_task_packet("user-handoff-task"),
        worker_provider_id="codex",
    )
    report_payload = {
        "schema_version": "commander-harness-v1",
        "task_id": "user-handoff-task",
        "status": "done",
        "summary": "Worker completed the task and it is ready for the user.",
        "changed_files": ["commander/graph/graph.py"],
        "verification": [
            {
                "name": "pytest",
                "command": "python -m pytest -q tests/test_commander_graph.py",
                "result": "passed",
            }
        ],
        "commit": {"message": "Graph worker result"},
        "risks": [],
        "recommended_next_step": "Return the final result to the user.",
        "needs_commander_decision": False,
        "result_grade": "closed",
        "next_action_owner": "commander",
        "continuation_mode": "close",
        "decision_reason": None,
        "split_suggestion": None,
        "needs_user_decision": False,
        "user_decision_reason": None,
        "ready_for_user_delivery": True,
        "harness_metadata": {"is_dispatch_draft": False},
    }

    result = run_once(
        thread_id="test-user-handoff",
        runtime_root=str(runtime_root),
        task_card_path=str(task_card_path),
        task_id="user-handoff-task",
        checkpoint_db=str(tmp_path / "graph" / "checkpoints.sqlite"),
        worker_report_payload=report_payload,
    )

    assert result["route"] == "ingest_worker"
    assert result["user_delivery"]["outcome"] == "return_final_result"
    assert result["continuation_required"] is False
    assert result["continuation_mode"] == "user_handoff"


def test_run_until_handoff_stops_when_waiting_for_external_result(
    tmp_path: Path,
) -> None:
    task_card_path = tmp_path / "当前任务卡.md"
    runtime_root = normalize_runtime_root(tmp_path / "runtime")
    write_task_card(
        task_card_path,
        "# 指挥官当前任务卡\n\n## 5. 当前活跃任务\n\n当前无活跃任务。\n",
    )

    result = run_until_handoff(
        thread_id="test-run-until-waiting",
        runtime_root=str(runtime_root),
        task_card_path=str(task_card_path),
        task_id="waiting-driver-task",
        checkpoint_db=str(tmp_path / "graph" / "checkpoints.sqlite"),
        worker_task_packet=make_worker_task_packet("waiting-driver-task"),
        worker_provider_id="codex",
        max_rounds=4,
        wait_timeout_seconds=0.1,
        poll_interval_seconds=0.05,
    )

    assert result["driver_status"] == "waiting_external_result"
    assert result["wait_monitor"]["timed_out"] is True
    assert result["wait_monitor"]["session_status"] == "resume_requested"
    assert result["final_state"]["worker_dispatch"]["status"] == "waiting_worker"
    assert result["compaction_event"]["source"] == "run_until_handoff"
    assert result["compaction_event"]["resume_mode"] == "compaction_event"

    paths = resolve_task_paths(runtime_root, "waiting-driver-task")
    compaction_event = load_json(paths.compaction_event_path)
    checkpoint = load_json(paths.checkpoint_path)
    status_payload = load_json(paths.status_path)
    resume_anchor = load_json(paths.resume_anchor_path)

    assert compaction_event["event_id"] == result["compaction_event"]["event_id"]
    assert compaction_event["driver_status"] == "waiting_external_result"
    assert compaction_event["stop_reason"] == "wait_timeout_or_missing_report"
    assert Path(compaction_event["artifact"]["path"]).exists()
    assert checkpoint["compaction_event"]["event_id"] == compaction_event["event_id"]
    assert status_payload["compaction_event"]["event_id"] == compaction_event["event_id"]
    assert resume_anchor["compaction_event"]["event_id"] == compaction_event["event_id"]
    assert resume_anchor["read_order"][0] == str(paths.compaction_event_path)


def test_commander_graph_codex_provider_emits_external_launch_bundle(
    tmp_path: Path,
) -> None:
    task_card_path = tmp_path / "current_task_card.md"
    runtime_root = tmp_path / "runtime"
    write_task_card(
        task_card_path,
        "# Current Task Card\n\n## 5. Active Tasks\n\nNo active tasks.\n",
    )

    result = run_until_handoff(
        thread_id="test-codex-external-provider",
        runtime_root=str(runtime_root),
        task_card_path=str(task_card_path),
        task_id="codex-external-task",
        checkpoint_db=str(tmp_path / "graph" / "checkpoints.sqlite"),
        worker_task_packet=make_worker_task_packet("codex-external-task"),
        worker_provider_id="codex",
        max_rounds=4,
    )

    provider_execution = result["final_state"]["worker_dispatch"]["provider_execution"]
    host_runtime = build_host_runtime_summary(runtime_root, task_id="codex-external-task")
    host_session = provider_execution["dispatch_metadata"]["host_session"]

    assert result["driver_status"] == "waiting_external_result"
    assert result["stop_reason"] == "wait_timeout_or_missing_report"
    assert result["task_id"] == "codex-external-task"
    assert result["final_state"]["worker_dispatch"]["status"] == "waiting_worker"
    assert provider_execution["provider_id"] == "codex"
    assert provider_execution["status"] == "waiting_worker"
    assert provider_execution["dispatch_metadata"]["mode"] == "external_window"
    assert provider_execution["dispatch_metadata"]["host_adapter_id"] == "external-window"
    assert provider_execution["governance"]["tool_policy"]["write_intent"] is True
    assert provider_execution["governance"]["path_policy"]["forbidden_paths"] == [
        "config/rag.yml"
    ]
    assert provider_execution["governance"]["path_policy"]["write_scope_declared"] is False
    assert "context_bundle.json" in provider_execution["dispatch_metadata"]["launch_prompt"]
    assert "read_policy / summary_lines / paths" in provider_execution["dispatch_metadata"]["launch_prompt"]
    assert "tool_profile: control_plane_safe_write" in provider_execution["dispatch_metadata"]["launch_prompt"]
    assert "allowed_tools: apply_patch, shell_command" in provider_execution["dispatch_metadata"]["launch_prompt"]
    assert "forbidden_paths: config/rag.yml" in provider_execution["dispatch_metadata"]["launch_prompt"]
    assert "owned_paths: (none)" in provider_execution["dispatch_metadata"]["launch_prompt"]
    assert provider_execution["dispatch_metadata"]["launch_bundle"]["auto_launch_supported"] is False
    assert provider_execution["dispatch_metadata"]["launch_bundle"]["launch_mode"] == "bundle_only"
    assert (
        provider_execution["dispatch_metadata"]["launch_bundle"]["tool_profile"]
        == "control_plane_safe_write"
    )
    assert provider_execution["dispatch_metadata"]["launch_bundle"]["allowed_tools"] == [
        "apply_patch",
        "shell_command",
    ]
    assert provider_execution["dispatch_metadata"]["launch_bundle"]["forbidden_paths"] == [
        "config/rag.yml"
    ]
    assert provider_execution["dispatch_metadata"]["launch_bundle"]["owned_paths"] == []
    assert (
        provider_execution["dispatch_metadata"]["launch_bundle"]["governance"][
            "tool_policy"
        ]["requested_tools"]
        == ["apply_patch", "shell_command"]
    )
    assert (
        provider_execution["dispatch_metadata"]["launch_bundle"]["governance"][
            "path_policy"
        ]["protected_paths_declared"]
        is True
    )
    assert Path(
        provider_execution["dispatch_metadata"]["context_bundle_path"]
    ).exists()
    assert "worker_brief.md" in provider_execution["dispatch_metadata"]["launch_prompt"]
    assert "worker_report.json" in provider_execution["dispatch_metadata"]["launch_prompt"]
    assert isinstance(host_session["session_id"], str) and host_session["session_id"]
    assert host_session["session_status"] == "waiting_worker"
    assert host_session["launch_bundle"]["launch_status"] == "ready"
    assert host_session["launch_bundle"]["tool_profile"] == "control_plane_safe_write"
    assert host_session["launch_bundle"]["forbidden_paths"] == ["config/rag.yml"]
    assert (
        host_session["session_card"]["governance"]["tool_policy"]["requested_tools"]
        == ["apply_patch", "shell_command"]
    )
    assert (
        host_session["session_card"]["governance"]["path_policy"][
            "protected_paths_declared"
        ]
        is True
    )
    assert host_runtime["session_count"] == 1
    assert host_runtime["registry"]["active_session_count"] == 1


def test_commander_graph_codex_provider_can_auto_launch_with_explicit_launcher(
    tmp_path: Path,
) -> None:
    task_card_path = tmp_path / "current_task_card.md"
    runtime_root = tmp_path / "runtime"
    marker_path = tmp_path / "auto-launch-marker.txt"
    write_task_card(
        task_card_path,
        "# Current Task Card\n\n## 5. Active Tasks\n\nNo active tasks.\n",
    )
    provider_input = {
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
    }

    result = run_until_handoff(
        thread_id="test-codex-auto-launch",
        runtime_root=str(runtime_root),
        task_card_path=str(task_card_path),
        task_id="codex-auto-launch-task",
        checkpoint_db=str(tmp_path / "graph" / "checkpoints.sqlite"),
        worker_task_packet=make_worker_task_packet(
            "codex-auto-launch-task",
            provider_input=provider_input,
        ),
        worker_provider_id="codex",
        max_rounds=4,
    )

    provider_execution = result["final_state"]["worker_dispatch"]["provider_execution"]
    host_session = provider_execution["dispatch_metadata"]["host_session"]
    launch_bundle = provider_execution["dispatch_metadata"]["launch_bundle"]

    assert result["driver_status"] == "waiting_external_result"
    assert provider_execution["status"] == "waiting_worker"
    assert marker_path.read_text(encoding="utf-8") == "launched"
    assert launch_bundle["auto_launch_supported"] is True
    assert launch_bundle["launch_mode"] == "auto_launch"
    assert launch_bundle["launch_status"] == "launched"
    assert launch_bundle["launcher"]["detached"] is False
    assert launch_bundle["launch_result"]["returncode"] == 0
    assert host_session["session_status"] == "waiting_worker"
    assert host_session["launch_bundle"]["launch_status"] == "launched"
    assert host_session["session_card"]["launch_status"] == "launched"


def test_commander_graph_codex_provider_can_auto_launch_with_preset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_card_path = tmp_path / "current_task_card.md"
    runtime_root = tmp_path / "runtime"
    marker_path = tmp_path / "preset-auto-launch-marker.txt"
    write_task_card(
        task_card_path,
        "# Current Task Card\n\n## 5. Active Tasks\n\nNo active tasks.\n",
    )
    monkeypatch.setitem(
        LAUNCHER_PRESETS,
        "codex-cli",
        WorkerLauncherPreset(
            preset_id="codex-cli",
            label="Codex CLI",
            command=(str(PYTHON_EXE),),
            detached=False,
            notes=("Test override preset.",),
        ),
    )
    provider_input = {
        "launcher": {
            "preset_id": "codex-cli",
            "args": [
                "-c",
                (
                    "from pathlib import Path; "
                    f"Path({str(marker_path)!r}).write_text('preset-launched', encoding='utf-8')"
                ),
            ],
            "cwd": ".",
            "detached": False,
        }
    }

    result = run_until_handoff(
        thread_id="test-codex-preset-auto-launch",
        runtime_root=str(runtime_root),
        task_card_path=str(task_card_path),
        task_id="codex-preset-auto-launch-task",
        checkpoint_db=str(tmp_path / "graph" / "checkpoints.sqlite"),
        worker_task_packet=make_worker_task_packet(
            "codex-preset-auto-launch-task",
            provider_input=provider_input,
        ),
        worker_provider_id="codex",
        max_rounds=4,
    )

    provider_execution = result["final_state"]["worker_dispatch"]["provider_execution"]
    host_session = provider_execution["dispatch_metadata"]["host_session"]
    launch_bundle = provider_execution["dispatch_metadata"]["launch_bundle"]

    assert result["driver_status"] == "waiting_external_result"
    assert provider_execution["status"] == "waiting_worker"
    assert marker_path.read_text(encoding="utf-8") == "preset-launched"
    assert launch_bundle["launcher"]["preset_id"] == "codex-cli"
    assert launch_bundle["launch_status"] == "launched"
    assert launch_bundle["launch_result"]["returncode"] == 0
    assert host_session["session_card"]["launch_status"] == "launched"


def test_commander_graph_codex_provider_blocks_when_auto_launch_fails(
    tmp_path: Path,
) -> None:
    task_card_path = tmp_path / "current_task_card.md"
    runtime_root = tmp_path / "runtime"
    write_task_card(
        task_card_path,
        "# Current Task Card\n\n## 5. Active Tasks\n\nNo active tasks.\n",
    )
    provider_input = {
        "launcher": {
            "command": ["definitely-not-a-real-launcher-command-for-test"],
            "cwd": ".",
            "detached": False,
        }
    }

    result = run_once(
        thread_id="test-codex-auto-launch-fails",
        runtime_root=str(runtime_root),
        task_card_path=str(task_card_path),
        checkpoint_db=str(tmp_path / "graph" / "checkpoints.sqlite"),
        worker_task_packet=make_worker_task_packet(
            "codex-auto-launch-fail-task",
            provider_input=provider_input,
        ),
        worker_provider_id="codex",
    )

    provider_execution = result["worker_dispatch"]["provider_execution"]
    launch_bundle = provider_execution["dispatch_metadata"]["launch_bundle"]
    host_session = provider_execution["dispatch_metadata"]["host_session"]

    assert result["worker_dispatch"]["status"] == "blocked"
    assert result["continuation_required"] is True
    assert result["continuation_mode"] == "commander_internal"
    assert provider_execution["status"] == "blocked"
    assert launch_bundle["launch_status"] == "failed"
    assert "error" in launch_bundle["launch_result"]
    assert host_session["session_status"] == "failed"
    assert host_session["session_card"]["launch_status"] == "failed"


def test_commander_graph_codex_provider_blocks_when_launcher_preset_is_invalid(
    tmp_path: Path,
) -> None:
    task_card_path = tmp_path / "current_task_card.md"
    runtime_root = tmp_path / "runtime"
    write_task_card(
        task_card_path,
        "# Current Task Card\n\n## 5. Active Tasks\n\nNo active tasks.\n",
    )
    provider_input = {
        "launcher": {
            "preset_id": "claude-code-cli",
        }
    }

    result = run_once(
        thread_id="test-codex-launcher-preset-invalid",
        runtime_root=str(runtime_root),
        task_card_path=str(task_card_path),
        checkpoint_db=str(tmp_path / "graph" / "checkpoints.sqlite"),
        worker_task_packet=make_worker_task_packet(
            "codex-launcher-preset-invalid-task",
            provider_input=provider_input,
        ),
        worker_provider_id="codex",
    )

    provider_execution = result["worker_dispatch"]["provider_execution"]

    assert result["worker_dispatch"]["status"] == "blocked"
    assert result["continuation_required"] is True
    assert result["continuation_mode"] == "commander_internal"
    assert provider_execution["status"] == "blocked"
    assert "does not support launcher preset" in provider_execution["dispatch_metadata"]["launcher_error"]


def test_run_until_handoff_auto_ingests_and_archives_when_report_exists(
    tmp_path: Path,
) -> None:
    task_card_path = tmp_path / "当前任务卡.md"
    runtime_root = tmp_path / "runtime"
    write_task_card(
        task_card_path,
        "# 指挥官当前任务卡\n\n## 5. 当前活跃任务\n\n当前无活跃任务。\n",
    )

    run_once(
        thread_id="test-driver-dispatch-before-resume",
        runtime_root=str(runtime_root),
        task_card_path=str(task_card_path),
        checkpoint_db=str(tmp_path / "graph" / "checkpoints.sqlite"),
        worker_task_packet=make_worker_task_packet("driver-report-task"),
        worker_provider_id="codex",
    )
    report_payload = {
        "schema_version": "commander-harness-v1",
        "task_id": "driver-report-task",
        "status": "done",
        "summary": "Worker completed the task.",
        "changed_files": ["commander/graph/graph.py"],
        "verification": [
            {
                "name": "pytest",
                "command": "python -m pytest -q tests/test_commander_graph.py",
                "result": "passed",
            }
        ],
        "commit": {"message": "Graph worker result"},
        "risks": [],
        "recommended_next_step": "Archive the task.",
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
    report_path = resolve_task_paths(
        normalize_runtime_root(runtime_root), "driver-report-task"
    ).report_path
    report_path.write_text(
        json.dumps(report_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    result = run_until_handoff(
        thread_id="test-driver-ingest-existing-report",
        runtime_root=str(runtime_root),
        task_card_path=str(task_card_path),
        task_id="driver-report-task",
        checkpoint_db=str(tmp_path / "graph" / "checkpoints.sqlite"),
        max_rounds=4,
        wait_timeout_seconds=0.1,
        poll_interval_seconds=0.1,
    )

    assert result["driver_status"] == "stopped"
    assert result["stop_reason"] == "terminal"
    assert result["final_state"]["task_archive"]["status"]["lifecycle_status"] == "archived"
    assert (
        result["final_state"]["worker_ingest"]["host_session_updates"][0]["session_status"]
        == "closed"
    )


def test_run_until_handoff_auto_ingests_worker_report_json(
    tmp_path: Path,
) -> None:
    task_card_path = tmp_path / "current_task_card.md"
    runtime_root = tmp_path / "runtime"
    write_task_card(
        task_card_path,
        "# Current Task Card\n\n## 5. Active Tasks\n\nNo active tasks.\n",
    )

    run_once(
        thread_id="test-driver-dispatch-before-worker-report",
        runtime_root=str(runtime_root),
        task_card_path=str(task_card_path),
        checkpoint_db=str(tmp_path / "graph" / "checkpoints.sqlite"),
        worker_task_packet=make_worker_task_packet("driver-worker-report-task"),
        worker_provider_id="codex",
    )
    worker_report_payload = {
        "schema_version": "commander-harness-v1",
        "task_id": "driver-worker-report-task",
        "status": "done",
        "summary": "Worker completed the task through worker_report.json.",
        "changed_files": ["commander/graph/graph.py"],
        "verification": [
            {
                "name": "pytest",
                "command": "python -m pytest -q tests/test_commander_graph.py",
                "result": "passed",
            }
        ],
        "commit": {"message": "Graph worker report draft"},
        "risks": [],
        "recommended_next_step": "Archive the task.",
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
    task_paths = resolve_task_paths(
        normalize_runtime_root(runtime_root), "driver-worker-report-task"
    )
    task_paths.worker_report_path.write_text(
        json.dumps(worker_report_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    result = run_until_handoff(
        thread_id="test-driver-ingest-worker-report",
        runtime_root=str(runtime_root),
        task_card_path=str(task_card_path),
        task_id="driver-worker-report-task",
        checkpoint_db=str(tmp_path / "graph" / "checkpoints.sqlite"),
        max_rounds=4,
        wait_timeout_seconds=0.1,
        poll_interval_seconds=0.05,
    )

    assert result["driver_status"] == "stopped"
    assert result["stop_reason"] == "terminal"
    assert result["final_state"]["worker_ingest"]["worker_status"] == "done"
    assert result["final_state"]["task_archive"]["status"]["lifecycle_status"] == "archived"


def test_commander_graph_local_script_provider_runs_inline_and_archives(
    tmp_path: Path,
) -> None:
    task_card_path = tmp_path / "当前任务卡.md"
    runtime_root = tmp_path / "runtime"
    write_task_card(
        task_card_path,
        "# 指挥官当前任务卡\n\n## 5. 当前活跃任务\n\n当前无活跃任务。\n",
    )

    provider_input = {
        "command": [
            str(PYTHON_EXE),
            "-c",
            "print('local-script provider ok')",
        ],
        "success_summary": "Local script provider completed inline.",
        "recommended_next_step": "Archive the task.",
    }
    result = run_until_handoff(
        thread_id="test-local-script-inline",
        runtime_root=str(runtime_root),
        task_card_path=str(task_card_path),
        task_id="local-script-inline-task",
        checkpoint_db=str(tmp_path / "graph" / "checkpoints.sqlite"),
        worker_task_packet={
            **make_worker_task_packet(
                "local-script-inline-task",
                provider_input=provider_input,
            ),
            "tool_profile": "default",
            "allowed_tools": ["shell_command"],
        },
        worker_provider_id="local-script",
        max_rounds=4,
    )

    assert result["driver_status"] == "stopped"
    assert result["final_state"]["worker_dispatch"]["status"] == "completed_inline"
    assert result["final_state"]["worker_ingest"]["worker_status"] == "done"
    assert result["final_state"]["task_archive"]["status"]["lifecycle_status"] == "archived"


def test_commander_graph_filters_inline_provider_result_before_ingest(
    tmp_path: Path,
) -> None:
    task_card_path = tmp_path / "当前任务卡.md"
    runtime_root = tmp_path / "runtime"
    write_task_card(
        task_card_path,
        "# 指挥官当前任务卡\n\n## 5. 当前活跃任务\n\n当前无活跃任务。\n",
    )

    provider_input = {
        "command": [
            str(PYTHON_EXE),
            "-c",
            "print('local-script provider ok')",
        ],
        "changed_files": ["docs/provider-result.md"],
        "success_summary": "Local script provider reported an unsafe change.",
        "recommended_next_step": "Archive the task.",
    }
    result = run_once(
        thread_id="test-local-script-result-filter",
        runtime_root=str(runtime_root),
        task_card_path=str(task_card_path),
        task_id="local-script-result-filter-task",
        checkpoint_db=str(tmp_path / "graph" / "checkpoints.sqlite"),
        worker_task_packet={
            **make_worker_task_packet(
                "local-script-result-filter-task",
                provider_input=provider_input,
            ),
            "tool_profile": "default",
            "allowed_tools": ["shell_command"],
        },
        worker_provider_id="local-script",
    )

    assert result["worker_dispatch"]["status"] == "blocked"
    assert result["worker_dispatch"]["reason"] == "provider_result_governance_rejected"
    assert result["worker_report_payload"] is None
    assert result["continuation_required"] is True
    assert result["worker_dispatch"]["result_post_check"]["write_intent"] is False
    assert result["worker_dispatch"]["result_post_check"]["forbidden_hit_count"] == 0
    assert any(
        "read-only governance reported changed_files" in item
        for item in result["worker_dispatch"]["violations"]
    )


def test_local_script_detects_unreported_repo_changes_before_ingest(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fake_project = tmp_path / "fake_project"
    fake_project.mkdir()
    subprocess.run(["git", "init"], cwd=fake_project, check=True, capture_output=True)
    monkeypatch.setattr(local_script_module, "PROJECT_ROOT", fake_project)
    task_card_path = tmp_path / "当前任务卡.md"
    runtime_root = tmp_path / "runtime"
    write_task_card(
        task_card_path,
        "# 指挥官当前任务卡\n\n## 5. 当前活跃任务\n\n当前无活跃任务。\n",
    )

    provider_input = {
        "command": [
            str(PYTHON_EXE),
            "-c",
            "from pathlib import Path; "
            "Path('config').mkdir(exist_ok=True); "
            "Path('config/rag.yml').write_text('unsafe', encoding='utf-8')",
        ],
        "success_summary": "Local script provider changed a forbidden file.",
        "recommended_next_step": "Archive the task.",
    }
    result = run_once(
        thread_id="test-local-script-detects-unreported-change",
        runtime_root=str(runtime_root),
        task_card_path=str(task_card_path),
        task_id="local-script-detects-unreported-change-task",
        checkpoint_db=str(tmp_path / "graph" / "checkpoints.sqlite"),
        worker_task_packet={
            **make_worker_task_packet(
                "local-script-detects-unreported-change-task",
                provider_input=provider_input,
            ),
            "tool_profile": "default",
            "allowed_tools": ["shell_command"],
        },
        worker_provider_id="local-script",
    )

    post_check = result["worker_dispatch"]["result_post_check"]
    provider_execution = result["worker_dispatch"]["provider_execution"]
    assert result["worker_dispatch"]["status"] == "blocked"
    assert result["worker_dispatch"]["reason"] == "provider_result_governance_rejected"
    assert "config/rag.yml" in provider_execution["dispatch_metadata"][
        "detected_changed_files"
    ]
    assert "config/rag.yml" in post_check["changed_files"]
    assert post_check["forbidden_hit_count"] == 1


def test_commander_graph_allows_two_non_overlapping_codex_dispatches(
    tmp_path: Path,
) -> None:
    task_card_path = tmp_path / "current_task_card.md"
    runtime_root = normalize_runtime_root(tmp_path / "runtime")
    write_task_card(
        task_card_path,
        "# Current Task Card\n\n## 5. Active Tasks\n\nNo active tasks.\n",
    )

    first = run_once(
        thread_id="test-codex-task-a",
        runtime_root=str(runtime_root),
        task_card_path=str(task_card_path),
        task_id="codex-task-a",
        checkpoint_db=str(tmp_path / "graph" / "checkpoints.sqlite"),
        worker_task_packet=make_worker_task_packet("codex-task-a"),
        worker_provider_id="codex",
    )
    second = run_once(
        thread_id="test-codex-task-b",
        runtime_root=str(runtime_root),
        task_card_path=str(task_card_path),
        task_id="codex-task-b",
        checkpoint_db=str(tmp_path / "graph" / "checkpoints.sqlite"),
        worker_task_packet=make_worker_task_packet("codex-task-b"),
        worker_provider_id="codex",
    )

    slots = [slot for slot in list_worker_slots(runtime_root) if slot["state"] == "busy"]
    binding_a = build_task_worker_binding_summary(runtime_root, "codex-task-a")
    binding_b = build_task_worker_binding_summary(runtime_root, "codex-task-b")

    assert first["worker_dispatch"]["status"] == "waiting_worker"
    assert second["worker_dispatch"]["status"] == "waiting_worker"
    assert len(slots) == 2
    assert binding_a["binding_health"] == "healthy"
    assert binding_b["binding_health"] == "healthy"
    assert binding_a["leased_worker_count"] == 1
    assert binding_b["leased_worker_count"] == 1


def test_commander_graph_multi_worker_e2e_reuses_mailbox_and_closes(
    tmp_path: Path,
) -> None:
    task_card_path = tmp_path / "current_task_card.md"
    runtime_root = normalize_runtime_root(tmp_path / "runtime")
    checkpoint_db = tmp_path / "graph" / "checkpoints.sqlite"
    write_task_card(
        task_card_path,
        "# Current Task Card\n\n## 5. Active Tasks\n\nNo active tasks.\n",
    )

    code_a_packet = {
        **make_worker_task_packet("multi-code-a"),
        "owned_paths": ["commander/graph/lane-a"],
    }
    code_b_packet = {
        **make_worker_task_packet("multi-code-b"),
        "owned_paths": ["commander/graph/lane-b"],
    }
    verifier_packet = {
        **make_worker_task_packet(
            "multi-verifier",
            provider_input={
                "command": [
                    str(PYTHON_EXE),
                    "-c",
                    "print('multi worker verifier ok')",
                ],
                "success_summary": "Verifier lane completed inline.",
                "recommended_next_step": "Archive the verifier task.",
            },
        ),
        "tool_profile": "default",
        "allowed_tools": ["shell_command"],
        "owned_paths": ["tests/multi-worker-verifier"],
    }

    first = run_once(
        thread_id="multi-code-a-dispatch",
        runtime_root=str(runtime_root),
        task_card_path=str(task_card_path),
        task_id="multi-code-a",
        checkpoint_db=str(checkpoint_db),
        worker_task_packet=code_a_packet,
        worker_provider_id="codex",
    )
    second = run_once(
        thread_id="multi-code-b-dispatch",
        runtime_root=str(runtime_root),
        task_card_path=str(task_card_path),
        task_id="multi-code-b",
        checkpoint_db=str(checkpoint_db),
        worker_task_packet=code_b_packet,
        worker_provider_id="codex",
    )
    verifier = run_until_handoff(
        thread_id="multi-verifier-inline",
        runtime_root=str(runtime_root),
        task_card_path=str(task_card_path),
        task_id="multi-verifier",
        checkpoint_db=str(checkpoint_db),
        worker_task_packet=verifier_packet,
        worker_provider_id="local-script",
        max_rounds=4,
    )

    summary_after_dispatch = build_host_runtime_summary(runtime_root)
    code_a_session = build_host_runtime_summary(
        runtime_root,
        task_id="multi-code-a",
    )["sessions"][0]
    code_b_session = build_host_runtime_summary(
        runtime_root,
        task_id="multi-code-b",
    )["sessions"][0]

    inspect_command = append_host_session_mailbox_command(
        runtime_root,
        code_b_session["session_id"],
        command_type="inspect_session",
        command_payload={"reason": "e2e_progress_check"},
        note="inspect the still-waiting worker",
    )
    retry_payload = retry_unacked_host_session_mailbox_commands(
        runtime_root,
        code_b_session["session_id"],
        max_retries=2,
        note="retry the unacked inspect command",
    )
    unacked_retry_commands = read_host_session_mailbox_entries(
        runtime_root,
        code_b_session["session_id"],
        commands_only=True,
        unacked_only=True,
    )
    ack_payload = ack_host_session_mailbox(
        runtime_root,
        code_b_session["session_id"],
        through_sequence=unacked_retry_commands["last_sequence"],
        note="worker consumed retried inspect command",
    )

    code_a_paths = resolve_task_paths(runtime_root, "multi-code-a")
    code_a_paths.worker_report_path.write_text(
        json.dumps(
            make_worker_report(
                "multi-code-a",
                summary="Code worker A completed and can release its session.",
                changed_files=["commander/graph/lane-a/impl.py"],
            ),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    code_a_ingest = run_until_handoff(
        thread_id="multi-code-a-ingest",
        runtime_root=str(runtime_root),
        task_card_path=str(task_card_path),
        task_id="multi-code-a",
        checkpoint_db=str(checkpoint_db),
        max_rounds=4,
        wait_timeout_seconds=0.1,
        poll_interval_seconds=0.05,
    )
    released = release_host_session_for_reuse(
        runtime_root,
        code_a_session["session_id"],
        reason="e2e_reuse_after_ingest",
        last_report_path=str(code_a_paths.report_path),
    )

    code_c_packet = {
        **make_worker_task_packet("multi-code-c"),
        "owned_paths": ["commander/graph/lane-c"],
    }
    reused = run_once(
        thread_id="multi-code-c-dispatch",
        runtime_root=str(runtime_root),
        task_card_path=str(task_card_path),
        task_id="multi-code-c",
        checkpoint_db=str(checkpoint_db),
        worker_task_packet=code_c_packet,
        worker_provider_id="codex",
    )
    code_c_session = build_host_runtime_summary(
        runtime_root,
        task_id="multi-code-c",
    )["sessions"][0]
    code_c_commands = read_host_session_mailbox_entries(
        runtime_root,
        code_c_session["session_id"],
        commands_only=True,
        unacked_only=True,
    )

    for task_id in ("multi-code-b", "multi-code-c"):
        task_paths = resolve_task_paths(runtime_root, task_id)
        task_paths.worker_report_path.write_text(
            json.dumps(
                make_worker_report(
                    task_id,
                    summary=f"{task_id} completed after E2E mailbox checks.",
                    changed_files=[
                        f"commander/graph/{'lane-b' if task_id == 'multi-code-b' else 'lane-c'}/impl.py"
                    ],
                ),
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        result = run_until_handoff(
            thread_id=f"{task_id}-ingest",
            runtime_root=str(runtime_root),
            task_card_path=str(task_card_path),
            task_id=task_id,
            checkpoint_db=str(checkpoint_db),
            max_rounds=4,
            wait_timeout_seconds=0.1,
            poll_interval_seconds=0.05,
        )
        assert result["driver_status"] == "stopped"
        assert result["final_state"]["worker_ingest"]["worker_status"] == "done"
        task_session = build_host_runtime_summary(runtime_root, task_id=task_id)[
            "sessions"
        ][0]
        assert task_session["session_status"] == "closed"
        assert result["final_state"]["task_archive"]["status"]["lifecycle_status"] == "archived"

    final_summary = build_host_runtime_summary(runtime_root)

    assert first["worker_dispatch"]["status"] == "waiting_worker"
    assert second["worker_dispatch"]["status"] == "waiting_worker"
    assert summary_after_dispatch["registry"]["status_counts"]["waiting_worker"] == 2
    assert verifier["final_state"]["worker_dispatch"]["status"] == "completed_inline"
    assert verifier["final_state"]["task_archive"]["status"]["lifecycle_status"] == "archived"
    assert inspect_command["event_type"] == "inspect_session"
    assert retry_payload["retried_count"] == 1
    assert unacked_retry_commands["entries"][0]["command_status"] == "retry"
    assert ack_payload["mailbox_ack_sequence"] == unacked_retry_commands["last_sequence"]
    assert code_a_ingest["driver_status"] == "stopped"
    assert code_a_ingest["final_state"]["task_archive"]["status"]["lifecycle_status"] == "archived"
    assert released["session_card"]["reuse_eligibility"]["decision"] == "reusable_now"
    assert reused["worker_dispatch"]["status"] == "waiting_worker"
    assert code_c_session["session_id"] == code_a_session["session_id"]
    assert code_c_session["dispatch_kind"] == "reuse"
    assert code_c_session["reused_from_task_id"] == "multi-code-a"
    assert code_c_session["context_paths_diff"]["schema_version"] == "commander-context-diff-v1"
    assert code_c_session["context_paths_diff"]["has_changes"] is True
    assert code_c_commands["entries"][0]["event_type"] == "assign_task"
    assert code_c_commands["entries"][0]["command_status"] == "pending"
    assert final_summary["registry"]["status_counts"]["closed"] == 2


def test_commander_graph_rejects_dispatch_when_provider_governance_fails(
    tmp_path: Path,
) -> None:
    task_card_path = tmp_path / "current_task_card.md"
    runtime_root = normalize_runtime_root(tmp_path / "runtime")
    write_task_card(
        task_card_path,
        "# Current Task Card\n\n## 5. Active Tasks\n\nNo active tasks.\n",
    )

    result = run_once(
        thread_id="test-provider-governance-failure",
        runtime_root=str(runtime_root),
        task_card_path=str(task_card_path),
        task_id="provider-governance-failure-task",
        checkpoint_db=str(tmp_path / "graph" / "checkpoints.sqlite"),
        worker_task_packet=make_worker_task_packet("provider-governance-failure-task"),
        worker_provider_id="qwen",
    )
    binding = build_task_worker_binding_summary(
        runtime_root, "provider-governance-failure-task"
    )

    assert result["route"] == "assign_worker"
    assert result["worker_orchestration"]["status"] == "blocked"
    assert result["worker_dispatch"]["status"] == "not_dispatched"
    assert result["worker_dispatch"]["reason"] == "dispatch_governance_rejected"
    assert any(
        "review-only provider" in item
        for item in result["worker_dispatch"]["violations"]
    )
    assert binding["leased_worker_count"] == 0


def test_commander_graph_rejects_dispatch_when_owned_paths_overlap_forbidden_paths(
    tmp_path: Path,
) -> None:
    task_card_path = tmp_path / "current_task_card.md"
    runtime_root = normalize_runtime_root(tmp_path / "runtime")
    write_task_card(
        task_card_path,
        "# Current Task Card\n\n## 5. Active Tasks\n\nNo active tasks.\n",
    )

    packet = {
        **make_worker_task_packet("path-governance-conflict-task"),
        "forbidden_paths": ["commander/graph"],
        "owned_paths": ["commander/graph/nodes"],
    }
    result = run_once(
        thread_id="test-path-governance-failure",
        runtime_root=str(runtime_root),
        task_card_path=str(task_card_path),
        task_id="path-governance-conflict-task",
        checkpoint_db=str(tmp_path / "graph" / "checkpoints.sqlite"),
        worker_task_packet=packet,
        worker_provider_id="codex",
    )
    binding = build_task_worker_binding_summary(
        runtime_root, "path-governance-conflict-task"
    )

    assert result["route"] == "assign_worker"
    assert result["worker_orchestration"]["status"] == "blocked"
    assert result["worker_dispatch"]["status"] == "not_dispatched"
    assert result["worker_dispatch"]["reason"] == "dispatch_governance_rejected"
    assert any(
        "overlaps forbidden_path" in item
        for item in result["worker_dispatch"]["violations"]
    )
    assert (
        result["worker_dispatch"]["governance"]["path_policy"]["conflicting_path_pairs"]
        == [
            {
                "owned_path": "commander/graph/nodes",
                "forbidden_path": "commander/graph",
            }
        ]
    )
    assert binding["leased_worker_count"] == 0


def test_commander_graph_promotes_phase_goal_and_runs_it_inline(
    tmp_path: Path,
) -> None:
    task_card_path = tmp_path / "current_task_card.md"
    runtime_root = normalize_runtime_root(tmp_path / "runtime")
    write_task_card(
        task_card_path,
        "# Current Task Card\n\n## 5. Active Tasks\n\nNo active tasks.\n",
    )
    provider_input = {
        "command": [
            str(PYTHON_EXE),
            "-c",
            "print('phase promotion provider ok')",
        ],
        "success_summary": "Phase goal executed inline.",
        "recommended_next_step": "Archive the task.",
    }
    create_phase_plan(
        runtime_root,
        phase_id="phase-m2",
        phase_key="langgraph-runtime",
        phase_title="Milestone 2",
        objective="Automatically continue the next goal.",
        goals=[
            make_phase_goal(
                "goal-1",
                "phase-goal-inline-task",
                provider_input=provider_input,
            )
        ],
    )

    result = run_until_handoff(
        thread_id="test-phase-goal-promotion",
        runtime_root=str(runtime_root),
        task_card_path=str(task_card_path),
        checkpoint_db=str(tmp_path / "graph" / "checkpoints.sqlite"),
        max_rounds=4,
    )

    phase_plan = load_phase_plan(runtime_root, "phase-m2")

    assert result["driver_status"] == "stopped"
    assert result["stop_reason"] == "terminal"
    assert result["task_id"] == "phase-goal-inline-task"
    assert result["final_state"]["phase_goal_promotion"]["status"] == "promoted"
    assert result["final_state"]["worker_dispatch"]["status"] == "completed_inline"
    assert result["final_state"]["task_archive"]["status"]["lifecycle_status"] == "archived"
    assert phase_plan["status"] == "completed"
    assert phase_plan["current_goal_id"] is None
    assert phase_plan["current_task_id"] is None
    assert phase_plan["goals"][0]["status"] == "done"


def test_commander_graph_run_once_cli(tmp_path: Path) -> None:
    task_card_path = tmp_path / "当前任务卡.md"
    write_task_card(
        task_card_path,
        "# 指挥官当前任务卡\n\n## 5. 当前活跃任务\n\n当前无活跃任务。\n",
    )
    result = subprocess.run(
        [
            str(PYTHON_EXE),
            "-m",
            "commander.graph.runners.run_once",
            "--thread-id",
            "test-cli",
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--task-card-path",
            str(task_card_path),
            "--checkpoint-db",
            str(tmp_path / "graph" / "checkpoints.sqlite"),
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["thread_id"] == "test-cli"
    assert payload["route"] == "deliver_result"


def test_commander_graph_binds_short_confirmation_to_latest_open_offer(
    tmp_path: Path,
) -> None:
    task_card_path = tmp_path / "current_task_card.md"
    runtime_root = tmp_path / "runtime"
    write_task_card(
        task_card_path,
        "# 鎸囨尌瀹樺綋鍓嶄换鍔″崱\n\n## 5. 褰撳墠娲昏穬浠诲姟\n\n褰撳墠鏃犳椿璺冧换鍔°€俓n",
    )
    dispatch_task(runtime_root, make_worker_task_packet("intent-binding-task"))

    result = run_once(
        thread_id="test-intent-binding",
        runtime_root=str(runtime_root),
        task_card_path=str(task_card_path),
        task_id="intent-binding-task",
        checkpoint_db=str(tmp_path / "graph" / "checkpoints.sqlite"),
        last_open_offer={
            "offer_id": "goal-4",
            "summary": "Continue Goal 4",
            "proposed_action": "Continue the next orchestration goal",
        },
        latest_user_reply_text="可以",
    )

    assert result["intent_binding"]["offer_confirmed"] is True
    assert result["intent_binding"]["resolved_reply_target"] == "goal-4"
    assert (
        result["intent_binding"]["binding_reason"]
        == "short_confirmation_bound_to_latest_open_offer"
    )

    paths = resolve_task_paths(
        normalize_runtime_root(runtime_root), "intent-binding-task"
    )
    resume_anchor = load_json(paths.resume_anchor_path)
    assert resume_anchor["offer_confirmed"] is True
    assert resume_anchor["pending_user_reply_target"] == "goal-4"


def test_commander_graph_keeps_freeform_reply_unconfirmed(
    tmp_path: Path,
) -> None:
    task_card_path = tmp_path / "current_task_card.md"
    runtime_root = tmp_path / "runtime"
    write_task_card(
        task_card_path,
        "# 鎸囨尌瀹樺綋鍓嶄换鍔″崱\n\n## 5. 褰撳墠娲昏穬浠诲姟\n\n褰撳墠鏃犳椿璺冧换鍔°€俓n",
    )
    dispatch_task(runtime_root, make_worker_task_packet("freeform-intent-task"))

    result = run_once(
        thread_id="test-freeform-intent",
        runtime_root=str(runtime_root),
        task_card_path=str(task_card_path),
        task_id="freeform-intent-task",
        checkpoint_db=str(tmp_path / "graph" / "checkpoints.sqlite"),
        last_open_offer={
            "offer_id": "goal-5",
            "summary": "Continue Goal 5",
            "proposed_action": "Prepare the next provider integration slice",
        },
        latest_user_reply_text="我想先看看方案",
    )

    assert result["intent_binding"]["offer_confirmed"] is False
    assert result["intent_binding"]["latest_user_reply_kind"] == "freeform_reply"
    assert (
        result["intent_binding"]["binding_reason"]
        == "freeform_reply_requires_normal_intent_resolution"
    )
