from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import inspect, select

from api import config as api_config
from api import db as api_db
from commander.transport.scripts.commander_harness import build_worker_report_draft
from commander.transport.scripts.commander_task_catalog import load_task_catalog
from commander.transport.scripts.commander_task_catalog_sync import main as sync_task_catalog_main


PYTHON_EXE = Path(sys.executable)


@pytest.fixture(autouse=True)
def isolated_commander_task_catalog_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    temp_auth_db_path = tmp_path / "commander_task_catalog.db"
    test_auth_settings = api_config.AuthSettings(
        jwt_secret="commander-task-catalog-secret",
        jwt_algorithm="HS256",
        access_token_expire_minutes=60,
        refresh_token_expire_days=7,
        database_url=f"sqlite:///{temp_auth_db_path.as_posix()}",
        runtime_store_backend="memory",
        redis_url="",
        redis_prefix="agent-catalog",
        allow_inmemory_runtime_store_fallback=False,
        demo_users=[],
    )

    monkeypatch.setattr(api_config, "get_auth_settings", lambda: test_auth_settings)
    monkeypatch.setattr(api_db, "get_auth_settings", lambda: test_auth_settings)

    api_db.reset_db_runtime_state()
    api_db.init_auth_db()

    yield

    try:
        api_db.get_engine().dispose()
    except Exception:
        pass
    api_db.reset_db_runtime_state()


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_event_log(path: Path, events: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(event, ensure_ascii=False) for event in events) + "\n", encoding="utf-8")


