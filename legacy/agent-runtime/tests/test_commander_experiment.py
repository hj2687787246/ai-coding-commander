from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from commander.transport.scripts.commander_harness import load_schema, validate_instance


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON_EXE = Path(sys.executable)
EXPERIMENT_SCHEMA_PATH = (
    PROJECT_ROOT / "commander" / "transport" / "schemas" / "commander_experiment_config.schema.json"
)
IMPROVEMENT_SCHEMA_PATH = (
    PROJECT_ROOT / "commander" / "transport" / "schemas" / "commander_improvement_candidate.schema.json"
)


def run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(PYTHON_EXE), "-m", "commander.transport.scripts.commander_experiment", *args],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def make_config(*, candidate_holdout_score: float) -> dict[str, object]:
    return {
        "schema_version": "commander-experiment-v1",
        "experiment_id": "exp-routing-001",
        "task_id": "task-phase-d",
        "surface": "routing_context_policy",
        "baseline": {
            "label": "baseline-routing-policy",
            "changed_files": ["commander/transport/scripts/commander_context_router.py"],
        },
        "candidate": {
            "label": "candidate-routing-policy",
            "workspace": ".runtime/commander/experiments/proposer_workspaces/exp-routing-001",
            "changed_files": ["commander/transport/scripts/commander_context_router.py"],
        },
        "scorecard": {
            "metric": "accuracy",
            "min_holdout_delta": 0.05,
            "higher_is_better": True,
            "train": [
                {
                    "case_id": "train-001",
                    "baseline_score": 0.60,
                    "candidate_score": 0.75,
                }
            ],
            "holdout": [
                {
                    "case_id": "holdout-001",
                    "baseline_score": 0.60,
                    "candidate_score": candidate_holdout_score,
                }
            ],
        },
    }


def write_config(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_experiment_config_schema_accepts_valid_payload() -> None:
    validate_instance(make_config(candidate_holdout_score=0.70), load_schema(EXPERIMENT_SCHEMA_PATH))


def test_experiment_keeps_candidate_and_enters_improvement_review(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    config_path = tmp_path / "experiment.json"
    write_config(config_path, make_config(candidate_holdout_score=0.70))

    result = run_script("--runtime-root", str(runtime_root), "--config", str(config_path))

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["decision"] == "keep"
    assert payload["candidate_review"]["entered_candidate_review"] is True
    report_path = Path(payload["report_path"])
    candidate_path = Path(payload["candidate_review"]["candidate_path"])
    source_report_path = Path(payload["candidate_review"]["source_report_path"])
    assert report_path.exists()
    assert candidate_path.exists()
    assert source_report_path.exists()
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    validate_instance(candidate, load_schema(IMPROVEMENT_SCHEMA_PATH))
    assert candidate["status"] == "candidate"
    assert candidate["recommended_layer"] == "script"
    assert candidate["source_report_path"] == str(source_report_path)


def test_experiment_discards_candidate_without_review_candidate(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    config_path = tmp_path / "experiment.json"
    write_config(config_path, make_config(candidate_holdout_score=0.62))

    result = run_script("--runtime-root", str(runtime_root), "--config", str(config_path))

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["decision"] == "discard"
    assert payload["candidate_review"]["entered_candidate_review"] is False
    assert Path(payload["report_path"]).exists()
    assert not (runtime_root / "improvements" / "task-phase-d.candidate.json").exists()


def test_experiment_rejects_candidate_outside_proposer_workspace(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    config_path = tmp_path / "experiment.json"
    payload = make_config(candidate_holdout_score=0.70)
    candidate = payload["candidate"]
    assert isinstance(candidate, dict)
    candidate["workspace"] = ".runtime/commander/live_surfaces/routing"
    write_config(config_path, payload)

    result = run_script("--runtime-root", str(runtime_root), "--config", str(config_path))

    assert result.returncode != 0
    assert "proposer workspace" in result.stderr
