from __future__ import annotations

import json
from pathlib import Path

from commander.graph.adapters.host_runtime import (
    ExternalWindowHostRuntimeAdapter,
    HostRuntimeSessionContext,
)
from commander.transport.scripts.commander_host_runtime import (
    HOST_SESSION_CLOSED,
    HOST_SESSION_FAILED,
    HOST_SESSION_PENDING_LAUNCH,
    HOST_SESSION_REPORT_READY,
    HOST_SESSION_RESUME_REQUESTED,
    HOST_SESSION_WAITING_WORKER,
    ack_host_session_mailbox,
    append_host_session_mailbox_command,
    assign_reusable_host_session_to_task,
    build_host_runtime_summary,
    build_task_host_wait_summary,
    close_task_host_sessions,
    create_host_session,
    get_task_host_session_summary,
    list_host_session_reuse_candidates,
    mark_task_host_session_report_ready,
    read_host_session_mailbox_entries,
    record_host_session_launch_result,
    release_host_session_for_reuse,
    request_task_host_session_resume,
    retry_unacked_host_session_mailbox_commands,
    resume_waiting_host_sessions,
)
from commander.transport.scripts.commander_harness import resolve_task_paths


def test_create_host_session_reuses_dispatch_idempotency_key(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    launch_bundle = {
        "schema_version": "commander-host-launch-bundle-v1",
        "provider_id": "codex",
        "provider_label": "Codex Worker Window",
        "host_adapter_id": "external-window",
        "task_id": "task-1",
        "thread_id": "thread-1",
        "launch_mode": "bundle_only",
        "auto_launch_supported": False,
        "launch_status": "ready",
        "launch_prompt": "launch task-1",
        "provider_notes": ["note-a"],
        "read_order": ["worker_brief_path", "packet_path"],
        "bundle_paths": {"packet_path": "packet.json"},
        "limitations": ["manual handoff only"],
    }
    first = create_host_session(
        runtime_root,
        thread_id="thread-1",
        task_id="task-1",
        provider_id="codex",
        provider_label="Codex Worker Window",
        host_adapter_id="external-window",
        launch_prompt="launch task-1",
        provider_notes=["note-a"],
        launch_bundle_paths={"packet_path": "packet.json"},
        launch_bundle=launch_bundle,
        dispatch_idempotency_key="dispatch-1",
        worker_id="warm-codex-1",
        worker_profile="code-worker",
        preferred_worker_profile="code-worker",
        tool_profile="control_plane_safe_write",
        allowed_tools=["shell_command", "apply_patch"],
        forbidden_paths=["config/rag.yml"],
        owned_paths=["commander/graph", "commander/transport"],
        reuse_allowed=True,
        dispatch_kind="fresh",
        closure_policy="close_when_validated",
    )
    second = create_host_session(
        runtime_root,
        thread_id="thread-1",
        task_id="task-1",
        provider_id="codex",
        provider_label="Codex Worker Window",
        host_adapter_id="external-window",
        launch_prompt="launch task-1",
        provider_notes=["note-a"],
        launch_bundle_paths={"packet_path": "packet.json"},
        launch_bundle=launch_bundle,
        dispatch_idempotency_key="dispatch-1",
    )
    summary = build_host_runtime_summary(runtime_root, task_id="task-1")

    assert second["session_id"] == first["session_id"]
    assert summary["session_count"] == 1
    assert summary["registry"]["active_session_count"] == 1
    assert summary["registry"]["reusable_after_release_count"] == 1
    assert "resume" in first["host_controls"]
    assert first["launch_bundle"]["auto_launch_supported"] is False
    assert summary["sessions"][0]["launch_bundle"]["launch_mode"] == "bundle_only"
    assert first["session_card"]["worker_id"] == "warm-codex-1"
    assert first["session_card"]["worker_profile"] == "code-worker"
    assert first["session_card"]["tool_profile"] == "control_plane_safe_write"
    assert first["session_card"]["owned_paths"] == [
        "commander/graph",
        "commander/transport",
    ]
    assert first["session_card"]["reuse_eligibility"]["decision"] == "eligible_after_release"
    assert summary["session_pool"]["reuse_allowed_count"] == 1
    assert summary["session_pool"]["reusable_after_release_count"] == 1
    mailbox_path = Path(first["mailbox_path"])
    assert mailbox_path.exists()
    mailbox_lines = mailbox_path.read_text(encoding="utf-8").strip().splitlines()
    assert mailbox_lines
    assert json.loads(mailbox_lines[0])["event_type"] == "session_created"


def test_record_host_session_launch_result_updates_launch_bundle_and_status(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    session = create_host_session(
        runtime_root,
        thread_id="thread-launch",
        task_id="task-launch",
        provider_id="codex",
        provider_label="Codex Worker Window",
        host_adapter_id="external-window",
        launch_prompt="launch task-launch",
        launch_bundle={
            "schema_version": "commander-host-launch-bundle-v1",
            "provider_id": "codex",
            "provider_label": "Codex Worker Window",
            "host_adapter_id": "external-window",
            "task_id": "task-launch",
            "thread_id": "thread-launch",
            "launch_mode": "auto_launch",
            "auto_launch_supported": True,
            "launch_status": "pending_launch",
        },
        dispatch_idempotency_key="dispatch-launch",
        session_status=HOST_SESSION_PENDING_LAUNCH,
    )

    launched = record_host_session_launch_result(
        runtime_root,
        session["session_id"],
        launch_status="launched",
        session_status=HOST_SESSION_WAITING_WORKER,
        launch_result={"pid": 4321, "detached": False},
        note="auto_launch_started",
    )
    failed = record_host_session_launch_result(
        runtime_root,
        session["session_id"],
        launch_status="failed",
        session_status=HOST_SESSION_FAILED,
        launch_result={"error": "launcher missing"},
        note="auto_launch_failed",
    )

    assert launched["launch_bundle"]["launch_status"] == "launched"
    assert launched["launch_bundle"]["launch_result"]["pid"] == 4321
    assert launched["session_status"] == HOST_SESSION_WAITING_WORKER
    assert launched["session_card"]["launch_status"] == "launched"
    assert failed["launch_bundle"]["launch_status"] == "failed"
    assert failed["launch_bundle"]["launch_result"]["error"] == "launcher missing"
    assert failed["session_status"] == HOST_SESSION_FAILED
    assert failed["session_card"]["launch_status"] == "failed"
    assert failed["session_card"]["launch_result"]["error"] == "launcher missing"
    assert failed["last_note"] == "auto_launch_failed"


def test_host_runtime_lists_reuse_candidates_after_release(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    reusable = create_host_session(
        runtime_root,
        thread_id="thread-reuse-a",
        task_id="task-reuse-a",
        provider_id="codex",
        provider_label="Codex Worker Window",
        host_adapter_id="external-window",
        launch_prompt="launch reusable task",
        worker_profile="code-worker",
        tool_profile="control_plane_safe_write",
        allowed_tools=["shell_command", "apply_patch"],
        owned_paths=["commander/graph"],
        reuse_allowed=True,
        dispatch_idempotency_key="dispatch-reuse-a",
    )
    create_host_session(
        runtime_root,
        thread_id="thread-reuse-b",
        task_id="task-reuse-b",
        provider_id="qwen",
        provider_label="Qwen Worker Window",
        host_adapter_id="external-window",
        launch_prompt="launch mismatched provider task",
        worker_profile="code-worker",
        tool_profile="control_plane_safe_write",
        allowed_tools=["shell_command", "apply_patch"],
        owned_paths=["commander/graph"],
        reuse_allowed=True,
        dispatch_idempotency_key="dispatch-reuse-b",
    )
    create_host_session(
        runtime_root,
        thread_id="thread-reuse-c",
        task_id="task-reuse-c",
        provider_id="codex",
        provider_label="Codex Worker Window",
        host_adapter_id="external-window",
        launch_prompt="launch no-reuse task",
        worker_profile="code-worker",
        tool_profile="control_plane_safe_write",
        allowed_tools=["shell_command", "apply_patch"],
        owned_paths=["commander/transport"],
        reuse_allowed=False,
        dispatch_idempotency_key="dispatch-reuse-c",
    )

    payload = list_host_session_reuse_candidates(
        runtime_root,
        provider_id="codex",
        worker_profile="code-worker",
        tool_profile="control_plane_safe_write",
        allowed_tools=["shell_command"],
        owned_paths=["commander/graph/nodes"],
        include_rejected=True,
    )
    candidate = payload["candidates"][0]
    rejected_reasons = {
        item["task_id"]: item["reject_reasons"]
        for item in payload["rejected_sessions"]
    }

    assert payload["candidate_count"] == 1
    assert payload["rejected_count"] == 2
    assert payload["can_accept_new_task_count"] == 0
    assert candidate["session_id"] == reusable["session_id"]
    assert candidate["candidate_state"] == "eligible_after_release"
    assert candidate["can_accept_new_task"] is False
    assert candidate["owned_path_overlaps"] == [
        {
            "session_owned_path": "commander/graph",
            "requested_owned_path": "commander/graph/nodes",
        }
    ]
    assert "provider_id_mismatch" in rejected_reasons["task-reuse-b"]
    assert "reuse_disabled_by_packet" in rejected_reasons["task-reuse-c"]


def test_released_host_session_can_accept_new_task(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    session = create_host_session(
        runtime_root,
        thread_id="thread-released",
        task_id="task-released",
        provider_id="codex",
        provider_label="Codex Worker Window",
        host_adapter_id="external-window",
        launch_prompt="launch released task",
        worker_profile="code-worker",
        tool_profile="control_plane_safe_write",
        allowed_tools=["shell_command", "apply_patch"],
        owned_paths=["commander/graph"],
        reuse_allowed=True,
        dispatch_idempotency_key="dispatch-released",
    )
    report_path = str(tmp_path / "released-worker-report.json")
    mark_task_host_session_report_ready(runtime_root, "task-released", report_path)

    released = release_host_session_for_reuse(
        runtime_root,
        session["session_id"],
        reason="report_ingested_reuse_allowed",
    )
    payload = list_host_session_reuse_candidates(
        runtime_root,
        provider_id="codex",
        worker_profile="code-worker",
        tool_profile="control_plane_safe_write",
        allowed_tools=["shell_command"],
        owned_paths=["commander/graph/nodes"],
    )
    summary = build_host_runtime_summary(runtime_root)

    assert released["session_card"]["session_status"] == "released_reusable"
    assert released["session_card"]["last_report_path"] == report_path
    assert released["session_card"]["reuse_eligibility"]["decision"] == "reusable_now"
    assert released["session_card"]["can_accept_new_task"] is True
    assert payload["candidate_count"] == 1
    assert payload["can_accept_new_task_count"] == 1
    assert payload["candidates"][0]["candidate_state"] == "reusable_now"
    assert summary["registry"]["reusable_now_count"] == 1
    assert summary["session_pool"]["reusable_now_count"] == 1


def test_assign_reusable_host_session_to_new_task_writes_mailbox_command(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    session = create_host_session(
        runtime_root,
        thread_id="thread-old",
        task_id="task-old",
        provider_id="codex",
        provider_label="Codex Worker Window",
        host_adapter_id="external-window",
        launch_prompt="launch old task",
        worker_profile="code-worker",
        tool_profile="control_plane_safe_write",
        allowed_tools=["shell_command", "apply_patch"],
        owned_paths=["commander/graph"],
        reuse_allowed=True,
        dispatch_idempotency_key="dispatch-old",
    )
    released = release_host_session_for_reuse(
        runtime_root,
        session["session_id"],
        reason="report_ingested_reuse_allowed",
    )

    assigned = assign_reusable_host_session_to_task(
        runtime_root,
        task_id="task-new",
        thread_id="thread-new",
        launch_prompt="launch new task with delta context",
        session_id=released["session_id"],
        provider_id="codex",
        worker_profile="code-worker",
        tool_profile="control_plane_safe_write",
        allowed_tools=["shell_command"],
        owned_paths=["commander/graph/nodes"],
        launch_bundle_paths={"context_bundle_path": "context-bundle.json"},
        dispatch_idempotency_key="dispatch-new",
    )
    payload = list_host_session_reuse_candidates(
        runtime_root,
        provider_id="codex",
        worker_profile="code-worker",
        tool_profile="control_plane_safe_write",
        allowed_tools=["shell_command"],
        owned_paths=["commander/graph/nodes"],
    )
    mailbox_events = [
        json.loads(line)
        for line in Path(assigned["mailbox_path"]).read_text(encoding="utf-8").splitlines()
    ]
    mailbox_commands = read_host_session_mailbox_entries(
        runtime_root,
        assigned["session_id"],
        commands_only=True,
    )

    assert assigned["session_id"] == session["session_id"]
    assert assigned["task_id"] == "task-new"
    assert assigned["thread_id"] == "thread-new"
    assert assigned["session_status"] == "waiting_worker"
    assert assigned["reused_from_task_id"] == "task-old"
    assert assigned["reuse_count"] == 1
    assert assigned["task_history"][-1]["task_id"] == "task-old"
    assert assigned["session_card"]["can_accept_new_task"] is False
    assert assigned["session_card"]["reuse_eligibility"]["decision"] == "eligible_after_release"
    assert assigned["launch_bundle_paths"] == {
        "context_bundle_path": "context-bundle.json"
    }
    assert assigned["context_delivery_mode"] == "reuse_delta"
    assert assigned["context_delta_paths"] == {
        "context_bundle_path": "context-bundle.json"
    }
    assert assigned["context_paths_diff"]["schema_version"] == "commander-context-diff-v1"
    assert assigned["context_paths_diff"]["added_paths"] == {
        "context_bundle_path": "context-bundle.json"
    }
    assert assigned["context_paths_diff"]["removed_paths"] == {}
    assert assigned["context_paths_diff"]["has_changes"] is True
    assert assigned["session_card"]["context_delivery_mode"] == "reuse_delta"
    assert assigned["session_card"]["context_paths_diff"]["added_paths"] == {
        "context_bundle_path": "context-bundle.json"
    }
    assert payload["candidate_count"] == 1
    assert payload["can_accept_new_task_count"] == 0
    assert mailbox_events[-1]["event_type"] == "assign_task"
    assert mailbox_events[-1]["command_id"].startswith("assign_task-")
    assert mailbox_events[-1]["command_status"] == "pending"
    assert mailbox_events[-1]["retry_count"] == 0
    assert mailbox_events[-1]["task_id"] == "task-new"
    assert mailbox_events[-1]["previous_task_id"] == "task-old"
    assert mailbox_events[-1]["context_delivery_mode"] == "reuse_delta"
    assert mailbox_events[-1]["context_delta_paths"] == {
        "context_bundle_path": "context-bundle.json"
    }
    assert mailbox_events[-1]["context_paths_diff"]["added_paths"] == {
        "context_bundle_path": "context-bundle.json"
    }
    assert mailbox_commands["command_count"] == 1
    assert mailbox_commands["entries"][0]["event_type"] == "assign_task"
    assert mailbox_commands["entries"][0]["command_status"] == "pending"
    assert mailbox_commands["entries"][0]["task_id"] == "task-new"
    acked = ack_host_session_mailbox(
        runtime_root,
        assigned["session_id"],
        through_sequence=mailbox_commands["entries"][0]["sequence"],
        note="worker consumed assign_task",
    )
    unacked_commands = read_host_session_mailbox_entries(
        runtime_root,
        assigned["session_id"],
        commands_only=True,
        unacked_only=True,
    )
    assert acked["mailbox_ack_sequence"] == mailbox_commands["entries"][0]["sequence"]
    assert unacked_commands["command_count"] == 0


def test_host_session_mailbox_supports_multiple_command_types_and_retry(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    session = create_host_session(
        runtime_root,
        thread_id="thread-command",
        task_id="task-command",
        provider_id="codex",
        provider_label="Codex Worker Window",
        host_adapter_id="external-window",
        launch_prompt="launch command task",
        worker_profile="code-worker",
        tool_profile="control_plane_safe_write",
        allowed_tools=["shell_command", "apply_patch"],
        dispatch_idempotency_key="dispatch-command",
    )

    inspect_command = append_host_session_mailbox_command(
        runtime_root,
        session["session_id"],
        command_type="inspect_session",
        command_payload={"reason": "progress_check"},
        note="inspect progress",
    )
    resumed = request_task_host_session_resume(
        runtime_root,
        "task-command",
        note="resume stalled worker",
    )
    commands = read_host_session_mailbox_entries(
        runtime_root,
        session["session_id"],
        commands_only=True,
    )
    retry_result = retry_unacked_host_session_mailbox_commands(
        runtime_root,
        session["session_id"],
        max_retries=2,
        note="retry unacked commands",
    )
    unacked_retry_commands = read_host_session_mailbox_entries(
        runtime_root,
        session["session_id"],
        commands_only=True,
        unacked_only=True,
    )
    acked = ack_host_session_mailbox(
        runtime_root,
        session["session_id"],
        through_sequence=unacked_retry_commands["last_sequence"],
        note="worker consumed retry commands",
    )
    unacked_after_ack = read_host_session_mailbox_entries(
        runtime_root,
        session["session_id"],
        commands_only=True,
        unacked_only=True,
    )

    assert inspect_command["event_type"] == "inspect_session"
    assert inspect_command["command_payload"] == {"reason": "progress_check"}
    assert resumed is not None
    assert resumed["session_status"] == HOST_SESSION_RESUME_REQUESTED
    assert {item["event_type"] for item in commands["entries"]} == {
        "inspect_session",
        "resume_session",
    }
    assert retry_result["retried_count"] == 2
    assert retry_result["skipped_count"] == 0
    assert retry_result["retry_sequence"] == commands["last_sequence"]
    assert {item["event_type"] for item in unacked_retry_commands["entries"]} == {
        "inspect_session",
        "resume_session",
    }
    assert {
        item["command_status"] for item in unacked_retry_commands["entries"]
    } == {"retry"}
    assert {item["retry_count"] for item in unacked_retry_commands["entries"]} == {1}
    assert {
        item["retry_of_sequence"] for item in unacked_retry_commands["entries"]
    } == {entry["sequence"] for entry in commands["entries"]}
    assert acked["mailbox_ack_sequence"] == unacked_retry_commands["last_sequence"]
    assert unacked_after_ack["command_count"] == 0


def test_host_runtime_adapter_reuses_released_session(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    session = create_host_session(
        runtime_root,
        thread_id="thread-adapter-old",
        task_id="task-adapter-old",
        provider_id="codex",
        provider_label="Codex Worker Window",
        host_adapter_id="external-window",
        launch_prompt="launch old adapter task",
        worker_profile="code-worker",
        tool_profile="control_plane_safe_write",
        allowed_tools=["shell_command", "apply_patch"],
        owned_paths=["commander/graph"],
        reuse_allowed=True,
        dispatch_idempotency_key="dispatch-adapter-old",
    )
    release_host_session_for_reuse(
        runtime_root,
        session["session_id"],
        reason="report_ingested_reuse_allowed",
    )
    adapter = ExternalWindowHostRuntimeAdapter()

    reused = adapter.create_or_attach_session(
        HostRuntimeSessionContext(
            thread_id="thread-adapter-new",
            task_id="task-adapter-new",
            runtime_root=str(runtime_root),
            provider_id="codex",
            provider_label="Codex Worker Window",
            launch_prompt="launch new adapter task",
            provider_notes=[],
            launch_bundle_paths={"context_bundle_path": "new-context.json"},
            launch_bundle={"task_id": "task-adapter-new"},
            dispatch_idempotency_key="dispatch-adapter-new",
            worker_profile="code-worker",
            tool_profile="control_plane_safe_write",
            allowed_tools=("shell_command",),
            owned_paths=("commander/graph/nodes",),
            reuse_allowed=True,
        )
    )

    assert reused["session_id"] == session["session_id"]
    assert reused["task_id"] == "task-adapter-new"
    assert reused["thread_id"] == "thread-adapter-new"
    assert reused["dispatch_kind"] == "reuse"
    assert reused["reuse_count"] == 1
    assert reused["launch_bundle"] == {"task_id": "task-adapter-new"}
    assert reused["session_card"]["can_accept_new_task"] is False


def test_host_runtime_marks_report_ready_then_closes_task_session(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    launch_bundle = {
        "schema_version": "commander-host-launch-bundle-v1",
        "provider_id": "codex",
        "provider_label": "Codex Worker Window",
        "host_adapter_id": "external-window",
        "task_id": "task-2",
        "thread_id": "thread-2",
        "launch_mode": "bundle_only",
        "auto_launch_supported": False,
        "launch_status": "ready",
        "launch_prompt": "launch task-2",
        "provider_notes": [],
        "read_order": ["worker_brief_path", "packet_path"],
        "bundle_paths": {"packet_path": "packet.json"},
        "limitations": ["manual handoff only"],
    }
    session = create_host_session(
        runtime_root,
        thread_id="thread-2",
        task_id="task-2",
        provider_id="codex",
        provider_label="Codex Worker Window",
        host_adapter_id="external-window",
        launch_prompt="launch task-2",
        provider_notes=[],
        launch_bundle_paths={"packet_path": "packet.json"},
        launch_bundle=launch_bundle,
        dispatch_idempotency_key="dispatch-2",
    )
    report_path = str(tmp_path / "worker-report.json")

    ready = mark_task_host_session_report_ready(runtime_root, "task-2", report_path)
    closed = close_task_host_sessions(
        runtime_root,
        "task-2",
        reason="report_ingested",
        attached_report_path=report_path,
    )
    latest = get_task_host_session_summary(runtime_root, "task-2")

    assert ready is not None
    assert ready["session_id"] == session["session_id"]
    assert ready["session_status"] == HOST_SESSION_REPORT_READY
    assert closed[0]["session_status"] == HOST_SESSION_CLOSED
    assert latest is not None
    assert latest["session_status"] == HOST_SESSION_CLOSED
    assert latest["attached_report_path"] == report_path
    assert latest["launch_bundle"]["launch_status"] == "ready"
    assert latest["session_card"]["last_report_path"] == report_path


def test_host_wait_summary_prefers_worker_report_and_resume_requests(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    create_host_session(
        runtime_root,
        thread_id="thread-3",
        task_id="task-3",
        provider_id="codex",
        provider_label="Codex Worker Window",
        host_adapter_id="external-window",
        launch_prompt="launch task-3",
        provider_notes=[],
        launch_bundle_paths={"packet_path": "packet.json"},
        launch_bundle={
            "schema_version": "commander-host-launch-bundle-v1",
            "provider_id": "codex",
            "provider_label": "Codex Worker Window",
            "host_adapter_id": "external-window",
            "task_id": "task-3",
            "thread_id": "thread-3",
            "launch_mode": "bundle_only",
            "auto_launch_supported": False,
            "launch_status": "ready",
            "launch_prompt": "launch task-3",
            "provider_notes": [],
            "read_order": ["worker_brief_path", "packet_path"],
            "bundle_paths": {"packet_path": "packet.json"},
            "limitations": ["manual handoff only"],
        },
        dispatch_idempotency_key="dispatch-3",
    )

    initial_wait = build_task_host_wait_summary(runtime_root, "task-3")
    resumed = request_task_host_session_resume(
        runtime_root,
        "task-3",
        note="wait timeout",
    )
    task_paths = resolve_task_paths(runtime_root, "task-3")
    task_paths.worker_report_path.parent.mkdir(parents=True, exist_ok=True)
    task_paths.worker_report_path.write_text(
        json.dumps(
            {
                "schema_version": "commander-harness-v1",
                "task_id": "task-3",
                "status": "done",
                "summary": "Worker report is ready.",
                "changed_files": [],
                "verification": [],
                "commit": {"message": "worker report"},
                "risks": [],
                "recommended_next_step": "Ingest the report.",
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
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    ready_wait = build_task_host_wait_summary(runtime_root, "task-3")

    assert initial_wait is not None
    assert initial_wait["wait_reason"] == "external_worker_running"
    assert initial_wait["report_available"] is False
    assert resumed is not None
    assert resumed["session_status"] == HOST_SESSION_RESUME_REQUESTED
    assert ready_wait is not None
    assert ready_wait["session_status"] == HOST_SESSION_RESUME_REQUESTED
    assert ready_wait["report_available"] is True
    assert ready_wait["report_source"] == "worker_report"
    assert ready_wait["wait_reason"] == "worker_report_available"
    assert ready_wait["session_card"]["session_status"] == HOST_SESSION_RESUME_REQUESTED


def test_resume_waiting_host_sessions_batches_parallel_waits(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    for task_id in ("task-batch-a", "task-batch-b"):
        create_host_session(
            runtime_root,
            thread_id=f"thread-{task_id}",
            task_id=task_id,
            provider_id="codex",
            provider_label="Codex Worker Window",
            host_adapter_id="external-window",
            launch_prompt=f"launch {task_id}",
            provider_notes=[],
            launch_bundle_paths={"packet_path": "packet.json"},
            dispatch_idempotency_key=f"dispatch-{task_id}",
        )

    payload = resume_waiting_host_sessions(
        runtime_root,
        provider_id="codex",
        note="batch resume",
    )
    summary = build_host_runtime_summary(runtime_root)

    assert payload["matched_session_count"] == 2
    assert payload["resumed_session_count"] == 2
    assert {item["task_id"] for item in payload["resumed_sessions"]} == {
        "task-batch-a",
        "task-batch-b",
    }
    assert summary["registry"]["status_counts"][HOST_SESSION_RESUME_REQUESTED] == 2
