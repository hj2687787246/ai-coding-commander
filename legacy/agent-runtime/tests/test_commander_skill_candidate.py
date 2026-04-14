from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


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


def make_candidate(*, layer: str = "skill") -> dict[str, object]:
    return {
        "schema_version": "commander-harness-v1",
        "candidate_id": "task-skill-abcdef12",
        "task_id": "task-skill",
        "source_report_path": "D:/tmp/report.json",
        "source_summary": "A repeated reusable process emerged from multiple tasks.",
        "observed_pattern": "The same GitHub digest workflow keeps appearing.",
        "recommended_layer": layer,
        "recommended_target": "commander/skill-source/github-digest/SKILL.md" if layer == "skill" else None,
        "evidence": ["source_report=D:/tmp/report.json", "changed_file=commander/skill-source/github-digest/SKILL.md"],
        "rationale": ["This pattern belongs in a reusable skill shell."],
        "validation_requirements": ["python quick_validate.py <candidate>"],
        "approval_required": True,
        "status": "candidate",
        "created_at": "2026-04-11T00:00:00Z",
    }


def test_generate_skill_candidate_cli_writes_candidate_files(tmp_path: Path) -> None:
    candidate_path = tmp_path / "candidate.json"
    candidate_path.write_text(json.dumps(make_candidate(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    generate = run_script("commander_generate_skill_candidate.py", "--candidate", str(candidate_path))

    assert generate.returncode == 0, generate.stderr
    payload = json.loads(generate.stdout)
    output_dir = Path(payload["output_dir"])
    metadata_path = Path(payload["metadata_path"])
    skill_candidate_path = Path(payload["skill_candidate_path"])

    assert output_dir.exists()
    assert metadata_path.exists()
    assert skill_candidate_path.exists()
    assert "## Activation Guard" in skill_candidate_path.read_text(encoding="utf-8")


def test_generate_skill_candidate_rejects_non_skill_candidate(tmp_path: Path) -> None:
    candidate_path = tmp_path / "candidate.json"
    candidate_path.write_text(
        json.dumps(make_candidate(layer="doc"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    generate = run_script("commander_generate_skill_candidate.py", "--candidate", str(candidate_path))

    assert generate.returncode != 0
    assert "recommended_layer=skill" in generate.stderr


def test_validate_skill_candidate_cli_accepts_generated_candidate(tmp_path: Path) -> None:
    candidate_path = tmp_path / "candidate.json"
    candidate_path.write_text(json.dumps(make_candidate(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    generate = run_script("commander_generate_skill_candidate.py", "--candidate", str(candidate_path))
    assert generate.returncode == 0, generate.stderr
    payload = json.loads(generate.stdout)

    validate = run_script("commander_validate_skill_candidate.py", "--candidate-dir", payload["output_dir"])

    assert validate.returncode == 0, validate.stderr
    validate_payload = json.loads(validate.stdout)
    assert validate_payload["valid"] is True
