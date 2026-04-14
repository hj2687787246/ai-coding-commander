from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from commander.transport.scripts.commander_harness import load_json, load_schema, utc_now, validate_instance, write_json
from commander.transport.scripts.commander_propose_improvement import (
    IMPROVEMENT_SCHEMA_PATH,
    IMPROVEMENT_STATUS_APPROVED,
    IMPROVEMENT_STATUS_ARCHIVED,
    IMPROVEMENT_STATUS_CANDIDATE,
    IMPROVEMENT_STATUS_REJECTED,
    normalize_candidate_payload,
    transition_candidate,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review a commander improvement candidate.")
    parser.add_argument("--candidate", required=True, help="Path to commander improvement candidate JSON")
    parser.add_argument("--decision", required=True, choices=["approve", "reject"], help="Review decision")
    parser.add_argument("--notes", default=None, help="Optional review notes")
    parser.add_argument("--reviewer", default="commander", help="Actor recording the review")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    candidate_path = Path(args.candidate).resolve()
    candidate = normalize_candidate_payload(load_json(candidate_path))
    validate_instance(candidate, load_schema(IMPROVEMENT_SCHEMA_PATH))

    target_status = IMPROVEMENT_STATUS_APPROVED if args.decision == "approve" else IMPROVEMENT_STATUS_REJECTED
    current_status = candidate.get("status")
    changed = False

    if current_status == IMPROVEMENT_STATUS_ARCHIVED:
        raise SystemExit(f"Archived candidate cannot be reviewed again: {candidate_path}")

    if current_status == target_status:
        updated_candidate = candidate
    else:
        if current_status != IMPROVEMENT_STATUS_CANDIDATE:
            raise SystemExit(
                f"Candidate must be in status={IMPROVEMENT_STATUS_CANDIDATE!r} before review; got {current_status!r}"
            )
        reviewed_at = utc_now()
        updated_candidate = transition_candidate(
            candidate,
            status=target_status,
            action="candidate_reviewed",
            actor=args.reviewer,
            notes=args.notes or f"Commander decision: {args.decision}",
            extra_fields={
                "reviewed_at": reviewed_at,
                "reviewed_by": args.reviewer,
                "review_notes": args.notes,
            },
        )
        changed = True

    validate_instance(updated_candidate, load_schema(IMPROVEMENT_SCHEMA_PATH))
    write_json(candidate_path, updated_candidate)
    print(
        json.dumps(
            {
                "candidate_path": str(candidate_path),
                "candidate_id": updated_candidate["candidate_id"],
                "task_id": updated_candidate["task_id"],
                "changed": changed,
                "status": updated_candidate["status"],
                "reviewed_at": updated_candidate.get("reviewed_at"),
                "reviewed_by": updated_candidate.get("reviewed_by"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
