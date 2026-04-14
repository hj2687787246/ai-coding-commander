from __future__ import annotations

import json
import subprocess
import sys
import types
from pathlib import Path

import pytest

from commander.transport.scripts.commander_harness import (
    PACKET_SCHEMA_PATH,
    IMPROVEMENT_SCHEMA_PATH,
    REPORT_SCHEMA_PATH,
    WORKER_SLOT_SCHEMA_PATH,
    SchemaValidationError,
    build_worker_brief,
    build_worker_report_draft,
    build_catalog_refresh_summary,
    ensure_report_ready_for_ingest,
    find_report_draft_markers,
    is_dispatch_draft_report,
    load_events,
    load_json,
    load_schema,
    mark_task_stale,
    normalize_active_subagent_update,
    refresh_status,
    refresh_commander_task_catalog,
    resolve_task_paths,
    validate_instance,
    write_json,
)
from commander.transport.scripts.commander_dispatch import dispatch_task
from commander.transport.scripts.commander_context_router import (
    CONTEXT_BUNDLE_SCHEMA_PATH,
    build_context_bundle,
)
from commander.transport.scripts.commander_audit import build_audit_report
from commander.transport.scripts.commander_close import close_task
from commander.transport.scripts.commander_ingest import ingest_worker_report
from commander.transport.scripts.commander_resume import build_resume_anchor
from commander.transport.scripts.commander_task_catalog import (
    build_task_catalog_summary,
    load_task_catalog,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON_EXE = Path(sys.executable)


def make_packet() -> dict[str, object]:
    return {
        "schema_version": "commander-harness-v1",
        "task_id": "task-001",
        "title": "Implement minimal harness",
        "goal": "Add dispatch and ingest transport",
        "must_read": ["README.md", "commander/outer/agent_workbench.md"],
        "bounds": ["Do not modify business workflow code"],
        "validation": ["python -m pytest -q tests/test_commander_harness.py"],
        "forbidden_paths": ["config/rag.yml"],
        "worker_profile": "code-worker",
        "preferred_worker_profile": "code-worker",
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
        "created_at": "2026-04-11T00:00:00Z",
        "updated_at": "2026-04-11T00:00:00Z",
        "notes": ["transport only"],
    }


def make_report() -> dict[str, object]:
    return {
        "schema_version": "commander-harness-v1",
        "task_id": "task-001",
        "status": "done",
        "summary": "Completed dispatch and ingest scripts.",
        "changed_files": ["commander/transport/scripts/commander_dispatch.py"],
        "verification": [
            {
                "name": "pytest",
                "command": "python -m pytest -q tests/test_commander_harness.py",
                "result": "passed",
            }
        ],
        "commit": {
            "message": "提交最小 harness v1",
        },
        "risks": ["status only reflects one current report"],
        "recommended_next_step": "Wire the commander prompt template to emit packet fields directly.",
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


def write_json_file(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def write_event_log(path: Path, events: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(event, ensure_ascii=False) for event in events) + "\n",
        encoding="utf-8",
    )


def run_script(script_name: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            str(PYTHON_EXE),
            "-m",
            f"commander.transport.scripts.{script_name.removesuffix('.py')}",
            *args,
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def create_cleanup_ready_archived_task(
    tmp_path: Path,
    *,
    task_id: str,
    title: str,
    goal: str,
    runtime_dir_name: str,
) -> tuple[Path, Path]:
    runtime_root = tmp_path / runtime_dir_name
    dispatch = run_script(
        "commander_dispatch.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        task_id,
        "--title",
        title,
        "--goal",
        goal,
        "--must-read",
        "README.md",
        "--bound",
        "transport only",
        "--validation",
        "pytest",
    )
    assert dispatch.returncode == 0, dispatch.stderr

    report = make_report()
    report["task_id"] = task_id
    report_path = tmp_path / f"{task_id}-report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    ingest = run_script(
        "commander_ingest.py",
        "--runtime-root",
        str(runtime_root),
        "--report",
        str(report_path),
    )
    assert ingest.returncode == 0, ingest.stderr

    candidate_path = runtime_root / "improvements" / f"{task_id}.candidate.json"
    review_result = run_script(
        "commander_review_improvement.py",
        "--candidate",
        str(candidate_path),
        "--decision",
        "approve",
    )
    assert review_result.returncode == 0, review_result.stderr

    apply_result = run_script(
        "commander_apply_improvement.py",
        "--candidate",
        str(candidate_path),
        "--runtime-root",
        str(runtime_root),
    )
    assert apply_result.returncode == 0, apply_result.stderr
    apply_payload = json.loads(apply_result.stdout)
    action_dir = Path(apply_payload["output_dir"])
    assert action_dir.exists() is True

    close_result = run_script(
        "commander_close.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        task_id,
    )
    assert close_result.returncode == 0, close_result.stderr

    archive_result = run_script(
        "commander_archive.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        task_id,
    )
    assert archive_result.returncode == 0, archive_result.stderr

    task_dir = runtime_root / "tasks" / task_id
    lifecycle_path = task_dir / "lifecycle.json"
    lifecycle = load_json(lifecycle_path)
    lifecycle["archived_at"] = "2000-01-01T00:00:00Z"
    write_json_file(lifecycle_path, lifecycle)
    return runtime_root, action_dir


def test_packet_schema_accepts_valid_packet() -> None:
    validate_instance(make_packet(), load_schema(PACKET_SCHEMA_PATH))


def test_worker_slot_schema_accepts_valid_worker_slot() -> None:
    validate_instance(
        {
            "schema_version": "commander-harness-v1",
            "worker_id": "code-worker-001",
            "worker_profile": "code-worker",
            "preferred_worker_profile": "code-worker",
            "tool_profile": "control_plane_safe_write",
            "allowed_tools": ["apply_patch", "shell_command"],
            "state": "warm_idle",
            "current_task_id": None,
            "acquire_count": 1,
            "reuse_count": 0,
            "lease_duration_seconds": 1800,
            "lease_expires_at": None,
            "heartbeat_at": None,
            "created_at": "2026-04-12T00:00:00Z",
            "updated_at": "2026-04-12T00:00:00Z",
            "last_used_at": "2026-04-12T00:00:00Z",
            "last_released_at": None,
        },
        load_schema(WORKER_SLOT_SCHEMA_PATH),
    )


def test_report_schema_rejects_invalid_status() -> None:
    invalid = make_report()
    invalid["status"] = "partial"
    with pytest.raises(SchemaValidationError):
        validate_instance(invalid, load_schema(REPORT_SCHEMA_PATH))


def test_load_json_accepts_utf8_bom(tmp_path: Path) -> None:
    payload = {"hello": "world"}
    path = tmp_path / "bom.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8-sig")
    assert load_json(path) == payload


def test_write_json_uses_clean_final_path_without_temp_residue(tmp_path: Path) -> None:
    payload = {"hello": "world"}
    path = tmp_path / "payload.json"

    write_json(path, payload)

    assert load_json(path) == payload
    assert list(tmp_path.glob("*.tmp")) == []


def test_report_ready_for_ingest_rejects_draft_placeholders() -> None:
    draft = build_worker_report_draft("task-001")
    assert is_dispatch_draft_report(draft) is True
    assert find_report_draft_markers(draft)
    assert "harness_metadata.is_dispatch_draft" in draft["summary"]
    assert "harness_metadata.is_dispatch_draft" in draft["recommended_next_step"]
    with pytest.raises(SchemaValidationError, match="still marked as a dispatch draft"):
        ensure_report_ready_for_ingest(draft)


def test_report_ready_for_ingest_accepts_real_report() -> None:
    report = make_report()
    assert is_dispatch_draft_report(report) is False
    assert find_report_draft_markers(report) == []
    ensure_report_ready_for_ingest(report)


def test_report_ready_for_ingest_keeps_placeholder_fallback_for_legacy_report() -> None:
    legacy_report = make_report()
    legacy_report.pop("harness_metadata")
    legacy_report["summary"] = "待执行窗口填写：legacy draft placeholder"
    with pytest.raises(SchemaValidationError, match="draft placeholder"):
        ensure_report_ready_for_ingest(legacy_report)


def test_execution_window_templates_reference_packet_and_report_contract() -> None:
    task_template = (
        PROJECT_ROOT
        / "commander"
        / "transport"
        / "prompts"
        / "execution_window_task_template.md"
    ).read_text(encoding="utf-8")
    report_template = (
        PROJECT_ROOT
        / "commander"
        / "transport"
        / "prompts"
        / "execution_window_report_template.md"
    ).read_text(encoding="utf-8")

    assert "packet.json" in task_template
    assert "worker_brief.md" in task_template
    assert "context_bundle.json" in task_template
    assert "resume_anchor.json" in task_template
    assert "checkpoint.json" in task_template
    assert "commander_resume.py --compact --task-id <task_id>" in task_template
    assert "worker_report.json" in task_template
    assert "commander_task_report.schema.json" in task_template
    assert "read_policy" in task_template
    assert "summary_lines" in task_template
    assert "deferred_paths" in task_template

    assert "worker_report.json" in report_template
    assert "checkpoint.json" in report_template
    assert '"status": "done"' in report_template
    assert '"needs_commander_decision": false' in report_template
    assert '"result_grade": "closed"' in report_template
    assert '"next_action_owner": "commander"' in report_template
    assert '"continuation_mode": "close"' in report_template
    assert '"needs_user_decision": false' in report_template
    assert '"ready_for_user_delivery": false' in report_template
    assert '"is_dispatch_draft": false' in report_template
    assert "harness_metadata.is_dispatch_draft" in report_template
    assert "harness_metadata.is_dispatch_draft" in task_template
    assert "needs_user_decision" in report_template
    assert "ready_for_user_delivery" in report_template
    assert "result_grade" in task_template
    assert "next_action_owner" in task_template
    assert "continuation_mode" in task_template
    assert "split_suggestion" in task_template


def test_dispatch_routes_spec_refs_into_brief_and_context_bundle(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    dispatch = run_script(
        "commander_dispatch.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-spec-routing",
        "--title",
        "Spec routing smoke",
        "--goal",
        "Route spec refs through packet and context bundle",
        "--must-read",
        "README.md",
        "--bound",
        "transport only",
        "--validation",
        "pytest",
        "--spec-ref",
        "commander/specs/task-5-7-spec-template.json",
    )
    assert dispatch.returncode == 0, dispatch.stderr
    payload = json.loads(dispatch.stdout)
    packet_path = Path(payload["packet_path"])
    context_bundle_path = Path(payload["context_bundle_path"])
    worker_brief_path = Path(payload["worker_brief_path"])

    packet_payload = load_json(packet_path)
    assert packet_payload["spec_refs"][0]["spec_id"] == "task-5-7-spec-template"
    assert packet_payload["spec_refs"][0]["path"] == "commander/specs/task-5-7-spec-template.json"
    assert packet_payload["spec_refs"][0]["status"] == "active"

    context_bundle = load_json(context_bundle_path)
    spec_entry = next(
        entry for entry in context_bundle["entries"] if entry["context_id"] == "spec_artifacts"
    )
    assert spec_entry["disclosure_mode"] == "always_open"
    assert spec_entry["deferred_paths"] == []
    assert any(
        Path(path).as_posix().endswith("commander/specs/task-5-7-spec-template.json")
        for path in spec_entry["paths"]
    )

    worker_brief = worker_brief_path.read_text(encoding="utf-8")
    assert "## Spec References" in worker_brief
    assert "task-5-7-spec-template" in worker_brief


def test_worker_brief_includes_checkpoint_resume_anchor() -> None:
    packet = make_packet()
    resume_anchor_path = (
        PROJECT_ROOT
        / ".runtime"
        / "commander"
        / "tasks"
        / packet["task_id"]
        / "resume_anchor.json"
    )
    checkpoint_path = (
        PROJECT_ROOT
        / ".runtime"
        / "commander"
        / "tasks"
        / packet["task_id"]
        / "checkpoint.json"
    )
    context_bundle_path = (
        PROJECT_ROOT
        / ".runtime"
        / "commander"
        / "tasks"
        / packet["task_id"]
        / "context_bundle.json"
    )
    context_bundle = build_context_bundle(
        packet,
        provider_id="codex",
        runtime_artifact_paths={
            "packet": str(PROJECT_ROOT / ".runtime" / "commander" / "tasks" / packet["task_id"] / "packet.json"),
            "resume_anchor": str(resume_anchor_path),
            "checkpoint": str(checkpoint_path),
        },
    )

    langgraph_entry = next(
        entry
        for entry in context_bundle["entries"]
        if entry["context_id"] == "langgraph_runtime"
    )
    runtime_entry = next(
        entry
        for entry in context_bundle["entries"]
        if entry["context_id"] == "runtime_artifacts"
    )
    brief = build_worker_brief(
        packet,
        context_bundle_path=context_bundle_path,
        context_bundle=context_bundle,
        resume_anchor_path=resume_anchor_path,
        checkpoint_path=checkpoint_path,
    )

    assert "## Compact Resume Anchor" in brief
    assert "## Checkpoint / Resume" in brief
    assert "## Worker Execution" in brief
    assert "Worker profile: code-worker" in brief
    assert "Preferred warm worker profile: code-worker" in brief
    assert "Reuse allowed: True" in brief
    assert "## Tool Boundary" in brief
    assert "Tool profile: control_plane_safe_write" in brief
    assert "apply_patch" in brief
    assert "## Dispatch Governance" in brief
    assert "## Context Route" in brief
    assert str(context_bundle_path) in brief
    assert "Read policy: progressive_disclosure" in brief
    assert "Router round budget: 12000 tokens" in brief
    assert "Router open-now estimate:" in brief
    assert "Default behavior:" in brief
    assert "commander_rules" in brief
    assert "[metadata_first]" in brief
    assert "budget: pinned_open" in brief
    assert "budget: deferred_by_budget" in brief
    assert "defer until needed:" in brief
    assert "trigger:" in brief
    assert "Dispatch kind: fresh" in brief
    assert str(resume_anchor_path) in brief
    assert "Task owner: commander" in brief
    assert str(checkpoint_path) in brief
    assert "resume_anchor.json" in brief
    assert "checkpoint.json" in brief
    assert langgraph_entry["disclosure_mode"] == "metadata_first"
    assert langgraph_entry["deferred_paths"]
    assert langgraph_entry["priority"] == "high"
    assert langgraph_entry["budget_action"] == "deferred_by_budget"
    assert str(resume_anchor_path) in runtime_entry["paths"]
    assert str(checkpoint_path) in runtime_entry["deferred_paths"]
    assert runtime_entry["priority"] == "critical"
    assert runtime_entry["budget_action"] == "pinned_open"
    assert context_bundle["read_policy"]["mode"] == "progressive_disclosure"
    assert context_bundle["read_policy"]["compact_resume_first"] is True
    assert context_bundle["read_policy"]["round_budget_tokens"] == 12000
    assert context_bundle["read_policy"]["deferred_by_budget_context_ids"] == [
        "memory_index",
        "langgraph_runtime",
        "repo_runbook",
        "execution_workbench",
    ]


def test_context_bundle_defers_low_priority_entries_when_budget_is_tight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COMMANDER_CONTEXT_ROUND_BUDGET_TOKENS", "50")
    packet = make_packet()
    resume_anchor_path = (
        PROJECT_ROOT
        / ".runtime"
        / "commander"
        / "tasks"
        / packet["task_id"]
        / "resume_anchor.json"
    )
    checkpoint_path = (
        PROJECT_ROOT
        / ".runtime"
        / "commander"
        / "tasks"
        / packet["task_id"]
        / "checkpoint.json"
    )
    context_bundle = build_context_bundle(
        packet,
        provider_id="codex",
        runtime_artifact_paths={
            "packet": str(
                PROJECT_ROOT
                / ".runtime"
                / "commander"
                / "tasks"
                / packet["task_id"]
                / "packet.json"
            ),
            "resume_anchor": str(resume_anchor_path),
            "checkpoint": str(checkpoint_path),
        },
    )

    read_policy = context_bundle["read_policy"]
    runtime_entry = next(
        entry
        for entry in context_bundle["entries"]
        if entry["context_id"] == "runtime_artifacts"
    )
    commander_rules_entry = next(
        entry
        for entry in context_bundle["entries"]
        if entry["context_id"] == "commander_rules"
    )
    deferred_entries = [
        entry
        for entry in context_bundle["entries"]
        if entry["budget_action"] == "deferred_by_budget"
    ]

    assert read_policy["round_budget_tokens"] == 50
    assert read_policy["router_budget_enforced"] is True
    assert read_policy["deferred_by_budget_context_ids"]
    assert read_policy["router_deferred_estimated_tokens"] > 0
    assert runtime_entry["budget_action"] == "pinned_open"
    assert commander_rules_entry["budget_action"] == "pinned_open"
    assert deferred_entries
    assert all(entry["paths"] == [] for entry in deferred_entries)
    assert all(entry["deferred_paths"] for entry in deferred_entries)
    assert any(
        entry["context_id"] in {"langgraph_runtime", "execution_workbench", "repo_runbook"}
        for entry in deferred_entries
    )
    assert all("round budget of 50 tokens" in entry["budget_reason"] for entry in deferred_entries)


def test_refresh_status_context_budget_tolerates_missing_context_bundle(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    packet = make_packet()
    packet["task_id"] = "task-no-context-bundle"
    paths = resolve_task_paths(runtime_root, str(packet["task_id"]))
    write_json(paths.packet_path, packet)

    snapshot = refresh_status(paths)

    assert paths.context_bundle_path.exists() is False
    assert snapshot["context_budget"]["scope"] == "task_round_context"
    assert snapshot["context_budget"]["estimation_mode"] == "heuristic_non_metered"
    assert snapshot["context_budget"]["open_now_estimated_tokens"] > 0
    assert "router_open_now_estimated_tokens" not in snapshot["context_budget"]
    resume_anchor = load_json(paths.resume_anchor_path)
    assert resume_anchor["context_budget"]["open_now_estimated_tokens"] == snapshot[
        "context_budget"
    ]["open_now_estimated_tokens"]


def test_dispatch_ingest_status_cli_smoke(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    dispatch = run_script(
        "commander_dispatch.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-001",
        "--title",
        "Harness smoke",
        "--goal",
        "Exercise dispatch ingest status",
        "--must-read",
        "README.md",
        "--bound",
        "transport only",
        "--validation",
        "pytest",
        "--forbidden-path",
        "config/rag.yml",
        "--tool-profile",
        "control_plane_safe_write",
        "--allowed-tool",
        "apply_patch",
        "--allowed-tool",
        "shell_command",
    )
    assert dispatch.returncode == 0, dispatch.stderr
    dispatch_payload = json.loads(dispatch.stdout)
    packet_path = Path(dispatch_payload["packet_path"])
    context_bundle_path = Path(dispatch_payload["context_bundle_path"])
    worker_report_path = Path(dispatch_payload["worker_report_path"])
    resume_anchor_path = Path(dispatch_payload["resume_anchor_path"])
    checkpoint_path = Path(dispatch_payload["checkpoint_path"])
    status_path = Path(dispatch_payload["status_path"])
    compaction_event_path = runtime_root / "tasks" / "task-001" / "compaction_event.json"
    assert packet_path.exists()
    assert context_bundle_path.exists()
    assert worker_report_path.exists()
    assert resume_anchor_path.exists()
    assert checkpoint_path.exists()
    assert status_path.exists()
    assert resume_anchor_path.stat().st_size < checkpoint_path.stat().st_size
    validate_instance(
        json.loads(packet_path.read_text(encoding="utf-8")),
        load_schema(PACKET_SCHEMA_PATH),
    )
    validate_instance(
        load_json(context_bundle_path),
        load_schema(CONTEXT_BUNDLE_SCHEMA_PATH),
    )
    packet_payload = load_json(packet_path)
    assert packet_payload["tool_profile"] == "control_plane_safe_write"
    assert packet_payload["allowed_tools"] == ["apply_patch", "shell_command"]
    assert packet_payload["worker_profile"] == "code-worker"
    assert packet_payload["preferred_worker_profile"] is None
    assert packet_payload["reuse_allowed"] is True
    assert packet_payload["dispatch_kind"] == "fresh"
    assert packet_payload["source_task_id"] is None
    assert packet_payload["parent_task_id"] is None
    assert packet_payload["task_owner"] == "commander"
    assert packet_payload["closure_policy"] == "close_when_validated"
    context_bundle_payload = load_json(context_bundle_path)
    assert "worker-orchestration" in context_bundle_payload["selected_tags"]
    assert context_bundle_payload["read_policy"]["mode"] == "progressive_disclosure"
    assert (
        context_bundle_payload["read_policy"]["recommended_sequence"][:3]
        == ["worker_brief", "packet", "context_bundle"]
    )
    assert context_bundle_payload["read_policy"]["round_budget_tokens"] == 12000
    assert context_bundle_payload["read_policy"]["deferred_by_budget_context_ids"] == [
        "memory_index",
        "langgraph_runtime",
        "repo_runbook",
        "execution_workbench",
    ]
    assert any(
        entry["context_id"] == "langgraph_runtime"
        for entry in context_bundle_payload["entries"]
    )
    assert any(
        entry["context_id"] == "langgraph_runtime"
        and entry["disclosure_mode"] == "metadata_first"
        and entry["deferred_paths"]
        for entry in context_bundle_payload["entries"]
    )
    assert any(
        entry["context_id"] == "runtime_artifacts"
        and str(resume_anchor_path) in entry["paths"]
        and str(checkpoint_path) in entry["deferred_paths"]
        for entry in context_bundle_payload["entries"]
    )
    validate_instance(load_json(worker_report_path), load_schema(REPORT_SCHEMA_PATH))
    worker_brief = (runtime_root / "tasks" / "task-001" / "worker_brief.md").read_text(
        encoding="utf-8"
    )
    assert "## Compact Resume Anchor" in worker_brief
    assert "## Checkpoint / Resume" in worker_brief
    assert "## Worker Execution" in worker_brief
    assert "Worker profile: code-worker" in worker_brief
    assert "Preferred warm worker profile: (none)" in worker_brief
    assert "Reuse allowed: True" in worker_brief
    assert "## Tool Boundary" in worker_brief
    assert "Tool profile: control_plane_safe_write" in worker_brief
    assert "apply_patch" in worker_brief
    assert "## Dispatch Governance" in worker_brief
    assert "## Context Route" in worker_brief
    assert str(context_bundle_path) in worker_brief
    assert "Read policy: progressive_disclosure" in worker_brief
    assert "Dispatch kind: fresh" in worker_brief
    assert str(resume_anchor_path) in worker_brief
    assert str(checkpoint_path) in worker_brief
    assert dispatch_payload["worker_report_created"] is True
    dispatched_report = load_json(worker_report_path)
    assert dispatched_report["summary"].startswith("待执行窗口填写")
    assert dispatched_report["harness_metadata"]["is_dispatch_draft"] is True
    assert dispatched_report["result_grade"] == "partial"
    assert dispatched_report["next_action_owner"] == "commander"
    assert dispatched_report["continuation_mode"] == "followup"
    checkpoint_path = Path(dispatch_payload["status"]["checkpoint_path"])
    assert checkpoint_path.exists()
    checkpoint_before = load_json(checkpoint_path)
    assert checkpoint_before["task_id"] == "task-001"
    assert checkpoint_before["current_phase"] == "awaiting_report"
    assert checkpoint_before["recommended_action"] == "wait_for_worker_report"
    assert checkpoint_before["controller_handoff"] == "wait_external_result"
    assert checkpoint_before["conversation_stop_required"] is False
    assert checkpoint_before["worker_profile"] == "code-worker"
    assert checkpoint_before["preferred_worker_profile"] is None
    assert checkpoint_before["reuse_allowed"] is True
    assert checkpoint_before["tool_profile"] == "control_plane_safe_write"
    assert checkpoint_before["allowed_tools"] == ["apply_patch", "shell_command"]
    assert checkpoint_before["dispatch_kind"] == "fresh"
    assert checkpoint_before["task_owner"] == "commander"
    assert checkpoint_before["closure_policy"] == "close_when_validated"
    assert checkpoint_before["result_governance"]["continuation_mode"] is None
    assert checkpoint_before["decision_gates"]["summary"] == "no_open_decision_gate"
    assert checkpoint_before["context_budget"]["scope"] == "task_round_context"
    assert checkpoint_before["context_budget"]["estimation_mode"] == "heuristic_non_metered"
    assert checkpoint_before["context_budget"]["round_budget_tokens"] == 12000
    assert checkpoint_before["context_budget"]["open_now_estimated_tokens"] > 0
    assert checkpoint_before["context_budget"]["full_expand_estimated_tokens"] >= checkpoint_before["context_budget"]["open_now_estimated_tokens"]
    assert checkpoint_before["context_budget"]["full_expand_percent_of_round_budget"] >= checkpoint_before["context_budget"]["open_now_percent_of_round_budget"]
    assert checkpoint_before["context_budget"]["router_open_now_estimated_tokens"] >= 0
    assert checkpoint_before["context_budget"]["router_deferred_estimated_tokens"] >= 0
    assert checkpoint_before["context_budget"]["router_budget_overflow"] is True
    assert checkpoint_before["context_budget"]["entries_deferred_by_budget"] == [
        "memory_index",
        "langgraph_runtime",
        "repo_runbook",
        "execution_workbench",
    ]
    resume_anchor_before = load_json(resume_anchor_path)
    assert resume_anchor_before["resume_mode"] == "compact"
    assert resume_anchor_before["key_paths"]["anchor"] == str(resume_anchor_path)
    assert resume_anchor_before["key_paths"]["compaction_event"] == str(compaction_event_path)
    assert resume_anchor_before["read_order"][0] == str(compaction_event_path)
    assert resume_anchor_before["read_order"][1] == str(resume_anchor_path)
    assert resume_anchor_before["read_order"][2] == str(checkpoint_path)
    assert resume_anchor_before["current_phase"] == "awaiting_report"
    assert resume_anchor_before["context_budget"]["round_budget_tokens"] == 12000
    assert resume_anchor_before["context_budget"]["open_now_estimated_tokens"] > 0
    assert resume_anchor_before["context_budget"]["router_budget_overflow"] is True

    ingest_draft = run_script(
        "commander_ingest.py",
        "--runtime-root",
        str(runtime_root),
        "--report",
        str(worker_report_path),
    )
    assert ingest_draft.returncode != 0
    assert "still marked as a dispatch draft" in ingest_draft.stderr

    report_path = tmp_path / "report.json"
    report_path.write_text(
        json.dumps(make_report(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    ingest = run_script(
        "commander_ingest.py",
        "--runtime-root",
        str(runtime_root),
        "--report",
        str(report_path),
    )
    assert ingest.returncode == 0, ingest.stderr
    ingest_payload = json.loads(ingest.stdout)
    assert ingest_payload["worker_status"] == "done"
    candidate_path = runtime_root / "improvements" / "task-001.candidate.json"
    assert candidate_path.exists()
    candidate = load_json(candidate_path)
    validate_instance(candidate, load_schema(IMPROVEMENT_SCHEMA_PATH))
    assert candidate["recommended_layer"] == "script"
    assert (
        candidate["recommended_target"]
        == "commander/transport/scripts/commander_dispatch.py"
    )
    assert ingest_payload["improvement_candidate_path"] == str(candidate_path)
    assert (
        ingest_payload["status"]["improvement_candidate"]["candidate_id"]
        == candidate["candidate_id"]
    )
    assert (
        ingest_payload["status"]["pending_close_worker_attention"]["anchors"][0]["kind"]
        == "trusted_report"
    )
    assert (
        ingest_payload["status"]["pending_close_worker_attention"]["anchors"][1]["kind"]
        == "improvement_candidate"
    )
    assert (
        ingest_payload["status"]["pending_close_worker_attention"]["anchors"][2]["kind"]
        == "controller_handoff"
    )
    checkpoint_after = load_json(checkpoint_path)
    assert checkpoint_after["worker_status"] == "done"
    assert checkpoint_after["current_phase"] == "ready_to_close"
    assert (
        checkpoint_after["recent_trusted_completion"]["summary"]
        == make_report()["summary"]
    )
    assert (
        checkpoint_after["improvement_candidate"]["candidate_id"]
        == candidate["candidate_id"]
    )
    assert checkpoint_after["improvement_candidate"]["recommended_layer"] == "script"
    assert (
        checkpoint_after["pending_close_worker_attention"]["anchors"][1]["candidate_id"]
        == candidate["candidate_id"]
    )
    assert checkpoint_after["result_grade"] == "closed"
    assert checkpoint_after["next_action_owner"] == "commander"
    assert checkpoint_after["continuation_mode"] == "close"
    assert checkpoint_after["decision_gates"]["summary"] == "no_open_decision_gate"
    assert checkpoint_after["event_count"] > checkpoint_before["event_count"]
    assert checkpoint_after["controller_handoff"] == "continue"
    assert checkpoint_after["conversation_stop_required"] is False

    status = run_script(
        "commander_status.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-001",
    )
    assert status.returncode == 0, status.stderr
    status_payload = json.loads(status.stdout)
    assert status_payload["worker_status"] == "done"
    assert status_payload["commander_recommendation"] == "ready_to_close"
    assert status_payload["event_count"] >= 2
    assert status_payload["controller_handoff"] == "continue"
    assert status_payload["conversation_stop_required"] is False
    assert (
        status_payload["improvement_candidate"]["candidate_id"]
        == candidate["candidate_id"]
    )
    assert (
        status_payload["pending_close_worker_attention"]["anchors"][1][
            "recommended_target"
        ]
        == "commander/transport/scripts/commander_dispatch.py"
    )
    assert status_payload["dispatch_kind"] == "fresh"
    assert status_payload["task_owner"] == "commander"
    assert status_payload["result_grade"] == "closed"
    assert status_payload["continuation_mode"] == "close"
    assert status_payload["resume_anchor_path"] == str(resume_anchor_path)
    assert status_payload["host_session"] is None
    assert status_payload["host_runtime"]["session_count"] == 0
    assert status_payload["context_route_summary"]["router_budget_overflow"] is True
    assert status_payload["context_route_summary"]["deferred_by_budget_count"] == 4
    assert status_payload["context_route_summary"]["entries_deferred_by_budget"] == [
        "memory_index",
        "langgraph_runtime",
        "repo_runbook",
        "execution_workbench",
    ]

    agent_state_running = run_script(
        "commander_agent_state.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-001",
        "--agent-id",
        "subagent-001",
        "--nickname",
        "subagent-alpha",
        "--state",
        "running",
    )
    assert agent_state_running.returncode == 0, agent_state_running.stderr
    checkpoint_running = load_json(checkpoint_path)
    assert checkpoint_running["active_subagents"][0]["agent_id"] == "subagent-001"
    assert checkpoint_running["active_subagents"][0]["state"] == "running"
    assert checkpoint_running["active_subagents_summary"]["open_count"] == 1
    assert checkpoint_running["recommended_action"] == "reconcile_active_subagents"
    running_anchor_kinds = [
        anchor["kind"]
        for anchor in checkpoint_running["pending_close_worker_attention"]["anchors"]
    ]
    assert "improvement_candidate" in running_anchor_kinds
    assert "open_subagents" in running_anchor_kinds

    resume = run_script(
        "commander_resume.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-001",
        "--compact",
    )
    assert resume.returncode == 0, resume.stderr
    resume_payload = json.loads(resume.stdout)
    assert resume_payload["task_id"] == "task-001"
    assert resume_payload["resume_mode"] == "compact"
    assert resume_payload["current_phase"] == "ready_to_close"
    assert resume_payload["key_paths"]["anchor"] == str(resume_anchor_path)
    assert resume_payload["key_paths"]["checkpoint"] == str(checkpoint_path)
    assert (
        resume_payload["recent_trusted_completion"]["summary"]
        == make_report()["summary"]
    )
    assert resume_payload["active_subagents_summary"]["open_agent_ids"] == [
        "subagent-001"
    ]
    assert resume_payload["active_subagents_summary"]["open_count"] == 1
    assert resume_payload["recommended_action"] == "reconcile_active_subagents"
    assert resume_payload["controller_handoff"] == "continue"
    assert resume_payload["conversation_stop_required"] is False
    assert (
        resume_payload["improvement_candidate"]["candidate_id"]
        == candidate["candidate_id"]
    )
    assert resume_payload["worker_binding"]["binding_health"] == "unbound"
    assert resume_payload["worker_binding"]["has_binding"] is False

    agent_state_waiting = run_script(
        "commander_agent_state.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-001",
        "--agent-id",
        "subagent-001",
        "--state",
        "completed_waiting_close",
    )
    assert agent_state_waiting.returncode == 0, agent_state_waiting.stderr

    resume_waiting = run_script(
        "commander_resume.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-001",
    )
    assert resume_waiting.returncode == 0, resume_waiting.stderr
    resume_waiting_payload = json.loads(resume_waiting.stdout)
    assert resume_waiting_payload["active_subagents_summary"]["open_agent_ids"] == [
        "subagent-001"
    ]
    assert resume_waiting_payload["recommended_action"] == "reconcile_active_subagents"
    assert (
        resume_waiting_payload["improvement_candidate"]["candidate_id"]
        == candidate["candidate_id"]
    )

    agent_state_closed = run_script(
        "commander_agent_state.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-001",
        "--agent-id",
        "subagent-001",
        "--state",
        "closed",
    )
    assert agent_state_closed.returncode == 0, agent_state_closed.stderr
    checkpoint_closed = load_json(checkpoint_path)
    assert checkpoint_closed["active_subagents"] == []
    assert checkpoint_closed["active_subagents_summary"]["open_count"] == 0

    resume_closed = run_script(
        "commander_resume.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-001",
    )
    assert resume_closed.returncode == 0, resume_closed.stderr
    resume_closed_payload = json.loads(resume_closed.stdout)
    assert resume_closed_payload["active_subagents_summary"]["open_count"] == 0
    assert resume_closed_payload["recommended_action"] == "close_task"
    assert resume_closed_payload["controller_handoff"] == "continue"
    assert resume_closed_payload["conversation_stop_required"] is False
    assert (
        resume_closed_payload["improvement_candidate"]["candidate_id"]
        == candidate["candidate_id"]
    )

    resume_full = run_script(
        "commander_resume.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-001",
        "--full-checkpoint",
    )
    assert resume_full.returncode == 0, resume_full.stderr
    resume_full_payload = json.loads(resume_full.stdout)
    assert resume_full_payload["active_subagents"] == []
    assert (
        resume_full_payload["pending_close_worker_attention"]["anchors"][1][
            "candidate_id"
        ]
        == candidate["candidate_id"]
    )

    catalog_summary = build_task_catalog_summary(runtime_root, limit=3)
    assert catalog_summary["task_count"] == 1
    assert catalog_summary["active_like_task_count"] == 1
    assert catalog_summary["tasks"][0]["task_id"] == "task-001"
    assert catalog_summary["tasks"][0]["current_phase"] == "ready_to_close"
    assert catalog_summary["tasks"][0]["recommended_action"] == "close_task"


def test_dispatch_and_ingest_functions_are_idempotent_for_graph_nodes(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    packet = make_packet()
    report = make_report()
    dispatch_key = "graph-dispatch-task-001"
    ingest_key = "graph-ingest-task-001"

    first_dispatch = dispatch_task(runtime_root, packet, idempotency_key=dispatch_key)
    second_dispatch = dispatch_task(runtime_root, packet, idempotency_key=dispatch_key)

    assert first_dispatch["event_appended"] is True
    assert second_dispatch["event_appended"] is False
    assert first_dispatch["worker_report_created"] is True
    assert second_dispatch["worker_report_created"] is False

    first_ingest = ingest_worker_report(
        runtime_root, report, idempotency_key=ingest_key
    )
    second_ingest = ingest_worker_report(
        runtime_root, report, idempotency_key=ingest_key
    )

    assert first_ingest["report_event_appended"] is True
    assert second_ingest["report_event_appended"] is False
    assert first_ingest["candidate_event_appended"] is True
    assert second_ingest["candidate_event_appended"] is False
    assert first_ingest["candidate_created"] is True
    assert second_ingest["candidate_created"] is False
    assert (
        first_ingest["improvement_candidate_path"]
        == second_ingest["improvement_candidate_path"]
    )
    assert first_ingest["archived_report_path"] == second_ingest["archived_report_path"]

    paths = resolve_task_paths(runtime_root, "task-001")
    events = load_events(paths.events_path)
    event_keys = [
        (event["event_type"], event["detail"].get("idempotency_key"))
        for event in events
        if isinstance(event.get("detail"), dict)
    ]
    assert event_keys.count(("task_dispatched", dispatch_key)) == 1
    assert event_keys.count(("task_report_ingested", ingest_key)) == 1
    assert event_keys.count(("task_improvement_candidate_emitted", ingest_key)) == 1


def test_normalize_active_subagent_update_accepts_wait_agent_payload() -> None:
    payload = {
        "status": {
            "agent-001": {
                "completed": "done",
            }
        },
        "timed_out": False,
    }

    normalized = normalize_active_subagent_update(
        payload,
        fallback_task_id="task-001",
    )

    assert normalized == {
        "agent_id": "agent-001",
        "nickname": "agent-001",
        "state": "completed_waiting_close",
        "task_id": "task-001",
    }


def test_commander_agent_state_accepts_spawn_payload_with_explicit_state(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    packet = make_packet()
    dispatch_task(runtime_root, packet)
    payload_path = tmp_path / "spawn-agent.json"
    write_json_file(
        payload_path,
        {
            "agent_id": "agent-spawned-001",
            "nickname": "Scout",
        },
    )

    run_state = run_script(
        "commander_agent_state.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-001",
        "--state",
        "running",
        "--notification-json",
        str(payload_path),
    )

    assert run_state.returncode == 0, run_state.stderr
    payload = json.loads(run_state.stdout)
    assert payload["agent_id"] == "agent-spawned-001"
    assert payload["state"] == "running"
    assert payload["active_subagents_summary"]["running_count"] == 1


def test_commander_agent_state_accepts_raw_wait_agent_payload(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    packet = make_packet()
    dispatch_task(runtime_root, packet)
    payload_path = tmp_path / "wait-agent.json"
    write_json_file(
        payload_path,
        {
            "status": {
                "agent-complete-001": {
                    "completed": "result ready",
                }
            },
            "timed_out": False,
        },
    )

    run_state = run_script(
        "commander_agent_state.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-001",
        "--notification-json",
        str(payload_path),
    )

    assert run_state.returncode == 0, run_state.stderr
    payload = json.loads(run_state.stdout)
    assert payload["agent_id"] == "agent-complete-001"
    assert payload["state"] == "completed_waiting_close"
    assert payload["active_subagents_summary"]["completed_waiting_close_count"] == 1


def test_close_task_rejects_open_subagents(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    packet = make_packet()
    report = make_report()

    dispatch_task(runtime_root, packet)
    ingest_worker_report(runtime_root, report)

    run_state = run_script(
        "commander_agent_state.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-001",
        "--agent-id",
        "subagent-001",
        "--state",
        "completed_waiting_close",
    )
    assert run_state.returncode == 0, run_state.stderr

    with pytest.raises(
        SchemaValidationError,
        match="still has open sub-agents .*completed_waiting_close=1.*active_subagents_have_completed_results_pending_close",
    ):
        close_task(runtime_root, "task-001")


def test_audit_reports_open_subagent_states(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    packet = make_packet()
    packet["task_id"] = "task-audit-subagents"
    report = make_report()
    report["task_id"] = "task-audit-subagents"

    dispatch_task(runtime_root, packet)
    ingest_worker_report(runtime_root, report)

    run_state_running = run_script(
        "commander_agent_state.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-audit-subagents",
        "--agent-id",
        "subagent-running",
        "--state",
        "running",
    )
    assert run_state_running.returncode == 0, run_state_running.stderr

    run_state_waiting_close = run_script(
        "commander_agent_state.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-audit-subagents",
        "--agent-id",
        "subagent-waiting-close",
        "--state",
        "completed_waiting_close",
    )
    assert run_state_waiting_close.returncode == 0, run_state_waiting_close.stderr

    audit = build_audit_report(runtime_root)
    warning_kinds = {warning["kind"] for warning in audit["warnings"]}
    assert "active_subagents_running" in warning_kinds
    assert "active_subagents_completed_waiting_close" in warning_kinds


def test_ingest_worker_report_rejects_changed_files_under_forbidden_paths(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    packet = make_packet()
    report = make_report()
    report["changed_files"] = ["config/rag.yml"]

    dispatch_task(runtime_root, packet)

    with pytest.raises(SchemaValidationError, match="touches forbidden_path"):
        ingest_worker_report(runtime_root, report)


def test_ingest_worker_report_rejects_changed_files_outside_owned_paths(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    packet = make_packet()
    packet["owned_paths"] = ["commander/transport/scripts"]
    report = make_report()
    report["changed_files"] = ["commander/graph/graph.py"]

    dispatch_task(runtime_root, packet)

    with pytest.raises(SchemaValidationError, match="escapes owned_paths"):
        ingest_worker_report(runtime_root, report)


def test_ingest_worker_report_accepts_changed_files_within_owned_paths(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    packet = make_packet()
    packet["owned_paths"] = ["commander/transport/scripts"]
    report = make_report()

    dispatch_task(runtime_root, packet)
    payload = ingest_worker_report(runtime_root, report)

    assert payload["worker_status"] == "done"
    assert payload["changed_file_governance"]["owned_scope_miss_count"] == 0
    assert payload["changed_file_governance"]["forbidden_hit_count"] == 0


def test_build_resume_anchor_keeps_only_compact_fields() -> None:
    checkpoint = {
        "schema_version": "commander-harness-v1",
        "task_id": "task-compact",
        "title": "Compact resume",
        "current_phase": "ready_to_close",
        "lifecycle_status": "closed",
        "worker_status": "done",
        "controller_handoff": "continue",
        "conversation_stop_required": False,
        "recommended_action": "close_task",
        "next_minimal_action": "Archive the task into runtime history",
        "result_grade": "closed",
        "next_action_owner": "commander",
        "continuation_mode": "close",
        "intent_binding": {
            "last_open_offer": {
                "offer_id": "goal-4",
                "summary": "Continue Goal 4",
                "proposed_action": "Continue Milestone 2 Goal 4",
            },
            "pending_user_reply_target": "goal-4",
            "offer_confirmed": True,
            "latest_user_reply_text": "可以",
            "latest_user_reply_kind": "short_confirmation",
            "resolved_reply_target": "goal-4",
            "binding_reason": "short_confirmation_bound_to_latest_open_offer",
        },
        "pending_decisions": [],
        "blockers": [],
        "recent_trusted_completion": {
            "status": "done",
            "summary": "Trusted completion",
            "report_path": "D:/tmp/report.json",
            "extra": "omit-me",
        },
        "improvement_candidate": {
            "candidate_id": "cand-001",
            "recommended_layer": "script",
            "recommended_target": "commander/transport/scripts/foo.py",
            "status": "candidate",
            "extra": "omit-me",
        },
        "worker_binding": {
            "binding_health": "healthy",
            "leased_worker_ids": ["code-worker-001"],
            "expired_leased_worker_ids": [],
            "state_counts": {"busy": 1},
            "extra": "omit-me",
        },
        "active_subagents_summary": {"open_count": 0},
        "catalog_refresh": {
            "status": "synced",
            "reason": "task_report_ingested",
            "failure_count": 0,
            "extra": "omit-me",
        },
        "context_budget": {
            "scope": "task_round_context",
            "estimation_mode": "heuristic_non_metered",
            "round_budget_tokens": 12000,
            "account_window_budget_tokens": None,
            "open_now_estimated_tokens": 2048,
            "deferred_estimated_tokens": 1024,
            "full_expand_estimated_tokens": 3072,
            "open_now_percent_of_round_budget": 17.07,
            "full_expand_percent_of_round_budget": 25.6,
            "open_now_percent_of_account_window_budget": None,
            "full_expand_percent_of_account_window_budget": None,
        },
        "key_paths": {
            "packet": "D:/tmp/packet.json",
            "report": "D:/tmp/report.json",
            "checkpoint": "D:/tmp/checkpoint.json",
            "status": "D:/tmp/status.json",
            "events": "D:/tmp/events.jsonl",
            "worker_report": "D:/tmp/worker_report.json",
            "worker_brief": "D:/tmp/worker_brief.md",
            "reports_dir": "D:/tmp/reports",
        },
        "active_subagents": [{"agent_id": "subagent-001"}],
        "pending_close_worker_attention": {"anchors": []},
        "updated_at": "2026-04-12T00:00:00Z",
    }

    anchor = build_resume_anchor(checkpoint)

    assert anchor["task_id"] == "task-compact"
    assert anchor["recent_trusted_completion"] == {
        "status": "done",
        "summary": "Trusted completion",
        "report_path": "D:/tmp/report.json",
    }
    assert anchor["improvement_candidate"] == {
        "candidate_id": "cand-001",
        "recommended_layer": "script",
        "recommended_target": "commander/transport/scripts/foo.py",
        "status": "candidate",
    }
    assert anchor["worker_binding"] == {
        "binding_health": "healthy",
        "leased_worker_ids": ["code-worker-001"],
        "expired_leased_worker_ids": [],
        "state_counts": {"busy": 1},
    }
    assert anchor["context_budget"] == {
        "estimation_mode": "heuristic_non_metered",
        "round_budget_tokens": 12000,
        "account_window_budget_tokens": None,
        "open_now_estimated_tokens": 2048,
        "deferred_estimated_tokens": 1024,
        "full_expand_estimated_tokens": 3072,
        "open_now_percent_of_round_budget": 17.07,
        "full_expand_percent_of_round_budget": 25.6,
        "open_now_percent_of_account_window_budget": None,
        "full_expand_percent_of_account_window_budget": None,
    }
    assert "router_open_now_estimated_tokens" not in anchor["context_budget"]
    assert "entries_deferred_by_budget" not in anchor["context_budget"]
    assert anchor["pending_user_reply_target"] == "goal-4"
    assert anchor["offer_confirmed"] is True
    assert anchor["latest_user_reply_text"] == "可以"
    assert anchor["intent_binding"]["resolved_reply_target"] == "goal-4"
    assert anchor["key_paths"] == {
        "packet": "D:/tmp/packet.json",
        "report": "D:/tmp/report.json",
        "checkpoint": "D:/tmp/checkpoint.json",
        "status": "D:/tmp/status.json",
        "events": "D:/tmp/events.jsonl",
        "worker_report": "D:/tmp/worker_report.json",
        "worker_brief": "D:/tmp/worker_brief.md",
    }
    assert "active_subagents" not in anchor
    assert "pending_close_worker_attention" not in anchor


def test_commander_resume_prefers_compaction_event_when_present(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    packet = make_packet()
    packet["task_id"] = "task-compact-preferred"
    packet["title"] = "Prefer compaction event"
    dispatch_task(runtime_root, packet)

    paths = resolve_task_paths(runtime_root, "task-compact-preferred")
    artifact_path = tmp_path / "compaction-artifact.json"
    artifact_path.write_text("{}", encoding="utf-8")
    write_json(
        paths.compaction_event_path,
        {
            "schema_version": "commander-compaction-event-v1",
            "resume_mode": "compaction_event",
            "event_id": "evt-compact-001",
            "recorded_at": "2026-04-13T00:00:00Z",
            "task_id": "task-compact-preferred",
            "source": "test-suite",
            "trigger": "resume-preference",
            "driver_status": "waiting_external_result",
            "stop_reason": "wait_timeout_or_missing_report",
            "summary": "Prefer this compaction event over resume_anchor.",
            "artifact": {
                "kind": "unit_test_payload",
                "path": str(artifact_path),
            },
            "resume_entry": {
                "task_id": "task-compact-preferred",
                "compact_anchor_path": str(paths.compaction_event_path),
                "resume_anchor_path": str(paths.resume_anchor_path),
                "checkpoint_path": str(paths.checkpoint_path),
            },
            "key_paths": {
                "compaction_event": str(paths.compaction_event_path),
                "checkpoint": str(paths.checkpoint_path),
            },
        },
    )

    result = run_script(
        "commander_resume.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-compact-preferred",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["resume_mode"] == "compaction_event"
    assert payload["summary"] == "Prefer this compaction event over resume_anchor."
    assert payload["source"] == "test-suite"
    assert payload["event_id"] == "evt-compact-001"


def test_refresh_status_persists_intent_binding_across_runtime_artifacts(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    packet = make_packet()
    packet["task_id"] = "task-intent-binding"
    packet["title"] = "Persist intent binding"
    dispatch_task(runtime_root, packet)

    paths = resolve_task_paths(runtime_root, "task-intent-binding")
    snapshot = refresh_status(
        paths,
        intent_binding_update={
            "last_open_offer": {
                "offer_id": "milestone-2-goal-4",
                "summary": "Continue Milestone 2 Goal 4",
                "proposed_action": "Finish the next orchestration slice",
            },
            "latest_user_reply_text": "可以",
        },
    )

    assert snapshot["pending_user_reply_target"] == "milestone-2-goal-4"
    assert snapshot["offer_confirmed"] is True
    assert (
        snapshot["intent_binding"]["binding_reason"]
        == "short_confirmation_bound_to_latest_open_offer"
    )

    checkpoint = load_json(paths.checkpoint_path)
    status_payload = load_json(paths.status_path)
    resume_payload = load_json(paths.resume_anchor_path)
    for payload in (checkpoint, status_payload, resume_payload):
        assert payload["pending_user_reply_target"] == "milestone-2-goal-4"
        assert payload["offer_confirmed"] is True
        assert payload["latest_user_reply_text"] == "可以"
        assert (
            payload["intent_binding"]["last_open_offer"]["offer_id"]
            == "milestone-2-goal-4"
        )


def test_worker_pool_cli_acquire_release_reuse_smoke(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"

    acquire_first = run_script(
        "commander_worker_pool.py",
        "--runtime-root",
        str(runtime_root),
        "acquire",
        "--task-id",
        "task-001",
        "--worker-profile",
        "code-worker",
        "--preferred-worker-profile",
        "code-worker",
        "--tool-profile",
        "control_plane_safe_write",
        "--allowed-tool",
        "apply_patch",
        "--allowed-tool",
        "shell_command",
    )
    assert acquire_first.returncode == 0, acquire_first.stderr
    acquire_first_payload = json.loads(acquire_first.stdout)
    assert acquire_first_payload["created"] is True
    assert acquire_first_payload["reused"] is False
    first_worker = acquire_first_payload["worker"]
    assert first_worker["state"] == "busy"
    assert first_worker["acquire_count"] == 1
    assert first_worker["reuse_count"] == 0
    assert first_worker["lease_duration_seconds"] == 1800
    assert first_worker["lease_expires_at"] is not None
    assert first_worker["heartbeat_at"] is not None

    heartbeat_first = run_script(
        "commander_worker_pool.py",
        "--runtime-root",
        str(runtime_root),
        "heartbeat",
        "--worker-id",
        acquire_first_payload["worker_id"],
        "--lease-seconds",
        "7200",
    )
    assert heartbeat_first.returncode == 0, heartbeat_first.stderr
    heartbeat_first_payload = json.loads(heartbeat_first.stdout)
    assert heartbeat_first_payload["worker"]["lease_duration_seconds"] == 7200
    assert heartbeat_first_payload["worker"]["heartbeat_at"] is not None
    assert heartbeat_first_payload["worker"]["lease_expires_at"] is not None

    release_first = run_script(
        "commander_worker_pool.py",
        "--runtime-root",
        str(runtime_root),
        "release",
        "--worker-id",
        acquire_first_payload["worker_id"],
        "--state",
        "warm_idle",
    )
    assert release_first.returncode == 0, release_first.stderr
    release_first_payload = json.loads(release_first.stdout)
    assert release_first_payload["worker"]["state"] == "warm_idle"
    assert release_first_payload["worker"]["current_task_id"] is None
    assert release_first_payload["worker"]["lease_expires_at"] is None

    acquire_second = run_script(
        "commander_worker_pool.py",
        "--runtime-root",
        str(runtime_root),
        "acquire",
        "--task-id",
        "task-002",
        "--worker-profile",
        "code-worker",
        "--preferred-worker-profile",
        "code-worker",
        "--tool-profile",
        "control_plane_safe_write",
        "--allowed-tool",
        "apply_patch",
    )
    assert acquire_second.returncode == 0, acquire_second.stderr
    acquire_second_payload = json.loads(acquire_second.stdout)
    assert acquire_second_payload["created"] is False
    assert acquire_second_payload["reused"] is True
    assert acquire_second_payload["worker_id"] == acquire_first_payload["worker_id"]
    assert acquire_second_payload["worker"]["state"] == "busy"
    assert acquire_second_payload["worker"]["acquire_count"] == 2
    assert acquire_second_payload["worker"]["reuse_count"] == 1
    assert acquire_second_payload["worker"]["current_task_id"] == "task-002"
    assert acquire_second_payload["worker"]["lease_duration_seconds"] == 1800

    release_waiting = run_script(
        "commander_worker_pool.py",
        "--runtime-root",
        str(runtime_root),
        "release",
        "--worker-id",
        acquire_second_payload["worker_id"],
        "--state",
        "completed_waiting_close",
    )
    assert release_waiting.returncode == 0, release_waiting.stderr
    release_waiting_payload = json.loads(release_waiting.stdout)
    assert release_waiting_payload["worker"]["state"] == "completed_waiting_close"
    assert release_waiting_payload["worker"]["current_task_id"] == "task-002"
    assert release_waiting_payload["worker"]["lease_expires_at"] is None

    acquire_verifier = run_script(
        "commander_worker_pool.py",
        "--runtime-root",
        str(runtime_root),
        "acquire",
        "--task-id",
        "task-003",
        "--worker-profile",
        "verifier-worker",
        "--tool-profile",
        "verification_only",
        "--allowed-tool",
        "shell_command",
        "--no-reuse",
    )
    assert acquire_verifier.returncode == 0, acquire_verifier.stderr
    acquire_verifier_payload = json.loads(acquire_verifier.stdout)
    assert acquire_verifier_payload["created"] is True
    assert acquire_verifier_payload["reused"] is False
    assert acquire_verifier_payload["worker"]["worker_profile"] == "verifier-worker"

    pool_status = run_script(
        "commander_worker_pool.py",
        "--runtime-root",
        str(runtime_root),
        "status",
    )
    assert pool_status.returncode == 0, pool_status.stderr
    pool_status_payload = json.loads(pool_status.stdout)
    assert pool_status_payload["registry"]["worker_count"] == 2
    assert (
        pool_status_payload["registry"]["state_counts"]["completed_waiting_close"] == 1
    )
    assert pool_status_payload["registry"]["state_counts"]["busy"] == 1

    verifier_status = run_script(
        "commander_worker_pool.py",
        "--runtime-root",
        str(runtime_root),
        "status",
        "--worker-profile",
        "verifier-worker",
    )
    assert verifier_status.returncode == 0, verifier_status.stderr
    verifier_status_payload = json.loads(verifier_status.stdout)
    assert verifier_status_payload["worker_count"] == 1
    assert verifier_status_payload["workers"][0]["worker_profile"] == "verifier-worker"


def test_worker_pool_operations_clear_stale_lock_files(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    locks_dir = runtime_root / "workers" / "locks"
    write_json_file(
        locks_dir / "pool.lock",
        {
            "schema_version": "commander-harness-v1",
            "scope": "worker_pool",
            "owner_id": "stale-owner",
            "acquired_at": "2026-04-11T00:00:00Z",
            "stale_after_seconds": 30,
            "expires_at": "2026-04-11T00:00:30Z",
        },
    )

    acquire = run_script(
        "commander_worker_pool.py",
        "--runtime-root",
        str(runtime_root),
        "acquire",
        "--task-id",
        "task-locks",
        "--worker-profile",
        "code-worker",
        "--preferred-worker-profile",
        "code-worker",
        "--tool-profile",
        "control_plane_safe_write",
        "--allowed-tool",
        "apply_patch",
    )
    assert acquire.returncode == 0, acquire.stderr
    acquire_payload = json.loads(acquire.stdout)
    worker_id = acquire_payload["worker_id"]
    assert (locks_dir / "pool.lock").exists() is False

    write_json_file(
        locks_dir / f"{worker_id}.lock",
        {
            "schema_version": "commander-harness-v1",
            "scope": f"worker_slot:{worker_id}",
            "owner_id": "stale-owner",
            "acquired_at": "2026-04-11T00:00:00Z",
            "stale_after_seconds": 30,
            "expires_at": "2026-04-11T00:00:30Z",
        },
    )
    release = run_script(
        "commander_worker_pool.py",
        "--runtime-root",
        str(runtime_root),
        "release",
        "--worker-id",
        worker_id,
        "--state",
        "warm_idle",
    )
    assert release.returncode == 0, release.stderr
    assert (locks_dir / f"{worker_id}.lock").exists() is False


def test_worker_pool_cli_reconcile_marks_orphaned_awaiting_report_task_stale(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    dispatch = run_script(
        "commander_dispatch.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-orphan",
        "--title",
        "Expire worker before report",
        "--goal",
        "Exercise stale worker reclaim for awaiting report tasks",
        "--must-read",
        "README.md",
        "--bound",
        "transport only",
        "--validation",
        "pytest",
        "--forbidden-path",
        "config/rag.yml",
    )
    assert dispatch.returncode == 0, dispatch.stderr

    acquire = run_script(
        "commander_worker_pool.py",
        "--runtime-root",
        str(runtime_root),
        "acquire",
        "--task-id",
        "task-orphan",
        "--worker-profile",
        "code-worker",
        "--preferred-worker-profile",
        "code-worker",
        "--tool-profile",
        "control_plane_safe_write",
        "--allowed-tool",
        "apply_patch",
    )
    assert acquire.returncode == 0, acquire.stderr
    acquire_payload = json.loads(acquire.stdout)
    worker_id = acquire_payload["worker_id"]

    status_before = run_script(
        "commander_status.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-orphan",
    )
    assert status_before.returncode == 0, status_before.stderr
    status_before_payload = json.loads(status_before.stdout)
    assert status_before_payload["current_phase"] == "awaiting_report"
    assert status_before_payload["worker_binding"]["binding_health"] == "healthy"
    assert status_before_payload["worker_binding"]["leased_worker_count"] == 1

    slot_path = runtime_root / "workers" / "slots" / f"{worker_id}.json"
    slot = load_json(slot_path)
    slot["lease_expires_at"] = "2026-04-11T00:00:00Z"
    slot["heartbeat_at"] = "2026-04-11T00:00:00Z"
    slot["updated_at"] = "2026-04-11T00:00:00Z"
    write_json_file(slot_path, slot)

    dry_run = run_script(
        "commander_worker_pool.py",
        "--runtime-root",
        str(runtime_root),
        "reconcile",
        "--dry-run",
        "--worker-id",
        worker_id,
    )
    assert dry_run.returncode == 0, dry_run.stderr
    dry_run_payload = json.loads(dry_run.stdout)
    assert dry_run_payload["changed_count"] == 1
    assert dry_run_payload["stale_worker_ids"] == [worker_id]
    assert dry_run_payload["orphan_task_ids"] == ["task-orphan"]
    assert (
        dry_run_payload["workers"][0]["action"]
        == "reclaim_expired_worker_and_mark_task_stale"
    )
    assert dry_run_payload["workers"][0]["task_marked_stale"] is True
    assert dry_run_payload["workers"][0]["release_to"] == "closed"

    status_after_dry_run = run_script(
        "commander_status.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-orphan",
    )
    assert status_after_dry_run.returncode == 0, status_after_dry_run.stderr
    status_after_dry_run_payload = json.loads(status_after_dry_run.stdout)
    assert status_after_dry_run_payload["lifecycle_status"] == "active"
    assert status_after_dry_run_payload["current_phase"] == "awaiting_report"

    reconcile = run_script(
        "commander_worker_pool.py",
        "--runtime-root",
        str(runtime_root),
        "reconcile",
        "--worker-id",
        worker_id,
    )
    assert reconcile.returncode == 0, reconcile.stderr
    reconcile_payload = json.loads(reconcile.stdout)
    assert reconcile_payload["changed_count"] == 1
    assert reconcile_payload["reclaimed_worker_ids"] == [worker_id]
    assert reconcile_payload["stale_worker_ids"] == [worker_id]
    assert reconcile_payload["orphan_task_ids"] == ["task-orphan"]
    assert reconcile_payload["workers"][0]["state"] == "closed"
    assert reconcile_payload["workers"][0]["task_marked_stale"] is True

    slot_after = load_json(slot_path)
    assert slot_after["state"] == "closed"
    assert slot_after["current_task_id"] is None

    status_after = run_script(
        "commander_status.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-orphan",
    )
    assert status_after.returncode == 0, status_after.stderr
    status_after_payload = json.loads(status_after.stdout)
    assert status_after_payload["lifecycle_status"] == "stale"
    assert status_after_payload["current_phase"] == "stale"
    assert status_after_payload["worker_binding"]["binding_health"] == "unbound"
    assert status_after_payload["worker_binding"]["worker_count"] == 0

    reconcile_again = run_script(
        "commander_worker_pool.py",
        "--runtime-root",
        str(runtime_root),
        "reconcile",
        "--worker-id",
        worker_id,
    )
    assert reconcile_again.returncode == 0, reconcile_again.stderr
    reconcile_again_payload = json.loads(reconcile_again.stdout)
    assert reconcile_again_payload["changed_count"] == 0
    assert reconcile_again_payload["reclaimed_worker_ids"] == []
    assert reconcile_again_payload["orphan_task_ids"] == []


def test_worker_pool_cli_reconcile_releases_expired_completed_waiting_close_worker(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    dispatch = run_script(
        "commander_dispatch.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-ready-close",
        "--title",
        "Reclaim completed worker",
        "--goal",
        "Exercise completed_waiting_close reclaim without staling the task",
        "--must-read",
        "README.md",
        "--bound",
        "transport only",
        "--validation",
        "pytest",
        "--forbidden-path",
        "config/rag.yml",
    )
    assert dispatch.returncode == 0, dispatch.stderr

    report = make_report()
    report["task_id"] = "task-ready-close"
    report_path = tmp_path / "task-ready-close-report.json"
    write_json_file(report_path, report)

    ingest = run_script(
        "commander_ingest.py",
        "--runtime-root",
        str(runtime_root),
        "--report",
        str(report_path),
    )
    assert ingest.returncode == 0, ingest.stderr

    acquire = run_script(
        "commander_worker_pool.py",
        "--runtime-root",
        str(runtime_root),
        "acquire",
        "--task-id",
        "task-ready-close",
        "--worker-profile",
        "code-worker",
        "--preferred-worker-profile",
        "code-worker",
        "--tool-profile",
        "control_plane_safe_write",
        "--allowed-tool",
        "apply_patch",
    )
    assert acquire.returncode == 0, acquire.stderr
    worker_id = json.loads(acquire.stdout)["worker_id"]

    release = run_script(
        "commander_worker_pool.py",
        "--runtime-root",
        str(runtime_root),
        "release",
        "--worker-id",
        worker_id,
        "--state",
        "completed_waiting_close",
    )
    assert release.returncode == 0, release.stderr

    slot_path = runtime_root / "workers" / "slots" / f"{worker_id}.json"
    slot = load_json(slot_path)
    slot["lease_expires_at"] = "2026-04-11T00:00:00Z"
    slot["heartbeat_at"] = "2026-04-11T00:00:00Z"
    slot["updated_at"] = "2026-04-11T00:00:00Z"
    write_json_file(slot_path, slot)

    reconcile = run_script(
        "commander_worker_pool.py",
        "--runtime-root",
        str(runtime_root),
        "reconcile",
        "--worker-id",
        worker_id,
    )
    assert reconcile.returncode == 0, reconcile.stderr
    reconcile_payload = json.loads(reconcile.stdout)
    assert reconcile_payload["changed_count"] == 1
    assert reconcile_payload["stale_worker_ids"] == [worker_id]
    assert reconcile_payload["orphan_task_ids"] == []
    assert reconcile_payload["workers"][0]["action"] == "reclaim_expired_worker"
    assert reconcile_payload["workers"][0]["release_to"] == "warm_idle"
    assert reconcile_payload["workers"][0]["state"] == "warm_idle"
    assert reconcile_payload["workers"][0]["task_marked_stale"] is False

    slot_after = load_json(slot_path)
    assert slot_after["state"] == "warm_idle"
    assert slot_after["current_task_id"] is None

    status_after = run_script(
        "commander_status.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-ready-close",
    )
    assert status_after.returncode == 0, status_after.stderr
    status_after_payload = json.loads(status_after.stdout)
    assert status_after_payload["lifecycle_status"] == "active"
    assert status_after_payload["current_phase"] == "ready_to_close"
    assert status_after_payload["worker_binding"]["binding_health"] == "unbound"
    assert status_after_payload["worker_binding"]["worker_count"] == 0


def test_worker_pool_cli_reconcile_arbitrates_duplicate_leased_workers(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    dispatch = run_script(
        "commander_dispatch.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-duplicate",
        "--title",
        "Duplicate leased workers",
        "--goal",
        "Exercise duplicate leased worker arbitration",
        "--must-read",
        "README.md",
        "--bound",
        "transport only",
        "--validation",
        "pytest",
        "--forbidden-path",
        "config/rag.yml",
    )
    assert dispatch.returncode == 0, dispatch.stderr

    acquire_first = run_script(
        "commander_worker_pool.py",
        "--runtime-root",
        str(runtime_root),
        "acquire",
        "--task-id",
        "task-duplicate",
        "--worker-profile",
        "code-worker",
        "--preferred-worker-profile",
        "code-worker",
        "--tool-profile",
        "control_plane_safe_write",
        "--allowed-tool",
        "apply_patch",
        "--no-reuse",
    )
    assert acquire_first.returncode == 0, acquire_first.stderr
    worker_first = json.loads(acquire_first.stdout)["worker_id"]

    acquire_second = run_script(
        "commander_worker_pool.py",
        "--runtime-root",
        str(runtime_root),
        "acquire",
        "--task-id",
        "task-duplicate",
        "--worker-profile",
        "code-worker",
        "--preferred-worker-profile",
        "code-worker",
        "--tool-profile",
        "control_plane_safe_write",
        "--allowed-tool",
        "apply_patch",
        "--no-reuse",
    )
    assert acquire_second.returncode == 0, acquire_second.stderr
    worker_second = json.loads(acquire_second.stdout)["worker_id"]

    status_before = run_script(
        "commander_status.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-duplicate",
    )
    assert status_before.returncode == 0, status_before.stderr
    status_before_payload = json.loads(status_before.stdout)
    assert (
        status_before_payload["worker_binding"]["binding_health"]
        == "multiple_leased_workers"
    )
    assert status_before_payload["worker_binding"]["leased_worker_count"] == 2
    assert (
        status_before_payload["worker_binding"]["canonical_worker_id"] == worker_second
    )
    assert status_before_payload["worker_binding"]["duplicate_worker_ids"] == [
        worker_first
    ]

    audit_before = run_script(
        "commander_audit.py",
        "--runtime-root",
        str(runtime_root),
        "--task-card-path",
        str(tmp_path / "task-card-duplicate.md"),
    )
    assert audit_before.returncode == 0, audit_before.stderr
    audit_before_payload = json.loads(audit_before.stdout)
    warning_kinds = {item["kind"] for item in audit_before_payload["warnings"]}
    assert "worker_pool_duplicate_bindings" in warning_kinds
    assert audit_before_payload["runtime_duplicate_binding_task_ids"] == [
        "task-duplicate"
    ]

    reconcile = run_script(
        "commander_worker_pool.py",
        "--runtime-root",
        str(runtime_root),
        "reconcile",
    )
    assert reconcile.returncode == 0, reconcile.stderr
    reconcile_payload = json.loads(reconcile.stdout)
    assert reconcile_payload["changed_count"] == 1
    assert reconcile_payload["duplicate_binding_task_ids"] == ["task-duplicate"]
    duplicate_worker_result = next(
        item
        for item in reconcile_payload["workers"]
        if item["action"] == "reclaim_duplicate_leased_worker"
    )
    assert duplicate_worker_result["worker_id"] == worker_first
    assert duplicate_worker_result["canonical_worker_id"] == worker_second
    assert duplicate_worker_result["release_to"] == "closed"

    status_after = run_script(
        "commander_status.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-duplicate",
    )
    assert status_after.returncode == 0, status_after.stderr
    status_after_payload = json.loads(status_after.stdout)
    assert status_after_payload["worker_binding"]["binding_health"] == "healthy"
    assert status_after_payload["worker_binding"]["leased_worker_count"] == 1
    assert (
        status_after_payload["worker_binding"]["canonical_worker_id"] == worker_second
    )
    assert status_after_payload["worker_binding"]["duplicate_worker_ids"] == []
    assert status_after_payload["current_phase"] == "awaiting_report"

    first_slot = load_json(runtime_root / "workers" / "slots" / f"{worker_first}.json")
    second_slot = load_json(
        runtime_root / "workers" / "slots" / f"{worker_second}.json"
    )
    assert first_slot["state"] == "closed"
    assert first_slot["current_task_id"] is None
    assert second_slot["state"] == "busy"
    assert second_slot["current_task_id"] == "task-duplicate"


def test_worker_pool_cli_rejects_invalid_lifecycle_transitions(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    acquire = run_script(
        "commander_worker_pool.py",
        "--runtime-root",
        str(runtime_root),
        "acquire",
        "--task-id",
        "task-transition",
        "--worker-profile",
        "code-worker",
        "--preferred-worker-profile",
        "code-worker",
        "--tool-profile",
        "control_plane_safe_write",
        "--allowed-tool",
        "apply_patch",
    )
    assert acquire.returncode == 0, acquire.stderr
    worker_id = json.loads(acquire.stdout)["worker_id"]

    release = run_script(
        "commander_worker_pool.py",
        "--runtime-root",
        str(runtime_root),
        "release",
        "--worker-id",
        worker_id,
        "--state",
        "warm_idle",
    )
    assert release.returncode == 0, release.stderr

    heartbeat_invalid = run_script(
        "commander_worker_pool.py",
        "--runtime-root",
        str(runtime_root),
        "heartbeat",
        "--worker-id",
        worker_id,
    )
    assert heartbeat_invalid.returncode != 0
    assert "cannot heartbeat from state" in heartbeat_invalid.stderr

    release_invalid = run_script(
        "commander_worker_pool.py",
        "--runtime-root",
        str(runtime_root),
        "release",
        "--worker-id",
        worker_id,
        "--state",
        "warm_idle",
    )
    assert release_invalid.returncode != 0
    assert "cannot release from state" in release_invalid.stderr


def test_user_decision_report_requests_pause_for_user(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    dispatch = run_script(
        "commander_dispatch.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-user-decision",
        "--title",
        "Need user choice",
        "--goal",
        "Exercise pause for user decision",
        "--must-read",
        "README.md",
        "--bound",
        "transport only",
        "--validation",
        "pytest",
        "--forbidden-path",
        "config/rag.yml",
    )
    assert dispatch.returncode == 0, dispatch.stderr

    report = make_report()
    report["task_id"] = "task-user-decision"
    report["needs_commander_decision"] = False
    report["needs_user_decision"] = True
    report["user_decision_reason"] = "Need the user to choose rollback or continue."
    report["recommended_next_step"] = (
        "Pause and ask the user to choose rollback or continue."
    )
    report_path = tmp_path / "user-decision-report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    ingest = run_script(
        "commander_ingest.py",
        "--runtime-root",
        str(runtime_root),
        "--report",
        str(report_path),
    )
    assert ingest.returncode == 0, ingest.stderr
    ingest_payload = json.loads(ingest.stdout)
    assert ingest_payload["status"]["controller_handoff"] == "request_user_decision"
    assert ingest_payload["status"]["conversation_stop_required"] is True
    assert (
        ingest_payload["status"]["conversation_stop_reason"]
        == "explicit_user_decision_required"
    )

    checkpoint_path = Path(ingest_payload["status"]["checkpoint_path"])
    checkpoint = load_json(checkpoint_path)
    assert checkpoint["current_phase"] == "pending_user"
    assert checkpoint["recommended_action"] == "request_user_decision"
    assert checkpoint["controller_handoff"] == "request_user_decision"
    assert checkpoint["conversation_stop_required"] is True
    assert (
        checkpoint["next_minimal_action"]
        == "Need the user to choose rollback or continue."
    )


def test_ready_for_user_delivery_report_requests_final_handoff(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    dispatch = run_script(
        "commander_dispatch.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-final-delivery",
        "--title",
        "Ready for final delivery",
        "--goal",
        "Exercise final return to user",
        "--must-read",
        "README.md",
        "--bound",
        "transport only",
        "--validation",
        "pytest",
        "--forbidden-path",
        "config/rag.yml",
    )
    assert dispatch.returncode == 0, dispatch.stderr

    report = make_report()
    report["task_id"] = "task-final-delivery"
    report["ready_for_user_delivery"] = True
    report["recommended_next_step"] = "Return the final result to the user."
    report_path = tmp_path / "final-delivery-report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    ingest = run_script(
        "commander_ingest.py",
        "--runtime-root",
        str(runtime_root),
        "--report",
        str(report_path),
    )
    assert ingest.returncode == 0, ingest.stderr
    ingest_payload = json.loads(ingest.stdout)
    assert ingest_payload["status"]["controller_handoff"] == "return_final_result"
    assert ingest_payload["status"]["conversation_stop_required"] is True
    assert (
        ingest_payload["status"]["conversation_stop_reason"]
        == "deliverable_ready_for_user"
    )

    checkpoint_path = Path(ingest_payload["status"]["checkpoint_path"])
    checkpoint = load_json(checkpoint_path)
    assert checkpoint["current_phase"] == "ready_for_user_delivery"
    assert checkpoint["recommended_action"] == "return_final_result"
    assert checkpoint["controller_handoff"] == "return_final_result"
    assert checkpoint["conversation_stop_required"] is True
    assert checkpoint["next_minimal_action"] == "Return the final result to the user"


def test_task_catalog_reads_minimal_summary_from_task_snapshots(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"

    alpha_dir = runtime_root / "tasks" / "task-alpha"
    write_json_file(
        alpha_dir / "packet.json",
        {
            "schema_version": "commander-harness-v1",
            "task_id": "task-alpha",
            "title": "Alpha task",
            "goal": "Stay as a file-backed summary only",
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
    write_json_file(
        alpha_dir / "worker_report.json", build_worker_report_draft("task-alpha")
    )
    write_json_file(
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
    write_json_file(
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
    write_event_log(
        alpha_dir / "events.jsonl",
        [
            {
                "event_id": "alpha-event-1",
                "task_id": "task-alpha",
                "event_type": "task_dispatched",
                "timestamp": "2026-04-12T10:00:05Z",
                "detail": {
                    "payload": "x" * 128,
                },
            }
        ],
    )

    beta_dir = runtime_root / "tasks" / "task-beta"
    write_json_file(
        beta_dir / "packet.json",
        {
            "schema_version": "commander-harness-v1",
            "task_id": "task-beta",
            "title": "Beta task",
            "goal": "Expose a completed report in the catalog",
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
    write_json_file(
        beta_dir / "worker_report.json", build_worker_report_draft("task-beta")
    )
    write_json_file(
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
    write_json_file(
        beta_dir / "status.json",
        {
            "schema_version": "commander-harness-v1",
            "task_id": "task-beta",
            "title": "Beta task",
            "current_phase": "ready_to_close",
            "recommended_action": "close_task",
            "next_minimal_action": "Review the report and close the task",
            "worker_profile": "analysis-worker",
            "preferred_worker_profile": None,
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
    write_json_file(
        beta_dir / "checkpoint.json",
        {
            "schema_version": "commander-harness-v1",
            "task_id": "task-beta",
            "title": "Beta task",
            "current_phase": "ready_to_close",
            "recommended_action": "close_task",
            "next_minimal_action": "Review the report and close the task",
            "worker_profile": "analysis-worker",
            "preferred_worker_profile": None,
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
    write_event_log(
        beta_dir / "events.jsonl",
        [
            {
                "event_id": "beta-event-1",
                "task_id": "task-beta",
                "event_type": "task_dispatched",
                "timestamp": "2026-04-12T10:05:05Z",
                "detail": {"payload": "y" * 128},
            },
            {
                "event_id": "beta-event-2",
                "task_id": "task-beta",
                "event_type": "task_report_ingested",
                "timestamp": "2026-04-12T10:10:05Z",
                "detail": {"report_digest": "z" * 128},
            },
        ],
    )

    catalog = load_task_catalog(runtime_root)
    assert catalog["schema_version"] == "commander-task-catalog-v1"
    assert catalog["task_count"] == 2
    assert catalog["runtime_root"] == str(runtime_root.resolve())

    entries_by_task_id = {entry["task_id"]: entry for entry in catalog["tasks"]}
    assert entries_by_task_id["task-alpha"]["has_report"] is False
    assert (
        entries_by_task_id["task-alpha"]["controller_handoff"] == "wait_external_result"
    )
    assert entries_by_task_id["task-alpha"]["worker_profile"] == "code-worker"
    assert entries_by_task_id["task-alpha"]["updated_at"] == "2026-04-12T10:00:10Z"
    assert entries_by_task_id["task-alpha"]["event_count"] == 1
    assert entries_by_task_id["task-alpha"]["last_event_type"] == "task_dispatched"
    assert entries_by_task_id["task-alpha"]["lifecycle_status"] == "active"
    assert entries_by_task_id["task-alpha"]["cleanup_eligible"] is False
    assert "detail" not in entries_by_task_id["task-alpha"]

    assert entries_by_task_id["task-beta"]["has_report"] is True
    assert entries_by_task_id["task-beta"]["controller_handoff"] == "continue"
    assert entries_by_task_id["task-beta"]["worker_profile"] == "analysis-worker"
    assert entries_by_task_id["task-beta"]["updated_at"] == "2026-04-12T10:10:10Z"
    assert entries_by_task_id["task-beta"]["event_count"] == 2
    assert entries_by_task_id["task-beta"]["last_event_type"] == "task_report_ingested"
    assert entries_by_task_id["task-beta"]["status"] == "done"
    assert entries_by_task_id["task-beta"]["lifecycle_status"] == "active"
    assert "summary" not in entries_by_task_id["task-beta"]

    filtered = run_script(
        "commander_task_catalog.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-beta",
    )
    assert filtered.returncode == 0, filtered.stderr
    filtered_payload = json.loads(filtered.stdout)
    assert filtered_payload["task_count"] == 1
    assert filtered_payload["tasks"][0]["task_id"] == "task-beta"
    assert filtered_payload["tasks"][0]["has_report"] is True
    assert filtered_payload["tasks"][0]["lifecycle_status"] == "active"


def test_close_and_archive_cli_update_runtime_lifecycle_and_catalog(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    dispatch = run_script(
        "commander_dispatch.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-close-archive",
        "--title",
        "Close and archive",
        "--goal",
        "Exercise lifecycle closure and archive",
        "--must-read",
        "README.md",
        "--bound",
        "transport only",
        "--validation",
        "pytest",
    )
    assert dispatch.returncode == 0, dispatch.stderr

    report = make_report()
    report["task_id"] = "task-close-archive"
    report_path = tmp_path / "close-archive-report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    ingest = run_script(
        "commander_ingest.py",
        "--runtime-root",
        str(runtime_root),
        "--report",
        str(report_path),
    )
    assert ingest.returncode == 0, ingest.stderr

    close_result = run_script(
        "commander_close.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-close-archive",
        "--reason",
        "validated_and_ready_to_archive",
    )
    assert close_result.returncode == 0, close_result.stderr
    close_payload = json.loads(close_result.stdout)
    assert close_payload["changed"] is True
    assert close_payload["status"]["lifecycle_status"] == "closed"
    assert close_payload["status"]["current_phase"] == "closed"
    assert close_payload["status"]["commander_recommendation"] == "closed"
    assert close_payload["status"]["recommended_action"] == "archive_task"
    assert (
        close_payload["status"]["next_minimal_action"]
        == "Archive the task into runtime history"
    )

    archive_result = run_script(
        "commander_archive.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-close-archive",
        "--reason",
        "archived_after_commander_review",
    )
    assert archive_result.returncode == 0, archive_result.stderr
    archive_payload = json.loads(archive_result.stdout)
    assert archive_payload["changed"] is True
    assert archive_payload["status"]["lifecycle_status"] == "archived"
    assert archive_payload["status"]["current_phase"] == "archived"
    assert archive_payload["status"]["commander_recommendation"] == "archived"
    assert (
        archive_payload["status"]["recommended_action"] == "retain_until_cleanup_window"
    )
    assert archive_payload["status"]["cleanup_eligible"] is False

    lifecycle_path = Path(archive_payload["lifecycle_path"])
    assert lifecycle_path.exists()
    lifecycle = load_json(lifecycle_path)
    assert lifecycle["lifecycle_status"] == "archived"
    assert lifecycle["closed_at"] is not None
    assert lifecycle["archived_at"] is not None

    catalog_result = run_script(
        "commander_task_catalog.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-close-archive",
    )
    assert catalog_result.returncode == 0, catalog_result.stderr
    catalog_payload = json.loads(catalog_result.stdout)
    entry = catalog_payload["tasks"][0]
    assert entry["task_id"] == "task-close-archive"
    assert entry["status"] == "archived"
    assert entry["lifecycle_status"] == "archived"
    assert entry["has_report"] is True
    assert entry["cleanup_eligible"] is False


def test_reconcile_marks_stale_then_reopens_when_new_activity_arrives(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    dispatch = run_script(
        "commander_dispatch.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-stale-reconcile",
        "--title",
        "Stale reconcile",
        "--goal",
        "Exercise stale marking and reopen",
        "--must-read",
        "README.md",
        "--bound",
        "transport only",
        "--validation",
        "pytest",
    )
    assert dispatch.returncode == 0, dispatch.stderr

    task_dir = runtime_root / "tasks" / "task-stale-reconcile"
    packet_path = task_dir / "packet.json"
    lifecycle_path = task_dir / "lifecycle.json"
    events_path = task_dir / "events.jsonl"

    packet = load_json(packet_path)
    packet["created_at"] = "2000-01-01T00:00:00Z"
    packet["updated_at"] = "2000-01-01T00:00:00Z"
    write_json_file(packet_path, packet)

    lifecycle = load_json(lifecycle_path)
    lifecycle["created_at"] = "2000-01-01T00:00:00Z"
    lifecycle["updated_at"] = "2000-01-01T00:00:00Z"
    write_json_file(lifecycle_path, lifecycle)

    write_event_log(
        events_path,
        [
            {
                "event_id": "stale-event-1",
                "task_id": "task-stale-reconcile",
                "event_type": "task_dispatched",
                "timestamp": "2000-01-01T00:00:00Z",
                "detail": {"title": "Stale reconcile"},
            }
        ],
    )

    reconcile_stale = run_script(
        "commander_reconcile.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-stale-reconcile",
        "--stale-after-hours",
        "1",
    )
    assert reconcile_stale.returncode == 0, reconcile_stale.stderr
    reconcile_stale_payload = json.loads(reconcile_stale.stdout)
    stale_task = reconcile_stale_payload["tasks"][0]
    assert stale_task["changed"] is True
    assert stale_task["action"] == "marked_stale"
    assert stale_task["status"]["lifecycle_status"] == "stale"
    assert stale_task["status"]["current_phase"] == "stale"
    assert stale_task["status"]["recommended_action"] == "reconcile_task"

    stale_status = stale_task["status"]
    assert stale_status["stale_at"] is not None
    write_event_log(
        events_path,
        [
            {
                "event_id": "stale-event-1",
                "task_id": "task-stale-reconcile",
                "event_type": "task_dispatched",
                "timestamp": "2000-01-01T00:00:00Z",
                "detail": {"title": "Stale reconcile"},
            },
            {
                "event_id": "stale-event-2",
                "task_id": "task-stale-reconcile",
                "event_type": "task_report_ingested",
                "timestamp": "2999-01-01T00:00:00Z",
                "detail": {"note": "fresh runtime activity"},
            },
        ],
    )

    reconcile_reopen = run_script(
        "commander_reconcile.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-stale-reconcile",
        "--stale-after-hours",
        "1",
    )
    assert reconcile_reopen.returncode == 0, reconcile_reopen.stderr
    reconcile_reopen_payload = json.loads(reconcile_reopen.stdout)
    reopened_task = reconcile_reopen_payload["tasks"][0]
    assert reopened_task["changed"] is True
    assert reopened_task["action"] == "reopened"
    assert reopened_task["status"]["lifecycle_status"] == "active"
    assert reopened_task["status"]["current_phase"] == "awaiting_report"
    assert reopened_task["status"]["commander_recommendation"] == "awaiting_report"
    assert reopened_task["status"]["recommended_action"] == "wait_for_worker_report"


def test_cancel_and_reopen_cli_round_trip_runtime_task(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    dispatch = run_script(
        "commander_dispatch.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-cancel-reopen",
        "--title",
        "Cancel and reopen",
        "--goal",
        "Exercise explicit cancel and reopen flow",
        "--must-read",
        "README.md",
        "--bound",
        "transport only",
        "--validation",
        "pytest",
    )
    assert dispatch.returncode == 0, dispatch.stderr

    cancel_result = run_script(
        "commander_cancel.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-cancel-reopen",
        "--reason",
        "commander_requested_stop",
    )
    assert cancel_result.returncode == 0, cancel_result.stderr
    cancel_payload = json.loads(cancel_result.stdout)
    assert cancel_payload["changed"] is True
    assert cancel_payload["status"]["lifecycle_status"] == "canceled"
    assert cancel_payload["status"]["current_phase"] == "canceled"
    assert cancel_payload["status"]["recommended_action"] == "review_canceled_task"

    reopen_result = run_script(
        "commander_reopen.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-cancel-reopen",
        "--reason",
        "work_should_continue",
    )
    assert reopen_result.returncode == 0, reopen_result.stderr
    reopen_payload = json.loads(reopen_result.stdout)
    assert reopen_payload["changed"] is True
    assert reopen_payload["status"]["lifecycle_status"] == "active"
    assert reopen_payload["status"]["current_phase"] == "awaiting_report"
    assert reopen_payload["status"]["recommended_action"] == "wait_for_worker_report"


def test_archive_cleanup_moves_cleanup_eligible_archived_task_out_of_live_runtime(
    tmp_path: Path,
) -> None:
    runtime_root, action_dir = create_cleanup_ready_archived_task(
        tmp_path,
        task_id="task-archive-cleanup",
        title="Archive cleanup",
        goal="Exercise archived task cleanup move",
        runtime_dir_name="runtime",
    )
    task_dir = runtime_root / "tasks" / "task-archive-cleanup"

    cleanup_result = run_script(
        "commander_archive_cleanup.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-archive-cleanup",
    )
    assert cleanup_result.returncode == 0, cleanup_result.stderr
    cleanup_payload = json.loads(cleanup_result.stdout)
    moved_task = cleanup_payload["tasks"][0]
    assert moved_task["moved"] is True

    archive_task_dir = runtime_root / "archive" / "tasks" / "task-archive-cleanup"
    archive_candidate_path = (
        runtime_root
        / "archive"
        / "improvements"
        / "task-archive-cleanup.candidate.json"
    )
    archive_action_dir = (
        runtime_root / "archive" / "improvement_actions" / action_dir.name
    )
    assert task_dir.exists() is False
    assert archive_task_dir.exists() is True
    assert (archive_task_dir / "archive_manifest.json").exists() is True
    assert archive_candidate_path.exists() is True
    assert action_dir.exists() is False
    assert archive_action_dir.exists() is True
    manifest = load_json(archive_task_dir / "archive_manifest.json")
    assert manifest["retention_policy"]["archive_retention_days"] == 7
    assert manifest["improvement_action_dirs"][0]["destination_dir"] == str(
        archive_action_dir
    )
    assert cleanup_payload["archive_catalog_sync"]["task_count"] == 1
    assert (runtime_root / "archive" / "catalog.json").exists() is True

    archive_catalog_result = run_script(
        "commander_archive_catalog.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-archive-cleanup",
    )
    assert archive_catalog_result.returncode == 0, archive_catalog_result.stderr
    archive_catalog_payload = json.loads(archive_catalog_result.stdout)
    assert archive_catalog_payload["task_count"] == 1
    archive_entry = archive_catalog_payload["tasks"][0]
    assert archive_entry["task_id"] == "task-archive-cleanup"
    assert archive_entry["archive_task_dir"] == str(archive_task_dir)
    assert archive_entry["improvement_action_dir_count"] == 1


def test_archive_catalog_sync_writes_secondary_snapshots_and_prunes_stale_ones(
    tmp_path: Path,
) -> None:
    runtime_root, _action_dir = create_cleanup_ready_archived_task(
        tmp_path,
        task_id="task-archive-sync",
        title="Archive sync",
        goal="Exercise archive catalog sync",
        runtime_dir_name="runtime-sync",
    )
    cleanup_result = run_script(
        "commander_archive_cleanup.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-archive-sync",
    )
    assert cleanup_result.returncode == 0, cleanup_result.stderr

    stale_snapshot_path = runtime_root / "archive" / "snapshots" / "ghost.summary.json"
    stale_snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    stale_snapshot_path.write_text("{}\n", encoding="utf-8")

    sync_result = run_script(
        "commander_archive_catalog.py",
        "--runtime-root",
        str(runtime_root),
        "--sync",
    )
    assert sync_result.returncode == 0, sync_result.stderr
    sync_payload = json.loads(sync_result.stdout)
    archive_sync = sync_payload["archive_catalog_sync"]
    task_snapshot_path = (
        runtime_root / "archive" / "snapshots" / "task-archive-sync.summary.json"
    )

    assert (runtime_root / "archive" / "catalog.json").exists() is True
    assert task_snapshot_path.exists() is True
    assert stale_snapshot_path.exists() is False
    assert archive_sync["task_count"] == 1
    assert archive_sync["snapshot_count"] == 1
    assert archive_sync["removed_stale_snapshot_count"] == 1
    assert sync_payload["tasks"][0]["secondary_snapshot_exists"] is True


def test_cleanup_plan_reports_protected_paths_and_can_apply_cleanup(
    tmp_path: Path,
) -> None:
    runtime_root, _action_dir = create_cleanup_ready_archived_task(
        tmp_path,
        task_id="task-cleanup-plan",
        title="Cleanup plan",
        goal="Exercise cleanup plan",
        runtime_dir_name="runtime-plan",
    )

    dry_run_result = run_script(
        "commander_cleanup_plan.py",
        "--runtime-root",
        str(runtime_root),
    )
    assert dry_run_result.returncode == 0, dry_run_result.stderr
    dry_run_payload = json.loads(dry_run_result.stdout)
    protected_relative_paths = {
        item["relative_path"] for item in dry_run_payload["protected_paths"]
    }

    assert dry_run_payload["cleanup_candidate_count"] == 1
    assert dry_run_payload["cleanup_candidate_ids"] == ["task-cleanup-plan"]
    assert "tasks" in protected_relative_paths
    assert "archive/catalog.json" in protected_relative_paths
    assert dry_run_payload["archive_sync_status"]["needs_sync"] is False

    apply_result = run_script(
        "commander_cleanup_plan.py",
        "--runtime-root",
        str(runtime_root),
        "--apply",
    )
    assert apply_result.returncode == 0, apply_result.stderr
    apply_payload = json.loads(apply_result.stdout)
    cleanup_apply_result = apply_payload["maintenance_actions"]["cleanup_apply_result"]

    assert cleanup_apply_result["moved_count"] == 1
    assert apply_payload["cleanup_candidate_count"] == 0
    assert apply_payload["archive_sync_status"]["archive_catalog_exists"] is True
    assert apply_payload["archive_sync_status"]["secondary_snapshot_count"] == 1


def test_maintenance_cycle_syncs_archive_and_reports_pending_cleanup(
    tmp_path: Path,
) -> None:
    runtime_root, _action_dir = create_cleanup_ready_archived_task(
        tmp_path,
        task_id="task-maintenance-cycle",
        title="Maintenance cycle",
        goal="Exercise maintenance cycle dry-run",
        runtime_dir_name="runtime-maintenance",
    )

    maintenance_result = run_script(
        "commander_maintenance.py",
        "--runtime-root",
        str(runtime_root),
    )
    assert maintenance_result.returncode == 0, maintenance_result.stderr
    maintenance_payload = json.loads(maintenance_result.stdout)

    assert maintenance_payload["sync_archive_catalog"] is True
    assert maintenance_payload["apply_cleanup"] is False
    assert maintenance_payload["before"]["cleanup_plan"]["cleanup_candidate_count"] == 1
    assert maintenance_payload["after"]["cleanup_plan"]["cleanup_candidate_count"] == 1
    assert maintenance_payload["actions"]["archive_catalog_sync"]["task_count"] == 0
    assert maintenance_payload["actions"]["cleanup_apply_result"] is None
    assert maintenance_payload["cycle_health"] == "cleanup_pending"
    assert (runtime_root / "archive" / "catalog.json").exists() is True


def test_maintenance_cycle_can_apply_cleanup_and_finish_healthy(tmp_path: Path) -> None:
    runtime_root, _action_dir = create_cleanup_ready_archived_task(
        tmp_path,
        task_id="task-maintenance-apply",
        title="Maintenance apply",
        goal="Exercise maintenance cycle apply",
        runtime_dir_name="runtime-maintenance-apply",
    )

    maintenance_result = run_script(
        "commander_maintenance.py",
        "--runtime-root",
        str(runtime_root),
        "--apply-cleanup",
    )
    assert maintenance_result.returncode == 0, maintenance_result.stderr
    maintenance_payload = json.loads(maintenance_result.stdout)
    cleanup_apply_result = maintenance_payload["actions"]["cleanup_apply_result"]

    assert cleanup_apply_result["moved_count"] == 1
    assert maintenance_payload["after"]["cleanup_plan"]["cleanup_candidate_count"] == 0
    assert maintenance_payload["after"]["audit"]["warning_count"] == 0
    assert maintenance_payload["cycle_health"] == "healthy"
    assert (
        runtime_root / "archive" / "tasks" / "task-maintenance-apply"
    ).exists() is True


def test_audit_warns_when_task_card_claims_no_active_work_but_runtime_has_live_task(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    dispatch = run_script(
        "commander_dispatch.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-audit-active",
        "--title",
        "Audit active drift",
        "--goal",
        "Exercise task card/runtime audit",
        "--must-read",
        "README.md",
        "--bound",
        "transport only",
        "--validation",
        "pytest",
    )
    assert dispatch.returncode == 0, dispatch.stderr

    task_card_path = tmp_path / "当前任务卡.md"
    task_card_path.write_text(
        "# 指挥官当前任务卡\n\n## 5. 当前活跃任务\n\n当前无活跃任务。\n",
        encoding="utf-8",
    )

    audit_result = run_script(
        "commander_audit.py",
        "--runtime-root",
        str(runtime_root),
        "--task-card-path",
        str(task_card_path),
    )
    assert audit_result.returncode == 0, audit_result.stderr
    audit_payload = json.loads(audit_result.stdout)
    assert audit_payload["task_card"]["claims_no_active_work"] is True
    assert audit_payload["warning_count"] >= 1
    warning_kinds = {item["kind"] for item in audit_payload["warnings"]}
    assert "task_card_runtime_drift" in warning_kinds


def test_audit_does_not_treat_canceled_runtime_task_as_active_drift(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    dispatch = run_script(
        "commander_dispatch.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-audit-canceled",
        "--title",
        "Audit canceled task",
        "--goal",
        "Ensure canceled runtime tasks are terminal for task-card drift",
        "--must-read",
        "README.md",
        "--bound",
        "transport only",
        "--validation",
        "pytest",
    )
    assert dispatch.returncode == 0, dispatch.stderr

    cancel = run_script(
        "commander_cancel.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-audit-canceled",
        "--reason",
        "test cancellation",
    )
    assert cancel.returncode == 0, cancel.stderr

    task_card_path = tmp_path / "当前任务卡.md"
    task_card_path.write_text(
        "# 指挥官当前任务卡\n\n## 5. 当前活跃任务\n\n当前无活跃任务。\n",
        encoding="utf-8",
    )

    audit_result = run_script(
        "commander_audit.py",
        "--runtime-root",
        str(runtime_root),
        "--task-card-path",
        str(task_card_path),
    )
    assert audit_result.returncode == 0, audit_result.stderr
    audit_payload = json.loads(audit_result.stdout)
    warning_kinds = {item["kind"] for item in audit_payload["warnings"]}
    assert "task_card_runtime_drift" not in warning_kinds
    assert "task-audit-canceled" not in audit_payload["runtime_attention_task_ids"]


def test_audit_surfaces_stale_worker_and_orphan_task_attention(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    dispatch = run_script(
        "commander_dispatch.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-audit-worker",
        "--title",
        "Audit worker drift",
        "--goal",
        "Exercise worker pool audit warnings",
        "--must-read",
        "README.md",
        "--bound",
        "transport only",
        "--validation",
        "pytest",
    )
    assert dispatch.returncode == 0, dispatch.stderr

    acquire = run_script(
        "commander_worker_pool.py",
        "--runtime-root",
        str(runtime_root),
        "acquire",
        "--task-id",
        "task-audit-worker",
        "--worker-profile",
        "code-worker",
        "--preferred-worker-profile",
        "code-worker",
        "--tool-profile",
        "control_plane_safe_write",
        "--allowed-tool",
        "apply_patch",
    )
    assert acquire.returncode == 0, acquire.stderr
    worker_id = json.loads(acquire.stdout)["worker_id"]

    slot_path = runtime_root / "workers" / "slots" / f"{worker_id}.json"
    slot = load_json(slot_path)
    slot["lease_expires_at"] = "2026-04-11T00:00:00Z"
    slot["heartbeat_at"] = "2026-04-11T00:00:00Z"
    slot["updated_at"] = "2026-04-11T00:00:00Z"
    write_json_file(slot_path, slot)

    task_card_path = tmp_path / "task-card-audit-worker.md"
    task_card_path.write_text(
        "# 鎸囨尌瀹樺綋鍓嶄换鍔″崱\n\n## 5. 褰撳墠娲昏穬浠诲姟\n\n### `5.5 鎸囨尌瀹樼郴缁熷畬鍠勫伐绋媊\n",
        encoding="utf-8",
    )

    audit_result = run_script(
        "commander_audit.py",
        "--runtime-root",
        str(runtime_root),
        "--task-card-path",
        str(task_card_path),
    )
    assert audit_result.returncode == 0, audit_result.stderr
    audit_payload = json.loads(audit_result.stdout)
    warning_kinds = {item["kind"] for item in audit_payload["warnings"]}
    assert "worker_pool_stale_leases" in warning_kinds
    assert "worker_pool_orphan_tasks" in warning_kinds
    assert "task_worker_binding_drift" in warning_kinds
    assert audit_payload["runtime_worker_attention_worker_ids"] == [worker_id]
    assert audit_payload["runtime_orphan_task_ids"] == ["task-audit-worker"]
    assert audit_payload["runtime_worker_binding_attention_task_ids"] == [
        "task-audit-worker"
    ]


def test_catalog_refresh_failure_is_projected_to_status_catalog_and_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = tmp_path / "runtime"
    dispatch = run_script(
        "commander_dispatch.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-catalog-failure",
        "--title",
        "Catalog refresh failure",
        "--goal",
        "Exercise explicit catalog refresh failure surfacing",
        "--must-read",
        "README.md",
        "--bound",
        "transport only",
        "--validation",
        "pytest",
    )
    assert dispatch.returncode == 0, dispatch.stderr

    paths = resolve_task_paths(runtime_root, "task-catalog-failure")
    fake_db = types.ModuleType("api.db")

    def _raise_upsert(_entry: dict[str, object]) -> None:
        raise RuntimeError("forced catalog failure")

    fake_db.upsert_commander_task_catalog_entry = _raise_upsert
    monkeypatch.setitem(sys.modules, "api.db", fake_db)

    refresh_payload = refresh_commander_task_catalog(
        paths, event_type="task_dispatched"
    )
    assert refresh_payload["status"] == "failed"
    assert refresh_payload["reason"] == "catalog_entry_upsert_failed"
    assert refresh_payload["failure_count"] == 1
    assert refresh_payload["error_type"] == "RuntimeError"
    assert "forced catalog failure" in str(refresh_payload["error_message"])

    status_result = run_script(
        "commander_status.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-catalog-failure",
    )
    assert status_result.returncode == 0, status_result.stderr
    status_payload = json.loads(status_result.stdout)
    assert status_payload["catalog_refresh"]["status"] == "failed"
    assert status_payload["catalog_refresh"]["failure_count"] == 1
    assert (
        status_payload["next_minimal_action"]
        == "Inspect catalog refresh failure before trusting catalog views"
    )
    anchors = status_payload["pending_close_worker_attention"]["anchors"]
    catalog_anchor = next(item for item in anchors if item["kind"] == "catalog_refresh")
    assert catalog_anchor["status"] == "failed"
    assert catalog_anchor["error_type"] == "RuntimeError"

    catalog = load_task_catalog(runtime_root, task_id="task-catalog-failure")
    entry = catalog["tasks"][0]
    assert entry["catalog_refresh_status"] == "failed"
    assert entry["catalog_refresh_failure_count"] == 1
    assert entry["catalog_refresh_error_type"] == "RuntimeError"

    task_card_path = tmp_path / "task-card-catalog-failure.md"
    task_card_path.write_text(
        "# 指挥官当前任务卡\n\n## 5. 当前活跃任务\n\n### `5.5 指挥官系统完善工程`\n",
        encoding="utf-8",
    )
    audit_result = run_script(
        "commander_audit.py",
        "--runtime-root",
        str(runtime_root),
        "--task-card-path",
        str(task_card_path),
    )
    assert audit_result.returncode == 0, audit_result.stderr
    audit_payload = json.loads(audit_result.stdout)
    warning_kinds = {item["kind"] for item in audit_payload["warnings"]}
    assert "catalog_refresh_failed" in warning_kinds
    assert audit_payload["runtime_catalog_refresh_failed_task_ids"] == [
        "task-catalog-failure"
    ]
    assert [
        item["task_id"]
        for item in audit_payload["attention_views"]["catalog_refresh_failed"]
    ] == ["task-catalog-failure"]
    recovery_item = audit_payload["recovery_queue"][0]
    assert recovery_item["task_id"] == "task-catalog-failure"
    assert recovery_item["attention_grade"] == "needs_commander"
    assert "catalog_refresh_failed" in recovery_item["attention_kinds"]


def test_audit_warns_on_commander_write_violation(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    task_card_path = tmp_path / "task-card-role-guard.md"
    task_card_path.write_text(
        "# 鎸囨尌瀹樺綋鍓嶄换鍔″崱\n\n## 5. 褰撳墠娲昏穬浠诲姟\n\n褰撳墠鏃犳椿璺冧换鍔°€俓n",
        encoding="utf-8",
    )

    audit_payload = build_audit_report(
        runtime_root,
        task_card_path=task_card_path,
        repo_status_paths=[
            "AGENTS.md",
            "commander/graph/graph.py",
            "commander/state/当前任务卡.md",
        ],
        enforce_role_guard=True,
    )

    warning_kinds = {item["kind"] for item in audit_payload["warnings"]}
    assert "commander_write_violation" in warning_kinds
    assert audit_payload["role_guard"]["enabled"] is True
    assert audit_payload["role_guard"]["violation_paths"] == [
        "commander/graph/graph.py"
    ]


def test_catalog_refresh_recovery_clears_failure_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = tmp_path / "runtime"
    dispatch = run_script(
        "commander_dispatch.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-catalog-recovery",
        "--title",
        "Catalog refresh recovery",
        "--goal",
        "Exercise recovery after a catalog refresh failure",
        "--must-read",
        "README.md",
        "--bound",
        "transport only",
        "--validation",
        "pytest",
    )
    assert dispatch.returncode == 0, dispatch.stderr

    paths = resolve_task_paths(runtime_root, "task-catalog-recovery")
    fake_db_fail = types.ModuleType("api.db")
    fake_db_fail.upsert_commander_task_catalog_entry = lambda _entry: (
        _ for _ in ()
    ).throw(RuntimeError("first refresh fails"))
    monkeypatch.setitem(sys.modules, "api.db", fake_db_fail)
    failed = refresh_commander_task_catalog(paths, event_type="task_dispatched")
    assert failed["status"] == "failed"
    assert failed["failure_count"] == 1

    fake_db_ok = types.ModuleType("api.db")
    synced_entries: list[dict[str, object]] = []

    def _capture_upsert(entry: dict[str, object]) -> None:
        synced_entries.append(entry)

    fake_db_ok.upsert_commander_task_catalog_entry = _capture_upsert
    monkeypatch.setitem(sys.modules, "api.db", fake_db_ok)
    recovered = refresh_commander_task_catalog(paths, event_type="task_dispatched")
    assert recovered["status"] == "synced"
    assert recovered["failure_count"] == 0
    assert recovered["error_type"] is None
    assert recovered["last_success_event_type"] == "task_dispatched"
    assert synced_entries and synced_entries[0]["task_id"] == "task-catalog-recovery"

    summary = build_catalog_refresh_summary(paths)
    assert summary["status"] == "synced"
    assert summary["failure_count"] == 0
    assert summary["last_success_event_type"] == "task_dispatched"
    assert summary["error_message"] is None


def test_audit_builds_attention_views_and_recovery_queue(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"

    dispatch_close = run_script(
        "commander_dispatch.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-close-view",
        "--title",
        "Pending close view",
        "--goal",
        "Exercise pending close attention bucket",
        "--must-read",
        "README.md",
        "--bound",
        "transport only",
        "--validation",
        "pytest",
    )
    assert dispatch_close.returncode == 0, dispatch_close.stderr
    close_report = make_report()
    close_report["task_id"] = "task-close-view"
    close_report_path = tmp_path / "task-close-view-report.json"
    write_json_file(close_report_path, close_report)
    ingest_close = run_script(
        "commander_ingest.py",
        "--runtime-root",
        str(runtime_root),
        "--report",
        str(close_report_path),
    )
    assert ingest_close.returncode == 0, ingest_close.stderr

    dispatch_stale = run_script(
        "commander_dispatch.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-stale-view",
        "--title",
        "Stale view",
        "--goal",
        "Exercise stale attention bucket",
        "--must-read",
        "README.md",
        "--bound",
        "transport only",
        "--validation",
        "pytest",
    )
    assert dispatch_stale.returncode == 0, dispatch_stale.stderr
    mark_task_stale(
        resolve_task_paths(runtime_root, "task-stale-view"),
        reason="test_stale_attention",
    )

    dispatch_drift = run_script(
        "commander_dispatch.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-drift-view",
        "--title",
        "Worker drift view",
        "--goal",
        "Exercise worker drift attention bucket",
        "--must-read",
        "README.md",
        "--bound",
        "transport only",
        "--validation",
        "pytest",
    )
    assert dispatch_drift.returncode == 0, dispatch_drift.stderr
    acquire_first = run_script(
        "commander_worker_pool.py",
        "--runtime-root",
        str(runtime_root),
        "acquire",
        "--task-id",
        "task-drift-view",
        "--worker-profile",
        "code-worker",
        "--preferred-worker-profile",
        "code-worker",
        "--tool-profile",
        "control_plane_safe_write",
        "--allowed-tool",
        "apply_patch",
        "--no-reuse",
    )
    assert acquire_first.returncode == 0, acquire_first.stderr
    acquire_second = run_script(
        "commander_worker_pool.py",
        "--runtime-root",
        str(runtime_root),
        "acquire",
        "--task-id",
        "task-drift-view",
        "--worker-profile",
        "code-worker",
        "--preferred-worker-profile",
        "code-worker",
        "--tool-profile",
        "control_plane_safe_write",
        "--allowed-tool",
        "apply_patch",
        "--no-reuse",
    )
    assert acquire_second.returncode == 0, acquire_second.stderr

    dispatch_user = run_script(
        "commander_dispatch.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-user-view",
        "--title",
        "Pending user view",
        "--goal",
        "Exercise pending user attention bucket",
        "--must-read",
        "README.md",
        "--bound",
        "transport only",
        "--validation",
        "pytest",
    )
    assert dispatch_user.returncode == 0, dispatch_user.stderr
    user_report = make_report()
    user_report["task_id"] = "task-user-view"
    user_report["needs_commander_decision"] = False
    user_report["needs_user_decision"] = True
    user_report["user_decision_reason"] = "Need the user to choose the next direction."
    user_report["recommended_next_step"] = (
        "Pause and ask the user to choose the next direction."
    )
    user_report_path = tmp_path / "task-user-view-report.json"
    write_json_file(user_report_path, user_report)
    ingest_user = run_script(
        "commander_ingest.py",
        "--runtime-root",
        str(runtime_root),
        "--report",
        str(user_report_path),
    )
    assert ingest_user.returncode == 0, ingest_user.stderr

    task_card_path = tmp_path / "task-card-attention.md"
    task_card_path.write_text(
        "# 指挥官当前任务卡\n\n## 5. 当前活跃任务\n\n### `5.5 指挥官系统完善工程`\n",
        encoding="utf-8",
    )
    audit_result = run_script(
        "commander_audit.py",
        "--runtime-root",
        str(runtime_root),
        "--task-card-path",
        str(task_card_path),
    )
    assert audit_result.returncode == 0, audit_result.stderr
    payload = json.loads(audit_result.stdout)
    attention_views = payload["attention_views"]

    assert "task-close-view" in {
        item["task_id"] for item in attention_views["pending_close"]
    }
    assert "task-close-view" in {
        item["task_id"] for item in attention_views["pending_candidate_review"]
    }
    assert "task-stale-view" in {item["task_id"] for item in attention_views["stale"]}
    assert "task-drift-view" in {
        item["task_id"] for item in attention_views["worker_drift"]
    }
    assert "task-user-view" in {
        item["task_id"] for item in attention_views["pending_user"]
    }

    recovery_queue = {item["task_id"]: item for item in payload["recovery_queue"]}
    assert recovery_queue["task-user-view"]["attention_grade"] == "needs_user"
    assert "pending_user" in recovery_queue["task-user-view"]["attention_kinds"]
    assert recovery_queue["task-drift-view"]["attention_grade"] == "needs_commander"
    assert "worker_drift" in recovery_queue["task-drift-view"]["attention_kinds"]


def test_need_split_report_surfaces_governance_and_split_attention(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    dispatch = run_script(
        "commander_dispatch.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-split-governance",
        "--title",
        "Split governance",
        "--goal",
        "Exercise split governance state",
        "--must-read",
        "README.md",
        "--bound",
        "transport only",
        "--validation",
        "pytest",
        "--dispatch-kind",
        "split",
        "--source-task-id",
        "task-parent",
        "--parent-task-id",
        "task-parent",
        "--task-owner",
        "commander-phase-c",
        "--closure-policy",
        "require_commander_review",
    )
    assert dispatch.returncode == 0, dispatch.stderr

    report = make_report()
    report["task_id"] = "task-split-governance"
    report["status"] = "need_split"
    report["summary"] = "This change should be split into a narrower follow-up task."
    report["risks"] = ["Scope is too broad for one worker pass."]
    report["recommended_next_step"] = (
        "Split the follow-up into a runtime governance child task."
    )
    report["needs_commander_decision"] = True
    report["result_grade"] = "partial"
    report["next_action_owner"] = "commander"
    report["continuation_mode"] = "split"
    report["decision_reason"] = (
        "A narrower follow-up task is needed before execution can continue."
    )
    report["split_suggestion"] = {
        "suggested_task_id": "task-split-governance-child",
        "title": "Split governance child",
        "goal": "Continue the runtime governance follow-up in a dedicated child task.",
        "reason": "Keep the current task closed to one governance slice.",
    }
    report_path = tmp_path / "report-split.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    ingest = run_script(
        "commander_ingest.py",
        "--runtime-root",
        str(runtime_root),
        "--report",
        str(report_path),
    )
    assert ingest.returncode == 0, ingest.stderr
    ingest_payload = json.loads(ingest.stdout)
    status_payload = ingest_payload["status"]
    assert status_payload["dispatch_kind"] == "split"
    assert status_payload["source_task_id"] == "task-parent"
    assert status_payload["parent_task_id"] == "task-parent"
    assert status_payload["task_owner"] == "commander-phase-c"
    assert status_payload["closure_policy"] == "require_commander_review"
    assert status_payload["commander_recommendation"] == "needs_commander_decision"
    assert status_payload["current_phase"] == "needs_commander_decision"
    assert status_payload["recommended_action"] == "review_split_suggestion"
    assert status_payload["result_grade"] == "partial"
    assert status_payload["continuation_mode"] == "split"
    assert (
        status_payload["split_suggestion"]["suggested_task_id"]
        == "task-split-governance-child"
    )
    assert status_payload["decision_gates"]["summary"] == "commander_decision_required"
    anchor_kinds = [
        anchor["kind"]
        for anchor in status_payload["pending_close_worker_attention"]["anchors"]
    ]
    assert "decision_gate" in anchor_kinds
    assert "split_suggestion" in anchor_kinds

    catalog_payload = load_task_catalog(runtime_root, task_id="task-split-governance")
    catalog_entry = catalog_payload["tasks"][0]
    assert catalog_entry["dispatch_kind"] == "split"
    assert catalog_entry["source_task_id"] == "task-parent"
    assert catalog_entry["task_owner"] == "commander-phase-c"
    assert catalog_entry["closure_policy"] == "require_commander_review"
    assert catalog_entry["result_grade"] == "partial"
    assert catalog_entry["continuation_mode"] == "split"


def test_audit_does_not_treat_rule_text_as_no_active_claim(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    dispatch = run_script(
        "commander_dispatch.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        "task-audit-rules",
        "--title",
        "Audit rules text",
        "--goal",
        "Ensure rule text does not trigger false drift",
        "--must-read",
        "README.md",
        "--bound",
        "transport only",
        "--validation",
        "pytest",
    )
    assert dispatch.returncode == 0, dispatch.stderr

    task_card_path = tmp_path / "当前任务卡.md"
    task_card_path.write_text(
        "# 指挥官当前任务卡\n\n## 2. 使用规则\n\n如果当前没有真实活跃任务，宁可明确写“当前无活跃任务”。\n\n## 5. 当前活跃任务\n\n### `5.5 指挥官系统完善工程`\n",
        encoding="utf-8",
    )

    audit_result = run_script(
        "commander_audit.py",
        "--runtime-root",
        str(runtime_root),
        "--task-card-path",
        str(task_card_path),
    )
    assert audit_result.returncode == 0, audit_result.stderr
    audit_payload = json.loads(audit_result.stdout)
    assert audit_payload["task_card"]["claims_no_active_work"] is False
    warning_kinds = {item["kind"] for item in audit_payload["warnings"]}
    assert "task_card_runtime_drift" not in warning_kinds


def test_agent_state_syncs_direct_completed_payload(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    task_id = "task-agent-state-completed"
    dispatch = run_script(
        "commander_dispatch.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        task_id,
        "--title",
        "Completed payload",
        "--goal",
        "Exercise direct completed payload sync",
        "--must-read",
        "README.md",
        "--bound",
        "transport only",
        "--validation",
        "pytest",
    )
    assert dispatch.returncode == 0, dispatch.stderr

    report = make_report()
    report["task_id"] = task_id
    report_path = tmp_path / f"{task_id}-report.json"
    write_json_file(report_path, report)
    ingest = run_script(
        "commander_ingest.py",
        "--runtime-root",
        str(runtime_root),
        "--report",
        str(report_path),
    )
    assert ingest.returncode == 0, ingest.stderr

    state_payload = json.dumps({"completed": "worker finished"})
    result = run_script(
        "commander_agent_state.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        task_id,
        "--agent-id",
        "subagent-completed",
        "--notification-json",
        state_payload,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["state"] == "completed_waiting_close"
    assert payload["active_subagents_summary"]["completed_waiting_close_count"] == 1
    assert payload["active_subagents_summary"]["has_open_subagents"] is True
    assert payload["active_subagents"][0]["state"] == "completed_waiting_close"


def test_agent_state_syncs_notification_envelope_blocked_payload(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    task_id = "task-agent-state-blocked"
    dispatch = run_script(
        "commander_dispatch.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        task_id,
        "--title",
        "Blocked payload",
        "--goal",
        "Exercise notification envelope payload sync",
        "--must-read",
        "README.md",
        "--bound",
        "transport only",
        "--validation",
        "pytest",
    )
    assert dispatch.returncode == 0, dispatch.stderr

    report = make_report()
    report["task_id"] = task_id
    report_path = tmp_path / f"{task_id}-report.json"
    write_json_file(report_path, report)
    ingest = run_script(
        "commander_ingest.py",
        "--runtime-root",
        str(runtime_root),
        "--report",
        str(report_path),
    )
    assert ingest.returncode == 0, ingest.stderr

    notification_payload = json.dumps(
        {
            "agent_path": "workers/subagent-blocked",
            "status": {"blocked": "waiting on user"},
        }
    )
    result = run_script(
        "commander_agent_state.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        task_id,
        "--notification-json",
        notification_payload,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["agent_id"] == "subagent-blocked"
    assert payload["state"] == "blocked"
    assert payload["active_subagents_summary"]["blocked_count"] == 1
    assert payload["active_subagents_summary"]["has_blocked_subagents"] is True
    assert payload["active_subagents"][0]["state"] == "blocked"


def test_blocked_subagents_are_reported_by_close_and_audit(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    task_id = "task-blocked-close-audit"
    dispatch = run_script(
        "commander_dispatch.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        task_id,
        "--title",
        "Blocked close audit",
        "--goal",
        "Exercise blocked subagent reporting",
        "--must-read",
        "README.md",
        "--bound",
        "transport only",
        "--validation",
        "pytest",
    )
    assert dispatch.returncode == 0, dispatch.stderr

    report = make_report()
    report["task_id"] = task_id
    report_path = tmp_path / f"{task_id}-report.json"
    write_json_file(report_path, report)
    ingest = run_script(
        "commander_ingest.py",
        "--runtime-root",
        str(runtime_root),
        "--report",
        str(report_path),
    )
    assert ingest.returncode == 0, ingest.stderr

    blocked_payload = json.dumps(
        {
            "agent_path": "workers/subagent-blocked",
            "status": {"blocked": "blocked on user input"},
        }
    )
    state_result = run_script(
        "commander_agent_state.py",
        "--runtime-root",
        str(runtime_root),
        "--task-id",
        task_id,
        "--notification-json",
        blocked_payload,
    )
    assert state_result.returncode == 0, state_result.stderr

    with pytest.raises(
        SchemaValidationError,
        match="active_subagents_are_blocked",
    ):
        close_task(runtime_root, task_id)

    task_card_path = tmp_path / "current_task_card.md"
    task_card_path.write_text(
        "# Current Task Card\n\n## 5. Active Tasks\n\nNo active tasks.\n",
        encoding="utf-8",
    )
    audit_payload = build_audit_report(
        runtime_root,
        task_card_path=task_card_path,
    )
    blocked_warning = next(
        item for item in audit_payload["warnings"] if item["kind"] == "active_subagents_blocked"
    )
    assert blocked_warning["reason"] == "active_subagents_are_blocked"
    assert blocked_warning["next_action"] == "Unblock or close blocked sub-agents before closing the task."
    assert blocked_warning["count"] == 1
