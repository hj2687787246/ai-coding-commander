from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from commander.transport.scripts.commander_harness import (
    REPORT_SCHEMA_PATH,
    SCHEMA_DIR,
    load_json,
    load_schema,
    normalize_runtime_root,
    validate_instance,
    write_json,
)
from commander.transport.scripts.commander_propose_improvement import (
    IMPROVEMENT_SCHEMA_PATH,
    build_candidate,
)


EXPERIMENT_CONFIG_SCHEMA_PATH = SCHEMA_DIR / "commander_experiment_config.schema.json"


def validate_candidate_workspace(config: dict[str, Any]) -> None:
    workspace = str(config["candidate"]["workspace"])
    normalized_parts = [
        part.lower()
        for part in workspace.replace("\\", "/").split("/")
        if part.strip()
    ]
    if not any("proposer" in part for part in normalized_parts):
        raise ValueError("candidate.workspace must point at a proposer workspace")


def summarize_scores(cases: list[dict[str, Any]], *, higher_is_better: bool) -> dict[str, Any]:
    baseline_total = sum(float(item["baseline_score"]) for item in cases)
    candidate_total = sum(float(item["candidate_score"]) for item in cases)
    case_count = len(cases)
    baseline_average = baseline_total / case_count
    candidate_average = candidate_total / case_count
    raw_delta = candidate_average - baseline_average
    normalized_delta = raw_delta if higher_is_better else -raw_delta
    return {
        "case_count": case_count,
        "baseline_average": baseline_average,
        "candidate_average": candidate_average,
        "delta": normalized_delta,
        "raw_delta": raw_delta,
        "case_ids": [str(item["case_id"]) for item in cases],
    }


def build_experiment_report(
    config: dict[str, Any],
    *,
    config_path: Path,
    runtime_root: Path,
) -> dict[str, Any]:
    scorecard = config["scorecard"]
    higher_is_better = bool(scorecard.get("higher_is_better", True))
    train_summary = summarize_scores(scorecard["train"], higher_is_better=higher_is_better)
    holdout_summary = summarize_scores(scorecard["holdout"], higher_is_better=higher_is_better)
    min_holdout_delta = float(scorecard["min_holdout_delta"])
    keep_candidate = holdout_summary["delta"] > min_holdout_delta
    decision = "keep" if keep_candidate else "discard"
    experiment_id = str(config["experiment_id"])
    report_path = runtime_root / "experiments" / experiment_id / "experiment_report.json"
    return {
        "schema_version": "commander-experiment-result-v1",
        "experiment_id": experiment_id,
        "task_id": str(config["task_id"]),
        "surface": str(config["surface"]),
        "config_path": str(config_path),
        "candidate_workspace": str(config["candidate"]["workspace"]),
        "candidate_workspace_policy": "proposer_workspace_review_only",
        "metric": str(scorecard["metric"]),
        "higher_is_better": higher_is_better,
        "min_holdout_delta": min_holdout_delta,
        "scores": {
            "train": train_summary,
            "holdout": holdout_summary,
        },
        "decision": decision,
        "keep_candidate": keep_candidate,
        "reason": (
            "candidate_holdout_score_improved"
            if keep_candidate
            else "candidate_holdout_score_did_not_clear_threshold"
        ),
        "candidate_review": {
            "entered_candidate_review": False,
            "candidate_path": None,
        },
        "report_path": str(report_path),
    }


def build_candidate_report_payload(config: dict[str, Any], experiment_report: dict[str, Any]) -> dict[str, Any]:
    candidate = config["candidate"]
    surface = str(config["surface"])
    summary = (
        f"Offline experiment {config['experiment_id']} kept candidate {candidate['label']} "
        f"for {surface}; holdout delta={experiment_report['scores']['holdout']['delta']:.4f}."
    )
    return {
        "schema_version": "commander-harness-v1",
        "task_id": str(config["task_id"]),
        "status": "done",
        "summary": summary,
        "changed_files": list(candidate["changed_files"]),
        "verification": [
            {
                "name": "offline_experiment_scorecard",
                "command": f"commander_experiment --config {experiment_report['config_path']}",
                "result": "passed",
                "details": json.dumps(
                    {
                        "experiment_id": experiment_report["experiment_id"],
                        "surface": surface,
                        "holdout_delta": experiment_report["scores"]["holdout"]["delta"],
                        "min_holdout_delta": experiment_report["min_holdout_delta"],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            }
        ],
        "commit": None,
        "risks": [
            "Offline scorecard evidence still requires commander review before applying to live surfaces.",
        ],
        "recommended_next_step": "Review the generated improvement candidate before applying it.",
        "needs_commander_decision": False,
        "result_grade": "closed",
        "next_action_owner": "commander",
        "continuation_mode": "close",
        "decision_reason": "offline_experiment_candidate_kept",
        "split_suggestion": None,
        "needs_user_decision": False,
        "user_decision_reason": None,
        "ready_for_user_delivery": False,
        "harness_metadata": {
            "is_dispatch_draft": False,
        },
    }


def run_experiment(
    config_path: Path,
    *,
    runtime_root: Path,
    output_path: Path | None = None,
) -> dict[str, Any]:
    config = load_json(config_path)
    validate_instance(config, load_schema(EXPERIMENT_CONFIG_SCHEMA_PATH))
    validate_candidate_workspace(config)
    experiment_report = build_experiment_report(
        config,
        config_path=config_path,
        runtime_root=runtime_root,
    )
    resolved_output_path = output_path or Path(str(experiment_report["report_path"]))
    experiment_report["report_path"] = str(resolved_output_path)

    if experiment_report["keep_candidate"]:
        candidate_report = build_candidate_report_payload(config, experiment_report)
        validate_instance(candidate_report, load_schema(REPORT_SCHEMA_PATH))
        candidate_report_path = resolved_output_path.with_name("candidate_source_report.json")
        write_json(candidate_report_path, candidate_report)
        improvement_candidate = build_candidate(
            candidate_report,
            candidate_report_path,
            observed_pattern=(
                f"Offline experiment kept candidate for {experiment_report['surface']} "
                f"with holdout delta {experiment_report['scores']['holdout']['delta']:.4f}."
            ),
        )
        validate_instance(improvement_candidate, load_schema(IMPROVEMENT_SCHEMA_PATH))
        candidate_path = runtime_root / "improvements" / f"{improvement_candidate['task_id']}.candidate.json"
        write_json(candidate_path, improvement_candidate)
        experiment_report["candidate_review"] = {
            "entered_candidate_review": True,
            "candidate_path": str(candidate_path),
            "candidate_id": improvement_candidate["candidate_id"],
            "recommended_layer": improvement_candidate["recommended_layer"],
            "recommended_target": improvement_candidate["recommended_target"],
            "source_report_path": str(candidate_report_path),
        }

    write_json(resolved_output_path, experiment_report)
    return experiment_report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run an offline baseline-vs-candidate commander experiment."
    )
    parser.add_argument("--config", required=True, help="Path to commander experiment config JSON")
    parser.add_argument("--runtime-root", default=None, help="Override runtime root. Defaults to .runtime/commander")
    parser.add_argument("--output", default=None, help="Optional explicit experiment report output path")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config_path = Path(args.config).resolve()
    runtime_root = normalize_runtime_root(args.runtime_root)
    output_path = Path(args.output).resolve() if args.output else None
    result = run_experiment(config_path, runtime_root=runtime_root, output_path=output_path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