def _run_script(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(PYTHON_EXE), "-m", *args],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def _build_sample_catalog(tmp_path: Path) -> Path:
    runtime_root = tmp_path / "runtime"

    alpha_dir = runtime_root / "tasks" / "task-alpha"
    _write_json(
        alpha_dir / "packet.json",
        {
            "schema_version": "commander-harness-v1",
            "task_id": "task-alpha",
            "title": "Alpha task",
            "goal": "Stay file-backed",
            "must_read": ["README.md"],
            "bounds": ["No database"],
            "validation": ["pytest"],
            "forbidden_paths": ["config/rag.yml"],
            "worker_profile": "code-worker",
            "preferred_worker_profile": "code-worker",
            "tool_profile": "control_plane_safe_write",
            "allowed_tools": ["apply_patch", "shell_command"],
            "reuse_allowed": True,
            "report_contract": {
                "allowed_statuses": ["done", "blocked", "need_split"],
                "required_fields": ["task_id", "status", "summary"],
            },
            "status": "dispatched",
            "created_at": "2026-04-12T10:00:00Z",
            "updated_at": "2026-04-12T10:00:00Z",
        },
    )
    _write_json(alpha_dir / "worker_report.json", build_worker_report_draft("task-alpha"))
    _write_json(
        alpha_dir / "status.json",
        {
            "schema_version": "commander-harness-v1",
            "task_id": "task-alpha",
            "title": "Alpha task",
            "current_phase": "awaiting_report",
            "recommended_action": "wait_for_worker_report",
            "next_minimal_action": "Wait for the worker report",
            "worker_profile": "code-worker",
            "preferred_worker_profile": "code-worker",
            "tool_profile": "control_plane_safe_write",
            "allowed_tools": ["apply_patch", "shell_command"],
            "controller_handoff": "wait_external_result",
            "commander_recommendation": "awaiting_report",
            "worker_status": None,
            "needs_commander_decision": False,
            "needs_user_decision": False,
            "ready_for_user_delivery": False,
            "event_count": 1,
            "last_event_type": "task_dispatched",
            "last_event_at": "2026-04-12T10:00:05Z",
            "updated_at": "2026-04-12T10:00:10Z",
        },
    )
    _write_json(
        alpha_dir / "checkpoint.json",
        {
            "schema_version": "commander-harness-v1",
            "task_id": "task-alpha",
            "title": "Alpha task",
            "current_phase": "awaiting_report",
            "recommended_action": "wait_for_worker_report",
            "next_minimal_action": "Wait for the worker report",
            "worker_profile": "code-worker",
            "preferred_worker_profile": "code-worker",
            "tool_profile": "control_plane_safe_write",
            "allowed_tools": ["apply_patch", "shell_command"],
            "controller_handoff": "wait_external_result",
            "conversation_stop_required": False,
            "conversation_stop_reason": None,
            "blockers": [],
            "pending_decisions": [],
            "active_subagents": [],
            "active_subagents_summary": {
                "open_count": 0,
                "open_agent_ids": [],
                "open_nicknames": [],
                "states": [],
                "has_open_subagents": False,
            },
            "key_paths": {
                "packet": str(alpha_dir / "packet.json"),
                "worker_brief": str(alpha_dir / "worker_brief.md"),
                "worker_report": str(alpha_dir / "worker_report.json"),
                "report": str(alpha_dir / "report.json"),
                "checkpoint": str(alpha_dir / "checkpoint.json"),
                "status": str(alpha_dir / "status.json"),
                "events": str(alpha_dir / "events.jsonl"),
                "reports_dir": str(alpha_dir / "reports"),
            },
            "event_count": 1,
            "worker_status": None,
            "commander_recommendation": "awaiting_report",
            "needs_commander_decision": False,
            "needs_user_decision": False,
            "ready_for_user_delivery": False,
            "last_event_type": "task_dispatched",
            "last_event_at": "2026-04-12T10:00:05Z",
            "updated_at": "2026-04-12T10:00:10Z",
        },
    )
    _write_event_log(
        alpha_dir / "events.jsonl",
        [
            {
                "event_id": "alpha-event-1",
                "task_id": "task-alpha",
                "event_type": "task_dispatched",
                "timestamp": "2026-04-12T10:00:05Z",
                "detail": {"payload": "alpha"},
            }
        ],
    )

    beta_dir = runtime_root / "tasks" / "task-beta"
    _write_json(
        beta_dir / "packet.json",
        {
            "schema_version": "commander-harness-v1",
            "task_id": "task-beta",
            "title": "Beta task",
            "goal": "Expose completed state",
            "must_read": ["README.md"],
            "bounds": ["No database"],
            "validation": ["pytest"],
            "forbidden_paths": ["config/rag.yml"],
            "worker_profile": "analysis-worker",
            "preferred_worker_profile": None,
            "tool_profile": "default",
            "allowed_tools": ["shell_command"],
            "reuse_allowed": False,
            "report_contract": {
                "allowed_statuses": ["done", "blocked", "need_split"],
                "required_fields": ["task_id", "status", "summary"],
            },
            "status": "dispatched",
            "created_at": "2026-04-12T10:05:00Z",
            "updated_at": "2026-04-12T10:05:00Z",
        },
    )
    _write_json(beta_dir / "worker_report.json", build_worker_report_draft("task-beta"))
    _write_json(
        beta_dir / "report.json",
        {
            "schema_version": "commander-harness-v1",
            "task_id": "task-beta",
            "status": "done",
            "summary": "Completed beta task.",
            "changed_files": ["commander/transport/scripts/commander_task_catalog.py"],
            "verification": [{"name": "pytest", "result": "passed"}],
            "commit": {"message": "Add catalog entry"},
            "risks": [],
            "recommended_next_step": "Close the task.",
            "needs_commander_decision": False,
            "needs_user_decision": False,
            "ready_for_user_delivery": False,
            "harness_metadata": {"is_dispatch_draft": False},
        },
    )
    _write_json(
        beta_dir / "status.json",
        {
            "schema_version": "commander-harness-v1",
            "task_id": "task-beta",
            "title": "Beta task",
            "current_phase": "ready_to_close",
            "recommended_action": "close_task",
            "next_minimal_action": "Review the report and close the task",
            "worker_profile": "analysis-worker",
            "preferred_worker_profile": "",
            "tool_profile": "default",
            "allowed_tools": ["shell_command"],
            "controller_handoff": "continue",
            "commander_recommendation": "ready_to_close",
            "worker_status": "done",
            "needs_commander_decision": False,
            "needs_user_decision": False,
            "ready_for_user_delivery": False,
            "event_count": 2,
            "last_event_type": "task_report_ingested",
            "last_event_at": "2026-04-12T10:10:05Z",
            "updated_at": "2026-04-12T10:10:10Z",
        },
    )
    _write_json(
        beta_dir / "checkpoint.json",
        {
            "schema_version": "commander-harness-v1",
            "task_id": "task-beta",
            "title": "Beta task",
            "current_phase": "ready_to_close",
            "recommended_action": "close_task",
            "next_minimal_action": "Review the report and close the task",
            "worker_profile": "analysis-worker",
            "preferred_worker_profile": "",
            "tool_profile": "default",
            "allowed_tools": ["shell_command"],
            "controller_handoff": "continue",
            "conversation_stop_required": False,
            "conversation_stop_reason": None,
            "blockers": [],
            "pending_decisions": [],
            "active_subagents": [],
            "active_subagents_summary": {
                "open_count": 0,
                "open_agent_ids": [],
                "open_nicknames": [],
                "states": [],
                "has_open_subagents": False,
            },
            "key_paths": {
                "packet": str(beta_dir / "packet.json"),
                "worker_brief": str(beta_dir / "worker_brief.md"),
                "worker_report": str(beta_dir / "worker_report.json"),
                "report": str(beta_dir / "report.json"),
                "checkpoint": str(beta_dir / "checkpoint.json"),
                "status": str(beta_dir / "status.json"),
                "events": str(beta_dir / "events.jsonl"),
                "reports_dir": str(beta_dir / "reports"),
            },
            "event_count": 2,
            "worker_status": "done",
            "commander_recommendation": "ready_to_close",
            "needs_commander_decision": False,
            "needs_user_decision": False,
            "ready_for_user_delivery": False,
            "last_event_type": "task_report_ingested",
            "last_event_at": "2026-04-12T10:10:05Z",
            "updated_at": "2026-04-12T10:10:10Z",
        },
    )
    _write_event_log(
        beta_dir / "events.jsonl",
        [
            {
                "event_id": "beta-event-1",
                "task_id": "task-beta",
                "event_type": "task_dispatched",
                "timestamp": "2026-04-12T10:05:05Z",
                "detail": {"payload": "beta-1"},
            },
            {
                "event_id": "beta-event-2",
                "task_id": "task-beta",
                "event_type": "task_report_ingested",
                "timestamp": "2026-04-12T10:10:05Z",
                "detail": {"report_digest": "beta-2"},
            },
        ],
    )

    return runtime_root


