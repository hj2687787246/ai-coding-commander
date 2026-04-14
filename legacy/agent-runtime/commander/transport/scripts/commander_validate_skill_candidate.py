from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from commander.transport.scripts.commander_harness import SCHEMA_DIR, load_json, load_schema, validate_instance
from commander.transport.scripts.commander_propose_improvement import normalize_candidate_payload


IMPROVEMENT_SCHEMA_PATH = SCHEMA_DIR / "commander_improvement_candidate.schema.json"
REQUIRED_HEADINGS = (
    "# Skill Candidate:",
    "## Trigger",
    "## Proposed Flow",
    "## Evidence",
    "## Rationale",
    "## Validation",
    "## Activation Guard",
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a generated commander skill candidate.")
    parser.add_argument("--candidate-dir", required=True, help="Directory created by commander_generate_skill_candidate.py")
    return parser.parse_args(argv)


def validate_skill_candidate_dir(candidate_dir: Path) -> dict[str, object]:
    metadata_path = candidate_dir / "candidate_metadata.json"
    skill_candidate_path = candidate_dir / "SKILL.candidate.md"

    if not metadata_path.exists():
        raise SystemExit(f"Missing metadata file: {metadata_path}")
    if not skill_candidate_path.exists():
        raise SystemExit(f"Missing skill candidate file: {skill_candidate_path}")

    candidate = normalize_candidate_payload(load_json(metadata_path))
    validate_instance(candidate, load_schema(IMPROVEMENT_SCHEMA_PATH))
    if candidate.get("recommended_layer") != "skill":
        raise SystemExit("candidate_metadata.json is not a skill-layer candidate.")

    skill_text = skill_candidate_path.read_text(encoding="utf-8")
    missing_headings = [heading for heading in REQUIRED_HEADINGS if heading not in skill_text]
    if missing_headings:
        raise SystemExit(f"Skill candidate is missing required headings: {missing_headings}")

    return {
        "candidate_id": candidate["candidate_id"],
        "task_id": candidate["task_id"],
        "valid": True,
        "metadata_path": str(metadata_path),
        "skill_candidate_path": str(skill_candidate_path),
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = validate_skill_candidate_dir(Path(args.candidate_dir).resolve())
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
