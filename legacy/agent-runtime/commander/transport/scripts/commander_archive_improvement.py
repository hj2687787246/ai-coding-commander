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
    IMPROVEMENT_STATUS_APPLIED,
    IMPROVEMENT_STATUS_ARCHIVED,
    IMPROVEMENT_STATUS_REJECTED,
    normalize_candidate_payload,
    transition_candidate,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Archive a closed commander improvement candidate.")
    parser.add_argument("--candidate", required=True, help="Path to commander improvement candidate JSON")
    parser.add_argument("--reason", default="improvement_lifecycle_closed", help="Why the candidate is being archived")
    parser.add_argument("--actor", default="commander", help="Actor archiving the candidate")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    candidate_path = Path(args.candidate).resolve()
    candidate = normalize_candidate_payload(load_json(candidate_path))
    validate_instance(candidate, load_schema(IMPROVEMENT_SCHEMA_PATH))

    current_status = candidate.get("status")
    changed = False
    if current_status == IMPROVEMENT_STATUS_ARCHIVED:
        updated_candidate = candidate
    else:
        if current_status not in {IMPROVEMENT_STATUS_REJECTED, IMPROVEMENT_STATUS_APPLIED}:
            raise SystemExit(
                f"Candidate can only be archived from rejected/applied; got status={current_status!r} for {candidate_path}"
            )
        archived_at = utc_now()
        updated_candidate = transition_candidate(
            candidate,
            status=IMPROVEMENT_STATUS_ARCHIVED,
            action="candidate_archived",
            actor=args.actor,
            notes=args.reason,
            extra_fields={
                "archived_at": archived_at,
                "archive_reason": args.reason,
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
                "archived_at": updated_candidate.get("archived_at"),
                "archive_reason": updated_candidate.get("archive_reason"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
