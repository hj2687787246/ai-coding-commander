from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from commander.transport.scripts.commander_harness import normalize_runtime_root
from commander.transport.scripts.commander_dispatch import dispatch_task
from commander.transport.scripts.commander_ingest import ingest_worker_report
from commander.transport.scripts.commander_host_runtime import create_host_session
from commander.transport.scripts.commander_objective_plan import create_objective_plan
from commander.transport.scripts.commander_phase_plan import create_phase_plan
from commander.transport.scripts.commander_phase_plan import load_phase_plan
from commander.transport.scripts.commander_phase_plan import write_phase_plan
from commander.graph.policies.role_guard import build_commander_role_guard_report
from commander.transport.scripts.commander_stop_gate import build_stop_gate_report


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON_EXE = Path(sys.executable)


def run_script(script_name: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(PYTHON_EXE), "-m", f"commander.transport.scripts.{script_name.removesuffix('.py')}", *args],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def make_report(task_id: str) -> dict[str, object]:
    return {
        "schema_version": "commander-harness-v1",
        "task_id": task_id,
        "status": "done",
        "summary": "Completed the worker task.",
        "changed_files": ["commander/transport/scripts/example.py"],
        "verification": [
            {
                "name": "pytest",
                "command": "python -m pytest -q tests/test_commander_stop_gate.py",
                "result": "passed",
            }
        ],
        "commit": {
            "message": "测试停机闸门",
        },
        "risks": [],
        "recommended_next_step": "Return final result to the user.",
        "needs_commander_decision": False,
        "result_grade": "closed",
        "next_action_owner": "commander",
        "continuation_mode": "close",
        "decision_reason": None,
        "split_suggestion": None,
        "needs_user_decision": False,
        "user_decision_reason": None,
        "ready_for_user_delivery": False,
        "harness_metadata": {
            "is_dispatch_draft": False,
        },
    }