def test_commander_task_catalog_table_is_available_after_migration_and_sync(tmp_path: Path) -> None:
    runtime_root = _build_sample_catalog(tmp_path)
    inspector = inspect(api_db.get_engine())
    assert inspector.has_table("commander_task_catalog") is True

    catalog = load_task_catalog(runtime_root)
    assert catalog["task_count"] == 2
    assert {item["task_id"] for item in catalog["tasks"]} == {"task-alpha", "task-beta"}

    sync_result = sync_task_catalog_main(
        [
            "--runtime-root",
            str(runtime_root),
        ]
    )
    assert sync_result == 0

    with api_db.session_scope() as session:
        rows = session.scalars(
            select(api_db.CommanderTaskCatalog).order_by(api_db.CommanderTaskCatalog.task_id.asc())
        ).all()

    assert [row.task_id for row in rows] == ["task-alpha", "task-beta"]
    alpha = rows[0]
    beta = rows[1]
    assert alpha.has_report is False
    assert alpha.controller_handoff == "wait_external_result"
    assert alpha.worker_profile == "code-worker"
    assert alpha.event_count == 1
    assert alpha.last_event_type == "task_dispatched"
    assert alpha.updated_at is not None
    assert beta.has_report is True
    assert beta.controller_handoff == "continue"
    assert beta.worker_profile == "analysis-worker"
    assert beta.event_count == 2
    assert beta.last_event_type == "task_report_ingested"
    assert beta.status == "done"


def test_commander_task_catalog_updates_via_natural_dispatch_and_ingest_points(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    env = {
        **os.environ,
        "AGENT_AUTH_DATABASE_URL": api_db.get_database_url(),
        "AGENT_AUTH_MIGRATION_DATABASE_URL": api_db.get_database_url(),
    }

    dispatch = _run_script(
        "commander.transport.scripts.commander_dispatch",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-auto",
        "--title",
        "Auto refresh task",
        "--goal",
        "Verify catalog refresh on dispatch",
        "--must-read",
        "README.md",
        "--bound",
        "transport only",
        "--validation",
        "pytest",
        "--forbidden-path",
        "config/rag.yml",
        "--worker-profile",
        "code-worker",
        "--tool-profile",
        "control_plane_safe_write",
        "--allowed-tool",
        "apply_patch",
        "--allowed-tool",
        "shell_command",
        env=env,
    )
    assert dispatch.returncode == 0, dispatch.stderr

    with api_db.session_scope() as session:
        row = session.get(api_db.CommanderTaskCatalog, "task-auto")
        assert row is not None
        assert row.has_packet is True
        assert row.has_report is False
        assert row.controller_handoff == "wait_external_result"
        assert row.worker_profile == "code-worker"
        assert row.status == "awaiting_report"
        assert row.event_count == 1
        assert row.last_event_type == "task_dispatched"

    report_path = tmp_path / "task-auto-report.json"
    report_path.write_text(
        json.dumps(
            {
                "schema_version": "commander-harness-v1",
                "task_id": "task-auto",
                "status": "done",
                "summary": "Auto refreshed report.",
                "changed_files": ["commander/transport/scripts/commander_task_catalog.py"],
                "verification": [{"name": "pytest", "result": "passed"}],
                "commit": {"message": "Auto refresh"},
                "risks": [],
                "recommended_next_step": "Close the task.",
                "needs_commander_decision": False,
                "needs_user_decision": False,
                "ready_for_user_delivery": False,
                "harness_metadata": {"is_dispatch_draft": False},
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    ingest = _run_script(
        "commander.transport.scripts.commander_ingest",
        "--runtime-root",
        str(runtime_root),
        "--report",
        str(report_path),
        env=env,
    )
    assert ingest.returncode == 0, ingest.stderr

    with api_db.session_scope() as session:
        row = session.get(api_db.CommanderTaskCatalog, "task-auto")
        assert row is not None
        assert row.has_report is True
        assert row.status == "done"
        assert row.controller_handoff == "continue"
        assert row.worker_status == "done"
        assert row.event_count == 2
        assert row.last_event_type == "task_report_ingested"
        assert row.updated_at is not None

    status = _run_script(
        "commander.transport.scripts.commander_status",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-auto",
        env=env,
    )
    assert status.returncode == 0, status.stderr
    resume = _run_script(
        "commander.transport.scripts.commander_resume",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-auto",
        env=env,
    )
    assert resume.returncode == 0, resume.stderr
    with api_db.session_scope() as session:
        row = session.get(api_db.CommanderTaskCatalog, "task-auto")
        assert row is not None
        assert row.status == "done"
