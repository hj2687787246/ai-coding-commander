from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from commander.transport.scripts.commander_harness import (
    SCHEMA_DIR,
    load_json,
    load_schema,
    normalize_runtime_root,
    validate_instance,
    write_json,
)
from commander.transport.scripts.commander_propose_improvement import normalize_candidate_payload


IMPROVEMENT_SCHEMA_PATH = SCHEMA_DIR / "commander_improvement_candidate.schema.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a non-live skill candidate from an improvement candidate.")
    parser.add_argument("--candidate", required=True, help="Path to commander improvement candidate JSON")
    parser.add_argument("--runtime-root", default=None, help="Override runtime root. Defaults to .runtime/commander")
    parser.add_argument("--output-dir", default=None, help="Optional explicit output directory")
    return parser.parse_args(argv)


def render_skill_candidate(candidate: dict[str, object]) -> str:
    target = candidate.get("recommended_target")
    evidence = candidate.get("evidence", [])
    rationale = candidate.get("rationale", [])
    validation_requirements = candidate.get("validation_requirements", [])

    def render_list(items: object) -> list[str]:
        if not isinstance(items, list) or not items:
            return ["- (none)"]
        return [f"- {item}" for item in items if isinstance(item, str)]

    lines = [
        f"# Skill Candidate: {candidate['candidate_id']}",
        "",
        f"- Task ID: {candidate['task_id']}",
        f"- Target Skill Path: {target if isinstance(target, str) and target else '(new skill candidate)'}",
        "- Status: candidate_only",
        "",
        "## Trigger",
        f"- {candidate['observed_pattern']}",
        "",
        "## Proposed Flow",
        "- Read the repo markdown truth sources first.",
        "- Reuse the observed pattern only when the same trigger appears again.",
        "- Keep project facts in repo docs instead of copying them into the skill body.",
        "",
        "## Evidence",
        *render_list(evidence),
        "",
        "## Rationale",
        *render_list(rationale),
        "",
        "## Validation",
        *render_list(validation_requirements),
        "",
        "## Activation Guard",
        "- Do not overwrite any live SKILL.md directly from this candidate.",
        "- Validate the candidate first, then let the commander decide whether to promote it.",
    ]
    return "\n".join(lines) + "\n"


def default_output_dir(runtime_root: Path, candidate_id: str) -> Path:
    return runtime_root / "skill_candidates" / candidate_id


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    runtime_root = normalize_runtime_root(args.runtime_root)
    candidate_path = Path(args.candidate).resolve()
    candidate = normalize_candidate_payload(load_json(candidate_path))
    validate_instance(candidate, load_schema(IMPROVEMENT_SCHEMA_PATH))

    if candidate.get("recommended_layer") != "skill":
        raise SystemExit("Only improvement candidates with recommended_layer=skill can generate skill candidates.")

    output_dir = Path(args.output_dir).resolve() if args.output_dir else default_output_dir(runtime_root, str(candidate["candidate_id"]))
    output_dir.mkdir(parents=True, exist_ok=True)

    metadata_path = output_dir / "candidate_metadata.json"
    skill_candidate_path = output_dir / "SKILL.candidate.md"

    write_json(metadata_path, candidate)
    skill_candidate_path.write_text(render_skill_candidate(candidate), encoding="utf-8")

    print(
        json.dumps(
            {
                "candidate_id": candidate["candidate_id"],
                "task_id": candidate["task_id"],
                "output_dir": str(output_dir),
                "metadata_path": str(metadata_path),
                "skill_candidate_path": str(skill_candidate_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
