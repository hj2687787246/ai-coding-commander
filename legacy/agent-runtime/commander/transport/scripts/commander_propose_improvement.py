from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import uuid4

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from commander.transport.scripts.commander_harness import (
    REPORT_SCHEMA_PATH,
    SCHEMA_DIR,
    load_json,
    load_schema,
    normalize_runtime_root,
    utc_now,
    validate_instance,
    write_json,
)


IMPROVEMENT_SCHEMA_PATH = SCHEMA_DIR / "commander_improvement_candidate.schema.json"
DOC_LAYER = "doc"
SCRIPT_LAYER = "script"
SKILL_LAYER = "skill"
NONE_LAYER = "none"
IMPROVEMENT_STATUS_CANDIDATE = "candidate"
IMPROVEMENT_STATUS_APPROVED = "approved"
IMPROVEMENT_STATUS_REJECTED = "rejected"
IMPROVEMENT_STATUS_APPLIED = "applied"
IMPROVEMENT_STATUS_ARCHIVED = "archived"
IMPROVEMENT_STATUS_IMPLEMENTED = "implemented"
IMPROVEMENT_STATUSES = (
    IMPROVEMENT_STATUS_CANDIDATE,
    IMPROVEMENT_STATUS_APPROVED,
    IMPROVEMENT_STATUS_REJECTED,
    IMPROVEMENT_STATUS_APPLIED,
    IMPROVEMENT_STATUS_ARCHIVED,
    IMPROVEMENT_STATUS_IMPLEMENTED,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Propose a reuse-layer improvement candidate from a worker report.")
    parser.add_argument("--report", required=True, help="Path to an ingested or worker report JSON file")
    parser.add_argument("--runtime-root", default=None, help="Override runtime root. Defaults to .runtime/commander")
    parser.add_argument("--observed-pattern", default=None, help="Optional override for the observed repeated pattern")
    parser.add_argument("--output", default=None, help="Optional explicit output path for the candidate JSON")
    return parser.parse_args(argv)


def normalize_changed_files(report_payload: dict[str, object]) -> list[str]:
    raw_files = report_payload.get("changed_files", [])
    if not isinstance(raw_files, list):
        return []
    return [str(item) for item in raw_files if isinstance(item, str) and item.strip()]


def infer_recommended_layer(changed_files: list[str]) -> tuple[str, str | None, list[str]]:
    normalized_files = [item.replace("\\", "/") for item in changed_files]

    skill_targets = [item for item in normalized_files if item.endswith("SKILL.md") or "/skills/" in item]
    if skill_targets:
        return (
            SKILL_LAYER,
            skill_targets[0],
            [
                "Changed files already point at a skill boundary.",
                "This pattern is better captured as a reusable process shell than as project facts.",
            ],
        )

    script_targets = [
        item
        for item in normalized_files
        if item.startswith("scripts/") or item.startswith("schemas/") or "/scripts/" in item or "/schemas/" in item
    ]
    if script_targets:
        return (
            SCRIPT_LAYER,
            script_targets[0],
            [
                "Changed files point at executable or machine-readable assets.",
                "This pattern is a better fit for a repeatable script-level capability.",
            ],
        )

    doc_targets = [item for item in normalized_files if item.startswith("docs/") or "/docs/" in item]
    if doc_targets:
        return (
            DOC_LAYER,
            doc_targets[0],
            [
                "Changed files point at stable markdown truth sources.",
                "This pattern should stay in repo docs before it is promoted to scripts or skills.",
            ],
        )

    return (
        NONE_LAYER,
        None,
        [
            "Changed files do not point at a clear reuse layer yet.",
            "Keep observing real tasks before promoting this pattern.",
        ],
    )


def build_validation_requirements(report_payload: dict[str, object]) -> list[str]:
    raw_checks = report_payload.get("verification", [])
    if not isinstance(raw_checks, list):
        return []

    requirements: list[str] = []
    for item in raw_checks:
        if isinstance(item, str):
            requirements.append(item)
            continue
        if isinstance(item, dict):
            command = item.get("command")
            name = item.get("name")
            result = item.get("result")
            if isinstance(command, str) and command.strip():
                requirements.append(command.strip())
            elif isinstance(name, str) and name.strip():
                requirements.append(name.strip())
            elif isinstance(result, str) and result.strip():
                requirements.append(result.strip())
    return requirements


def build_evidence(report_payload: dict[str, object], changed_files: list[str], report_path: Path) -> list[str]:
    evidence: list[str] = [f"source_report={report_path}"]
    summary = report_payload.get("summary")
    if isinstance(summary, str) and summary.strip():
        evidence.append(f"summary={summary.strip()}")

    evidence.extend(f"changed_file={item}" for item in changed_files[:5])

    for requirement in build_validation_requirements(report_payload)[:5]:
        evidence.append(f"verification={requirement}")

    return evidence


def build_observed_pattern(report_payload: dict[str, object], override: str | None) -> str:
    if isinstance(override, str) and override.strip():
        return override.strip()

    summary = report_payload.get("summary")
    if isinstance(summary, str) and summary.strip():
        return summary.strip()

    recommended = report_payload.get("recommended_next_step")
    if isinstance(recommended, str) and recommended.strip():
        return recommended.strip()

    return "Commander observed a reusable pattern but the report summary was empty."


def build_history_entry(
    *,
    action: str,
    status: str,
    actor: str,
    notes: str | None = None,
    artifacts: list[str] | None = None,
    timestamp: str | None = None,
) -> dict[str, object]:
    return {
        "timestamp": timestamp or utc_now(),
        "action": action,
        "status": status,
        "actor": actor,
        "notes": notes,
        "artifacts": artifacts or [],
    }


def normalize_candidate_payload(candidate_payload: dict[str, object]) -> dict[str, object]:
    normalized = dict(candidate_payload)
    status = str(normalized.get("status") or IMPROVEMENT_STATUS_CANDIDATE)
    if status == IMPROVEMENT_STATUS_IMPLEMENTED:
        status = IMPROVEMENT_STATUS_APPLIED
    normalized["status"] = status
    normalized.setdefault("reviewed_at", None)
    normalized.setdefault("reviewed_by", None)
    normalized.setdefault("review_notes", None)
    normalized.setdefault("applied_at", None)
    normalized.setdefault("applied_by", None)
    normalized.setdefault("applied_summary", None)
    normalized.setdefault("applied_artifacts", [])
    normalized.setdefault("archived_at", None)
    normalized.setdefault("archive_reason", None)
    raw_history = normalized.get("history")
    history = raw_history if isinstance(raw_history, list) else []
    if not history:
        history = [
            build_history_entry(
                action="candidate_created",
                status=IMPROVEMENT_STATUS_CANDIDATE,
                actor="commander_ingest",
                notes="Candidate emitted from trusted report ingest.",
                timestamp=str(normalized.get("created_at") or utc_now()),
            )
        ]
    normalized["history"] = history
    return normalized


def transition_candidate(
    candidate_payload: dict[str, object],
    *,
    status: str,
    action: str,
    actor: str,
    notes: str | None = None,
    artifacts: list[str] | None = None,
    extra_fields: dict[str, object] | None = None,
) -> dict[str, object]:
    normalized = normalize_candidate_payload(candidate_payload)
    normalized["status"] = status
    if extra_fields:
        normalized.update(extra_fields)
    history = normalized.get("history")
    if not isinstance(history, list):
        history = []
    history.append(
        build_history_entry(
            action=action,
            status=status,
            actor=actor,
            notes=notes,
            artifacts=artifacts,
        )
    )
    normalized["history"] = history
    return normalized


def build_candidate(report_payload: dict[str, object], report_path: Path, *, observed_pattern: str) -> dict[str, object]:
    changed_files = normalize_changed_files(report_payload)
    layer, target, rationale = infer_recommended_layer(changed_files)
    task_id = str(report_payload.get("task_id") or "unknown-task")
    candidate_id = f"{task_id}-{uuid4().hex[:8]}"
    source_summary = str(report_payload.get("summary") or observed_pattern)
    validation_requirements = build_validation_requirements(report_payload)
    created_at = utc_now()

    return normalize_candidate_payload(
        {
        "schema_version": "commander-harness-v1",
        "candidate_id": candidate_id,
        "task_id": task_id,
        "source_report_path": str(report_path),
        "source_summary": source_summary,
        "observed_pattern": observed_pattern,
        "recommended_layer": layer,
        "recommended_target": target,
        "evidence": build_evidence(report_payload, changed_files, report_path),
        "rationale": rationale,
        "validation_requirements": validation_requirements,
        "approval_required": True,
        "status": IMPROVEMENT_STATUS_CANDIDATE,
        "created_at": created_at,
        "reviewed_at": None,
        "reviewed_by": None,
        "review_notes": None,
        "applied_at": None,
        "applied_by": None,
        "applied_summary": None,
        "applied_artifacts": [],
        "archived_at": None,
        "archive_reason": None,
        "history": [
            build_history_entry(
                action="candidate_created",
                status=IMPROVEMENT_STATUS_CANDIDATE,
                actor="commander_ingest",
                notes="Candidate emitted from trusted report ingest.",
                timestamp=created_at,
            )
        ],
    }
    )


def default_output_path(runtime_root: Path, task_id: str) -> Path:
    return runtime_root / "improvements" / f"{task_id}.candidate.json"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report_path = Path(args.report).resolve()
    runtime_root = normalize_runtime_root(args.runtime_root)

    report_payload = load_json(report_path)
    validate_instance(report_payload, load_schema(REPORT_SCHEMA_PATH))

    observed_pattern = build_observed_pattern(report_payload, args.observed_pattern)
    candidate = build_candidate(report_payload, report_path, observed_pattern=observed_pattern)
    validate_instance(candidate, load_schema(IMPROVEMENT_SCHEMA_PATH))

    output_path = Path(args.output).resolve() if args.output else default_output_path(runtime_root, candidate["task_id"])
    write_json(output_path, candidate)

    print(
        json.dumps(
            {
                "candidate_id": candidate["candidate_id"],
                "task_id": candidate["task_id"],
                "recommended_layer": candidate["recommended_layer"],
                "recommended_target": candidate["recommended_target"],
                "output_path": str(output_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
