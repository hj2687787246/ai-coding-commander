from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from commander.transport.scripts.commander_generate_skill_candidate import render_skill_candidate
from commander.transport.scripts.commander_harness import (
    load_json,
    load_schema,
    normalize_runtime_root,
    utc_now,
    validate_instance,
    write_json,
)
from commander.transport.scripts.commander_propose_improvement import (
    DOC_LAYER,
    IMPROVEMENT_SCHEMA_PATH,
    IMPROVEMENT_STATUS_APPLIED,
    IMPROVEMENT_STATUS_APPROVED,
    NONE_LAYER,
    SCRIPT_LAYER,
    SKILL_LAYER,
    normalize_candidate_payload,
    transition_candidate,
)
from commander.transport.scripts.commander_validate_skill_candidate import validate_skill_candidate_dir


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply an approved commander improvement candidate into a controlled artifact.")
    parser.add_argument("--candidate", required=True, help="Path to commander improvement candidate JSON")
    parser.add_argument("--runtime-root", default=None, help="Override runtime root. Defaults to .runtime/commander")
    parser.add_argument("--actor", default="commander", help="Actor applying the candidate")
    parser.add_argument("--output-dir", default=None, help="Optional explicit apply artifact directory")
    return parser.parse_args(argv)


def default_output_dir(runtime_root: Path, candidate_id: str) -> Path:
    return runtime_root / "improvement_actions" / candidate_id


def render_apply_plan(candidate: dict[str, object]) -> str:
    evidence = candidate.get("evidence", [])
    rationale = candidate.get("rationale", [])
    validation_requirements = candidate.get("validation_requirements", [])

    def render_list(items: object) -> list[str]:
        if not isinstance(items, list) or not items:
            return ["- (none)"]
        return [f"- {item}" for item in items if isinstance(item, str)]

    lines = [
        f"# Improvement Apply Plan: {candidate['candidate_id']}",
        "",
        f"- Task ID: {candidate['task_id']}",
        f"- Recommended Layer: {candidate['recommended_layer']}",
        f"- Recommended Target: {candidate.get('recommended_target') or '(none)'}",
        "",
        "## Source Summary",
        f"- {candidate['source_summary']}",
        "",
        "## Observed Pattern",
        f"- {candidate['observed_pattern']}",
        "",
        "## Evidence",
        *render_list(evidence),
        "",
        "## Rationale",
        *render_list(rationale),
        "",
        "## Validation Requirements",
        *render_list(validation_requirements),
        "",
        "## Controlled Apply Guard",
        "- This artifact records an approved reuse direction without editing live repo assets directly.",
        "- Promotion into live docs/scripts/skills remains a separate commanded action.",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    runtime_root = normalize_runtime_root(args.runtime_root)
    candidate_path = Path(args.candidate).resolve()
    candidate = normalize_candidate_payload(load_json(candidate_path))
    validate_instance(candidate, load_schema(IMPROVEMENT_SCHEMA_PATH))

    current_status = candidate.get("status")
    if current_status not in {IMPROVEMENT_STATUS_APPROVED, IMPROVEMENT_STATUS_APPLIED}:
        raise SystemExit(
            f"Candidate must be approved before apply; got status={current_status!r} for {candidate_path}"
        )

    output_dir = Path(args.output_dir).resolve() if args.output_dir else default_output_dir(runtime_root, str(candidate["candidate_id"]))
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = output_dir / "candidate_metadata.json"
    artifacts: list[str] = []

    if candidate.get("recommended_layer") == SKILL_LAYER:
        skill_candidate_path = output_dir / "SKILL.candidate.md"
        skill_candidate_path.write_text(render_skill_candidate(candidate), encoding="utf-8")
        applied_summary = "Generated and validated a non-live skill candidate."
        artifacts = [
            str(metadata_path),
            str(skill_candidate_path),
            str(output_dir / "validation.json"),
        ]
    elif candidate.get("recommended_layer") in {DOC_LAYER, SCRIPT_LAYER, NONE_LAYER}:
        apply_plan_path = output_dir / "apply_plan.md"
        apply_plan_path.write_text(render_apply_plan(candidate), encoding="utf-8")
        applied_summary = f"Materialized a controlled {candidate.get('recommended_layer')} improvement handoff."
        artifacts = [
            str(metadata_path),
            str(apply_plan_path),
            str(output_dir / "validation.json"),
        ]
    else:
        raise SystemExit(f"Unsupported recommended_layer={candidate.get('recommended_layer')!r}")

    if current_status == IMPROVEMENT_STATUS_APPLIED:
        updated_candidate = normalize_candidate_payload(candidate)
        updated_candidate["applied_artifacts"] = artifacts
        updated_candidate["applied_summary"] = applied_summary
        updated_candidate["applied_by"] = args.actor
        changed = False
    else:
        applied_at = utc_now()
        updated_candidate = transition_candidate(
            candidate,
            status=IMPROVEMENT_STATUS_APPLIED,
            action="candidate_applied",
            actor=args.actor,
            notes=applied_summary,
            artifacts=artifacts,
            extra_fields={
                "applied_at": applied_at,
                "applied_by": args.actor,
                "applied_summary": applied_summary,
                "applied_artifacts": artifacts,
            },
        )
        changed = True

    validation_path = output_dir / "validation.json"
    validate_instance(updated_candidate, load_schema(IMPROVEMENT_SCHEMA_PATH))
    write_json(metadata_path, updated_candidate)

    if candidate.get("recommended_layer") == SKILL_LAYER:
        validation_payload = validate_skill_candidate_dir(output_dir)
        write_json(validation_path, validation_payload)
    else:
        write_json(
            validation_path,
            {
                "candidate_id": candidate["candidate_id"],
                "task_id": candidate["task_id"],
                "valid": True,
                "mode": "plan_only",
                "recommended_layer": candidate.get("recommended_layer"),
                "recommended_target": candidate.get("recommended_target"),
                "validation_requirements": candidate.get("validation_requirements", []),
            },
        )

    write_json(candidate_path, updated_candidate)
    print(
        json.dumps(
            {
                "candidate_path": str(candidate_path),
                "candidate_id": updated_candidate["candidate_id"],
                "task_id": updated_candidate["task_id"],
                "changed": changed,
                "status": updated_candidate["status"],
                "output_dir": str(output_dir),
                "applied_summary": updated_candidate.get("applied_summary"),
                "applied_artifacts": updated_candidate.get("applied_artifacts", []),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