def make_packet(task_id: str) -> dict[str, object]:
    return {
        "schema_version": "commander-harness-v1",
        "task_id": task_id,
        "title": "Task",
        "goal": "Task",
        "must_read": ["README.md"],
        "bounds": ["transport only"],
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
        "status": "dispatched",
        "created_at": "2026-04-12T00:00:00Z",
        "updated_at": "2026-04-12T00:00:00Z",
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


def make_phase_goal(
    goal_id: str,
    task_id: str,
    *,
    theme_key: str = "langgraph-runtime",
) -> dict[str, object]:
    return {
        "goal_id": goal_id,
        "theme_key": theme_key,
        "title": f"Goal {goal_id}",
        "objective": f"Implement {goal_id}",
        "task_id": task_id,
        "worker_provider_id": "local-script",
        "packet_template": {
            "must_read": ["README.md"],
            "bounds": ["commander only"],
            "validation": ["python -m pytest -q tests/test_commander_stop_gate.py"],
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


def make_objective_phase(
    phase_id: str,
    task_id: str,
    *,
    theme_key: str = "langgraph-runtime",
) -> dict[str, object]:
    return {
        "phase_id": phase_id,
        "phase_key": phase_id,
        "theme_key": theme_key,
        "phase_title": f"Phase {phase_id}",
        "objective": f"Complete {phase_id}",
        "goals": [make_phase_goal(f"{phase_id}-goal-1", task_id, theme_key=theme_key)],
    }


def test_stop_gate_blocks_active_task_card_work(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    task_card_path = tmp_path / "当前任务卡.md"
    task_card_path.write_text(
        "# 指挥官当前任务卡\n\n"
        "## 5. 当前活跃任务\n\n"
        "### `5.5 指挥官系统完善工程`\n\n"
        "- 当前状态：`active`\n"
        "- 下一步最小动作：继续 Phase F 收口\n",
        encoding="utf-8",
    )
    gate = run_script(
        "commander_stop_gate.py",
        "--runtime-root",
        str(runtime_root),
        "--task-card-path",
        str(task_card_path),
    )
    assert gate.returncode == 2
    payload = json.loads(gate.stdout)
    assert payload["stop_allowed"] is False
    assert payload["continuation_required"] is True
    assert payload["continuation_mode"] == "commander_internal"
    assert payload["outcome"] == "must_continue"
    assert payload["task_card_results"][0]["reason"] == "task_card_has_active_work"


def test_stop_gate_blocks_commander_write_violation(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    task_card_path = tmp_path / "task-card-role-guard.md"
    task_card_path.write_text(
        "# 鎸囨尌瀹樺綋鍓嶄换鍔″崱\n\n## 5. 褰撳墠娲昏穬浠诲姟\n\n褰撳墠鏃犳椿璺冧换鍔°€俓n",
        encoding="utf-8",
    )

    payload = build_stop_gate_report(
        runtime_root,
        task_card_path=task_card_path,
        repo_status_paths=[
            "AGENTS.md",
            "commander/graph/graph.py",
            "commander/state/当前任务卡.md",
        ],
        enforce_role_guard=True,
    )

    assert payload["stop_allowed"] is False
    assert payload["continuation_required"] is True
    assert payload["continuation_mode"] == "commander_internal"
    assert payload["outcome"] == "must_continue"
    assert payload["role_guard"]["violation_paths"] == ["commander/graph/graph.py"]
    assert payload["role_guard_result"]["outcome"] == "commander_write_violation"
    assert payload["next_actions"] == [
        "Delegate business-code changes to a worker sub-agent or reconcile/revert the commander-local diff before stopping."
    ]


def test_stop_gate_blocks_running_subagents_with_specific_reason(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    packet = make_packet("task-running-subagent")
    report = make_report("task-running-subagent")
    dispatch_task(runtime_root, packet)
    ingest_worker_report(runtime_root, report)

    run_state = run_script(
        "commander_agent_state.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-running-subagent",
        "--agent-id",
        "subagent-running",
        "--state",
        "running",
    )
    assert run_state.returncode == 0, run_state.stderr

    task_card_path = tmp_path / "task-card-running.md"
    task_card_path.write_text("# Current Task Card\n\n## 5. Active Tasks\n\nNo active tasks.\n", encoding="utf-8")
    gate = run_script(
        "commander_stop_gate.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-running-subagent",
        "--task-card-path",
        str(task_card_path),
    )

    assert gate.returncode == 2
    payload = json.loads(gate.stdout)
    assert payload["stop_allowed"] is False
    assert payload["continuation_required"] is True
    assert payload["continuation_mode"] == "commander_internal"
    assert payload["runtime_results"][0]["outcome"] == "active_subagents_running"
    assert payload["runtime_results"][0]["reason"] == "active_subagents_are_still_running"
    assert payload["runtime_results"][0]["active_subagents_summary"]["running_count"] == 1
    assert payload["next_actions"] == [
        "Wait for running sub-agents to finish or reassign them before closing the task."
    ]


def test_stop_gate_blocks_completed_waiting_close_subagents_with_specific_reason(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    packet = make_packet("task-waiting-close-subagent")
    report = make_report("task-waiting-close-subagent")
    dispatch_task(runtime_root, packet)
    ingest_worker_report(runtime_root, report)

    run_state = run_script(
        "commander_agent_state.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-waiting-close-subagent",
        "--agent-id",
        "subagent-complete",
        "--state",
        "completed_waiting_close",
    )
    assert run_state.returncode == 0, run_state.stderr

    task_card_path = tmp_path / "task-card-waiting-close.md"
    task_card_path.write_text("# Current Task Card\n\n## 5. Active Tasks\n\nNo active tasks.\n", encoding="utf-8")
    gate = run_script(
        "commander_stop_gate.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-waiting-close-subagent",
        "--task-card-path",
        str(task_card_path),
    )

    assert gate.returncode == 2
    payload = json.loads(gate.stdout)
    assert payload["stop_allowed"] is False
    assert payload["continuation_required"] is True
    assert payload["continuation_mode"] == "commander_internal"
    assert payload["runtime_results"][0]["outcome"] == "active_subagents_completed_waiting_close"
    assert payload["runtime_results"][0]["reason"] == "active_subagents_have_completed_results_pending_close"
    assert payload["runtime_results"][0]["active_subagents_summary"]["completed_waiting_close_count"] == 1
    assert payload["next_actions"] == [
        "Recover the completed results and close the sub-agents before closing the task."
    ]


def test_stop_gate_blocks_blocked_subagents_with_specific_reason(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    packet = make_packet("task-blocked-subagent")
    report = make_report("task-blocked-subagent")
    dispatch_task(runtime_root, packet)
    ingest_worker_report(runtime_root, report)

    run_state = run_script(
        "commander_agent_state.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-blocked-subagent",
        "--notification-json",
        json.dumps(
            {
                "agent_path": "workers/subagent-blocked",
                "status": {"blocked": "waiting on external input"},
            }
        ),
    )
    assert run_state.returncode == 0, run_state.stderr

    task_card_path = tmp_path / "task-card-blocked.md"
    task_card_path.write_text("# Current Task Card\n\n## 5. Active Tasks\n\nNo active tasks.\n", encoding="utf-8")
    gate = run_script(
        "commander_stop_gate.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-blocked-subagent",
        "--task-card-path",
        str(task_card_path),
    )

    assert gate.returncode == 2
    payload = json.loads(gate.stdout)
    assert payload["stop_allowed"] is False
    assert payload["continuation_required"] is True
    assert payload["continuation_mode"] == "commander_internal"
    assert payload["runtime_results"][0]["outcome"] == "active_subagents_blocked"
    assert payload["runtime_results"][0]["reason"] == "active_subagents_are_blocked"
    assert payload["runtime_results"][0]["active_subagents_summary"]["blocked_count"] == 1
    assert payload["next_actions"] == [
        "Unblock or close blocked sub-agents before closing the task."
    ]


def test_role_guard_accepts_quoted_commander_doc_path() -> None:
    payload = build_commander_role_guard_report(
        ['"commander/state/runtime-anchor.md"', "commander/graph/graph.py"],
        enabled=True,
    )

    assert payload["allowed_local_paths"] == ["commander/state/runtime-anchor.md"]
    assert payload["violation_paths"] == ["commander/graph/graph.py"]


def test_role_guard_ignores_safe_pytest_run_artifacts() -> None:
    payload = build_commander_role_guard_report(
        [
            "codex_test/pytest_runs/subagent-bridge-20260414/example/runtime/tasks/task-001/status.json",
            "scripts/run_pytest_safe.py",
        ],
        enabled=True,
    )

    assert payload["ignored_changed_paths"] == [
        "codex_test/pytest_runs/subagent-bridge-20260414/example/runtime/tasks/task-001/status.json"
    ]
    assert payload["violation_paths"] == ["scripts/run_pytest_safe.py"]


def test_stop_gate_blocks_awaiting_report_runtime_task(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    dispatch = run_script(
        "commander_dispatch.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-awaiting-report",
        "--title",
        "Awaiting report",
        "--goal",
        "Ensure awaiting worker result is not treated as user stop",
        "--must-read",
        "README.md",
        "--bound",
        "transport only",
        "--validation",
        "pytest",
    )
    assert dispatch.returncode == 0, dispatch.stderr
    create_host_session(
        runtime_root,
        thread_id="thread-awaiting-report",
        task_id="task-awaiting-report",
        provider_id="codex",
        provider_label="Codex Worker Window",
        host_adapter_id="external-window",
        launch_prompt="launch task-awaiting-report",
        provider_notes=[],
        launch_bundle_paths={"packet_path": "packet.json"},
        dispatch_idempotency_key="dispatch-awaiting-report",
    )

    task_card_path = tmp_path / "当前任务卡.md"
    task_card_path.write_text("# 指挥官当前任务卡\n\n## 5. 当前活跃任务\n\n当前无活跃任务。\n", encoding="utf-8")
    gate = run_script(
        "commander_stop_gate.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-awaiting-report",
        "--task-card-path",
        str(task_card_path),
    )
    assert gate.returncode == 2
    payload = json.loads(gate.stdout)
    assert payload["stop_allowed"] is False
    assert payload["continuation_required"] is True
    assert payload["continuation_mode"] == "wait_external_result"
    assert payload["task_card"]["claims_no_active_work"] is True
    assert payload["runtime_results"][0]["outcome"] == "wait_external_result"
    assert payload["runtime_results"][0]["reason"] == "external_worker_running"
    assert payload["runtime_results"][0]["host_wait"]["session_status"] == "waiting_worker"


def test_stop_gate_prefers_runtime_wait_over_active_task_card(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    dispatch = run_script(
        "commander_dispatch.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-awaiting-report-with-active-card",
        "--title",
        "Awaiting report with active card",
        "--goal",
        "Ensure concrete runtime wait is not downgraded by generic task card active work",
        "--must-read",
        "README.md",
        "--bound",
        "transport only",
        "--validation",
        "pytest",
    )
    assert dispatch.returncode == 0, dispatch.stderr
    create_host_session(
        runtime_root,
        thread_id="thread-awaiting-report-with-active-card",
        task_id="task-awaiting-report-with-active-card",
        provider_id="codex",
        provider_label="Codex Worker Window",
        host_adapter_id="external-window",
        launch_prompt="launch task-awaiting-report-with-active-card",
        provider_notes=[],
        launch_bundle_paths={"packet_path": "packet.json"},
        dispatch_idempotency_key="dispatch-awaiting-report-with-active-card",
    )

    task_card_path = tmp_path / "current_task_card.md"
    task_card_path.write_text(
        (
            "# \\u6307\\u6325\\u5b98\\u5f53\\u524d\\u4efb\\u52a1\\u5361\\n\\n"
            "## 5. \\u5f53\\u524d\\u6d3b\\u8dc3\\u4efb\\u52a1\\n\\n"
            "### `5.6 LangGraph \\u6307\\u6325\\u5b98\\u8fd0\\u884c\\u65f6\\u9879\\u76ee\\u5316`\\n\\n"
            "- \\u5f53\\u524d\\u72b6\\u6001\\uff1a`active`\\n"
        ).encode("ascii").decode("unicode_escape"),
        encoding="utf-8",
    )
    gate = run_script(
        "commander_stop_gate.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-awaiting-report-with-active-card",
        "--task-card-path",
        str(task_card_path),
    )
    assert gate.returncode == 2
    payload = json.loads(gate.stdout)
    assert payload["stop_allowed"] is False
    assert payload["continuation_required"] is True
    assert payload["continuation_mode"] == "wait_external_result"
    assert payload["runtime_results"][0]["outcome"] == "wait_external_result"
    assert payload["task_card_results"][0]["outcome"] == "must_continue"


def test_stop_gate_blocks_when_phase_plan_has_remaining_goals(tmp_path: Path) -> None:
    runtime_root = normalize_runtime_root(tmp_path / "runtime")
    create_phase_plan(
        runtime_root,
        phase_id="phase-m2",
        phase_key="langgraph-runtime",
        phase_title="Milestone 2",
        objective="Keep remaining goals machine-readable.",
        goals=[make_phase_goal("goal-1", "phase-goal-task-1")],
    )

    task_card_path = tmp_path / "current_task_card.md"
    task_card_path.write_text(
        "# Current Task Card\n\n## 5. Active Tasks\n\nNo active tasks.\n",
        encoding="utf-8",
    )
    gate = run_script(
        "commander_stop_gate.py",
        "--runtime-root",
        str(runtime_root),
        "--task-card-path",
        str(task_card_path),
    )

    assert gate.returncode == 2
    payload = json.loads(gate.stdout)
    assert payload["stop_allowed"] is False
    assert payload["continuation_required"] is True
    assert payload["continuation_mode"] == "commander_internal"
    assert payload["outcome"] == "must_continue"
    assert payload["phase_plan_results"][0]["outcome"] == "phase_goals_remaining"
    assert payload["phase_plan_results"][0]["remaining_goal_count"] == 1


def test_stop_gate_blocks_when_objective_has_pending_phases(tmp_path: Path) -> None:
    runtime_root = normalize_runtime_root(tmp_path / "runtime")
    create_objective_plan(
        runtime_root,
        objective_id="objective-m2",
        objective_key="langgraph-runtime",
        objective_title="Long objective",
        objective="Keep the long-running objective machine-readable.",
        phases=[make_objective_phase("phase-1", "objective-phase-task-1")],
    )

    task_card_path = tmp_path / "current_task_card.md"
    task_card_path.write_text(
        "# Current Task Card\n\n## 5. Active Tasks\n\nNo active tasks.\n",
        encoding="utf-8",
    )
    gate = run_script(
        "commander_stop_gate.py",
        "--runtime-root",
        str(runtime_root),
        "--task-card-path",
        str(task_card_path),
    )

    assert gate.returncode == 2
    payload = json.loads(gate.stdout)
    assert payload["stop_allowed"] is False
    assert payload["continuation_required"] is True
    assert payload["continuation_mode"] == "commander_internal"
    assert payload["outcome"] == "must_continue"
    assert payload["objective_plan_results"][0]["outcome"] == "objective_phases_remaining"
    assert payload["objective_plan_results"][0]["remaining_phase_count"] == 1


def test_stop_gate_blocks_after_current_phase_done_until_objective_done(
    tmp_path: Path,
) -> None:
    runtime_root = normalize_runtime_root(tmp_path / "runtime")
    create_objective_plan(
        runtime_root,
        objective_id="objective-long",
        objective_key="langgraph-runtime",
        objective_title="Long objective",
        objective="Do not stop at a single completed phase.",
        phases=[
            make_objective_phase("phase-1", "objective-phase-task-1"),
            make_objective_phase("phase-2", "objective-phase-task-2"),
        ],
    )
    promoted = run_script(
        "commander_objective_plan.py",
        "--runtime-root",
        str(runtime_root),
        "promote-next-phase",
        "--objective-id",
        "objective-long",
    )
    assert promoted.returncode == 0, promoted.stderr
    phase_plan = load_phase_plan(runtime_root, "phase-1")
    phase_plan["goals"][0]["status"] = "done"
    write_phase_plan(runtime_root, phase_plan)

    task_card_path = tmp_path / "current_task_card.md"
    task_card_path.write_text(
        "# Current Task Card\n\n## 5. Active Tasks\n\nNo active tasks.\n",
        encoding="utf-8",
    )
    gate = run_script(
        "commander_stop_gate.py",
        "--runtime-root",
        str(runtime_root),
        "--task-card-path",
        str(task_card_path),
    )

    assert gate.returncode == 2
    payload = json.loads(gate.stdout)
    assert payload["stop_allowed"] is False
    assert payload["continuation_required"] is True
    assert payload["outcome"] == "must_continue"
    assert payload["phase_plan_results"] == []
    assert payload["objective_plan_results"][0]["outcome"] == "objective_phases_remaining"
    assert payload["objective_plan_results"][0]["current_phase"] is None
    assert payload["objective_plan_results"][0]["promotable_phase_id"] == "phase-2"
    assert payload["objective_plan_results"][0]["next_phase"]["phase_id"] == "phase-2"


def test_stop_gate_allows_explicit_final_delivery(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    dispatch = run_script(
        "commander_dispatch.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-final-delivery",
        "--title",
        "Final delivery",
        "--goal",
        "Ensure final delivery is allowed to stop at user layer",
        "--must-read",
        "README.md",
        "--bound",
        "transport only",
        "--validation",
        "pytest",
    )
    assert dispatch.returncode == 0, dispatch.stderr

    report = make_report("task-final-delivery")
    report["ready_for_user_delivery"] = True
    report_path = tmp_path / "final-delivery-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ingest = run_script(
        "commander_ingest.py",
        "--runtime-root",
        str(runtime_root),
        "--report",
        str(report_path),
    )
    assert ingest.returncode == 0, ingest.stderr

    task_card_path = tmp_path / "当前任务卡.md"
    task_card_path.write_text("# 指挥官当前任务卡\n\n## 5. 当前活跃任务\n\n当前无活跃任务。\n", encoding="utf-8")
    gate = run_script(
        "commander_stop_gate.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-final-delivery",
        "--task-card-path",
        str(task_card_path),
    )
    assert gate.returncode == 0
    payload = json.loads(gate.stdout)
    assert payload["stop_allowed"] is True
    assert payload["continuation_required"] is False
    assert payload["continuation_mode"] == "user_handoff"
    assert payload["outcome"] == "user_handoff_allowed"
    assert payload["task_card"]["claims_no_active_work"] is True
    assert payload["runtime_results"][0]["outcome"] == "return_final_result"
