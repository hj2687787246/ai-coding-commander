from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from commander.transport.scripts.commander_harness import SchemaValidationError, load_schema, validate_instance


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON_EXE = Path(sys.executable)
IMPROVEMENT_SCHEMA_PATH = (
    PROJECT_ROOT / "commander" / "transport" / "schemas" / "commander_improvement_candidate.schema.json"
)


def run_script(script_name: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(PYTHON_EXE), "-m", f"commander.transport.scripts.{script_name.removesuffix('.py')}", *args],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def make_report(*, task_id: str, changed_files: list[str], summary: str) -> dict[str, object]:
    return {
        "schema_version": "commander-harness-v1",
        "task_id": task_id,
        "status": "done",
        "summary": summary,
        "changed_files": changed_files,
        "verification": [
            {
                "name": "pytest",
                "command": "python -m pytest -q tests/test_commander_propose_improvement.py",
                "result": "passed",
            }
        ],
        "commit": {
            "message": "测试提交",
        },
        "risks": ["low confidence until replayed on real tasks"],
        "recommended_next_step": "Review whether this should be promoted into a reusable asset.",
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


def write_report(path: Path, *, task_id: str, changed_files: list[str], summary: str) -> None:
    path.write_text(
        json.dumps(
            make_report(task_id=task_id, changed_files=changed_files, summary=summary),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def load_candidate_from_output(result: subprocess.CompletedProcess[str]) -> tuple[dict[str, object], Path]:
    payload = json.loads(result.stdout)
    candidate_path = Path(payload["output_path"])
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    return candidate, candidate_path


def test_improvement_candidate_schema_accepts_valid_payload() -> None:
    payload = {
        "schema_version": "commander-harness-v1",
        "candidate_id": "task-001-abcdef12",
        "task_id": "task-001",
        "source_report_path": "D:/tmp/report.json",
        "source_summary": "Memory retrieval layer completed.",
        "observed_pattern": "The same recovery path keeps showing up in tasks.",
        "recommended_layer": "script",
        "recommended_target": "commander/transport/scripts/commander_memory_search.py",
        "evidence": ["source_report=D:/tmp/report.json"],
        "rationale": ["Executable assets are a better fit for this repeated pattern."],
        "validation_requirements": ["pytest"],
        "approval_required": True,
        "status": "candidate",
        "created_at": "2026-04-11T00:00:00Z",
    }

    validate_instance(payload, load_schema(IMPROVEMENT_SCHEMA_PATH))


def test_improvement_candidate_schema_rejects_invalid_layer() -> None:
    payload = {
        "schema_version": "commander-harness-v1",
        "candidate_id": "task-001-abcdef12",
        "task_id": "task-001",
        "source_report_path": "D:/tmp/report.json",
        "source_summary": "Memory retrieval layer completed.",
        "observed_pattern": "The same recovery path keeps showing up in tasks.",
        "recommended_layer": "workflow",
        "recommended_target": "workflow.yaml",
        "evidence": ["source_report=D:/tmp/report.json"],
        "rationale": ["bad layer"],
        "validation_requirements": [],
        "approval_required": True,
        "status": "candidate",
        "created_at": "2026-04-11T00:00:00Z",
    }

    try:
        validate_instance(payload, load_schema(IMPROVEMENT_SCHEMA_PATH))
    except SchemaValidationError:
        return
    raise AssertionError("Expected schema validation to fail for invalid recommended_layer")


def test_propose_improvement_cli_recommends_doc_layer(tmp_path: Path) -> None:
    report_path = tmp_path / "report-doc.json"
    report_path.write_text(
        json.dumps(
            make_report(
                task_id="task-doc",
                changed_files=["docs/工程排障入口矩阵.md"],
                summary="Added a stable troubleshooting matrix.",
            ),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    result = run_script("commander_propose_improvement.py", "--report", str(report_path))

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["recommended_layer"] == "doc"
    assert payload["recommended_target"] == "docs/工程排障入口矩阵.md"
    output_path = Path(payload["output_path"])
    saved_candidate = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved_candidate["recommended_layer"] == "doc"


def test_propose_improvement_cli_recommends_script_layer(tmp_path: Path) -> None:
    report_path = tmp_path / "report-script.json"
    report_path.write_text(
        json.dumps(
            make_report(
                task_id="task-script",
                changed_files=[
                    "commander/transport/scripts/commander_memory_search.py",
                    "tests/test_commander_memory_search.py",
                ],
                summary="Added a reusable memory retrieval entry.",
            ),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    result = run_script("commander_propose_improvement.py", "--report", str(report_path))

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["recommended_layer"] == "script"
    assert payload["recommended_target"] == "commander/transport/scripts/commander_memory_search.py"


def test_propose_improvement_cli_recommends_skill_layer(tmp_path: Path) -> None:
    report_path = tmp_path / "report-skill.json"
    report_path.write_text(
        json.dumps(
            make_report(
                task_id="task-skill",
                changed_files=["commander/skill-source/commander-reuse-upgrader/SKILL.md"],
                summary="Updated a reusable skill shell.",
            ),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    result = run_script("commander_propose_improvement.py", "--report", str(report_path))

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["recommended_layer"] == "skill"
    assert payload["recommended_target"].endswith("SKILL.md")


def test_propose_improvement_initializes_candidate_lifecycle_fields(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    report_path = tmp_path / "report-init.json"
    write_report(
        report_path,
        task_id="task-init",
        changed_files=["docs/commander-governance.md"],
        summary="Captured a reusable commander governance pattern.",
    )

    result = run_script(
        "commander_propose_improvement.py",
        "--runtime-root",
        str(runtime_root),
        "--report",
        str(report_path),
    )

    assert result.returncode == 0, result.stderr
    candidate, _ = load_candidate_from_output(result)
    validate_instance(candidate, load_schema(IMPROVEMENT_SCHEMA_PATH))
    assert candidate["status"] == "candidate"
    assert candidate["reviewed_at"] is None
    assert candidate["reviewed_by"] is None
    assert candidate["applied_at"] is None
    assert candidate["applied_artifacts"] == []
    assert candidate["archived_at"] is None
    assert len(candidate["history"]) == 1
    assert candidate["history"][0]["action"] == "candidate_created"
    assert candidate["history"][0]["status"] == "candidate"


def test_improvement_candidate_review_apply_archive_doc_lifecycle(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    report_path = tmp_path / "report-doc-lifecycle.json"
    write_report(
        report_path,
        task_id="task-doc-lifecycle",
        changed_files=["docs/commander-governance.md"],
        summary="Documented a stable commander governance pattern.",
    )

    propose = run_script(
        "commander_propose_improvement.py",
        "--runtime-root",
        str(runtime_root),
        "--report",
        str(report_path),
    )
    assert propose.returncode == 0, propose.stderr
    _, candidate_path = load_candidate_from_output(propose)

    review = run_script(
        "commander_review_improvement.py",
        "--candidate",
        str(candidate_path),
        "--decision",
        "approve",
        "--notes",
        "Promote this reuse direction into a controlled handoff.",
        "--reviewer",
        "phase-b-reviewer",
    )
    assert review.returncode == 0, review.stderr
    review_payload = json.loads(review.stdout)
    assert review_payload["status"] == "approved"
    assert review_payload["changed"] is True

    apply_result = run_script(
        "commander_apply_improvement.py",
        "--candidate",
        str(candidate_path),
        "--runtime-root",
        str(runtime_root),
        "--actor",
        "phase-b-applier",
    )
    assert apply_result.returncode == 0, apply_result.stderr
    apply_payload = json.loads(apply_result.stdout)
    assert apply_payload["status"] == "applied"
    output_dir = Path(apply_payload["output_dir"])
    apply_plan_path = output_dir / "apply_plan.md"
    metadata_path = output_dir / "candidate_metadata.json"
    validation_path = output_dir / "validation.json"
    assert apply_plan_path.exists()
    assert metadata_path.exists()
    assert validation_path.exists()
    validation_payload = json.loads(validation_path.read_text(encoding="utf-8"))
    assert validation_payload["valid"] is True
    assert validation_payload["mode"] == "plan_only"

    archive = run_script(
        "commander_archive_improvement.py",
        "--candidate",
        str(candidate_path),
        "--reason",
        "approved_doc_handoff_closed",
        "--actor",
        "phase-b-archiver",
    )
    assert archive.returncode == 0, archive.stderr
    archive_payload = json.loads(archive.stdout)
    assert archive_payload["status"] == "archived"

    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    validate_instance(candidate, load_schema(IMPROVEMENT_SCHEMA_PATH))
    assert candidate["status"] == "archived"
    assert candidate["reviewed_by"] == "phase-b-reviewer"
    assert candidate["applied_by"] == "phase-b-applier"
    assert candidate["archive_reason"] == "approved_doc_handoff_closed"
    assert candidate["applied_artifacts"] == [str(metadata_path), str(apply_plan_path), str(validation_path)]
    assert [entry["action"] for entry in candidate["history"]] == [
        "candidate_created",
        "candidate_reviewed",
        "candidate_applied",
        "candidate_archived",
    ]
    metadata_candidate = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata_candidate["status"] == "applied"
    assert metadata_candidate["applied_by"] == "phase-b-applier"


def test_improvement_candidate_reject_archive_lifecycle(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    report_path = tmp_path / "report-none-lifecycle.json"
    write_report(
        report_path,
        task_id="task-none-lifecycle",
        changed_files=["app.py"],
        summary="Observed a pattern that is not ready for promotion.",
    )

    propose = run_script(
        "commander_propose_improvement.py",
        "--runtime-root",
        str(runtime_root),
        "--report",
        str(report_path),
    )
    assert propose.returncode == 0, propose.stderr
    candidate, candidate_path = load_candidate_from_output(propose)
    assert candidate["recommended_layer"] == "none"

    review = run_script(
        "commander_review_improvement.py",
        "--candidate",
        str(candidate_path),
        "--decision",
        "reject",
        "--notes",
        "Keep observing before promoting this pattern.",
        "--reviewer",
        "phase-b-reviewer",
    )
    assert review.returncode == 0, review.stderr
    assert json.loads(review.stdout)["status"] == "rejected"

    archive = run_script(
        "commander_archive_improvement.py",
        "--candidate",
        str(candidate_path),
        "--reason",
        "candidate_not_ready",
        "--actor",
        "phase-b-archiver",
    )
    assert archive.returncode == 0, archive.stderr

    archived_candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    validate_instance(archived_candidate, load_schema(IMPROVEMENT_SCHEMA_PATH))
    assert archived_candidate["status"] == "archived"
    assert archived_candidate["archive_reason"] == "candidate_not_ready"
    assert [entry["action"] for entry in archived_candidate["history"]] == [
        "candidate_created",
        "candidate_reviewed",
        "candidate_archived",
    ]


def test_improvement_candidate_apply_skill_materializes_validated_artifacts(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    report_path = tmp_path / "report-skill-lifecycle.json"
    write_report(
        report_path,
        task_id="task-skill-lifecycle",
        changed_files=["commander/skill-source/commander-reuse-upgrader/SKILL.md"],
        summary="Updated a reusable skill shell for commander reuse routing.",
    )

    propose = run_script(
        "commander_propose_improvement.py",
        "--runtime-root",
        str(runtime_root),
        "--report",
        str(report_path),
    )
    assert propose.returncode == 0, propose.stderr
    candidate, candidate_path = load_candidate_from_output(propose)
    assert candidate["recommended_layer"] == "skill"

    review = run_script(
        "commander_review_improvement.py",
        "--candidate",
        str(candidate_path),
        "--decision",
        "approve",
        "--notes",
        "This should remain a candidate skill until explicitly promoted.",
        "--reviewer",
        "phase-b-reviewer",
    )
    assert review.returncode == 0, review.stderr

    apply_result = run_script(
        "commander_apply_improvement.py",
        "--candidate",
        str(candidate_path),
        "--runtime-root",
        str(runtime_root),
        "--actor",
        "phase-b-applier",
    )
    assert apply_result.returncode == 0, apply_result.stderr
    apply_payload = json.loads(apply_result.stdout)
    output_dir = Path(apply_payload["output_dir"])
    metadata_path = output_dir / "candidate_metadata.json"
    skill_candidate_path = output_dir / "SKILL.candidate.md"
    validation_path = output_dir / "validation.json"
    assert metadata_path.exists()
    assert skill_candidate_path.exists()
    assert validation_path.exists()
    validation_payload = json.loads(validation_path.read_text(encoding="utf-8"))
    assert validation_payload["valid"] is True
    assert validation_payload["skill_candidate_path"] == str(skill_candidate_path)

    applied_candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    validate_instance(applied_candidate, load_schema(IMPROVEMENT_SCHEMA_PATH))
    assert applied_candidate["status"] == "applied"
    assert applied_candidate["applied_artifacts"] == [
        str(metadata_path),
        str(skill_candidate_path),
        str(validation_path),
    ]
