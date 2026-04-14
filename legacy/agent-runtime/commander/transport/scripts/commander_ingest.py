from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from commander.transport.scripts.commander_harness import (
    PACKET_SCHEMA_PATH,
    REPORT_SCHEMA_PATH,
    SchemaValidationError,
    ensure_report_ready_for_ingest,
    append_event,
    load_events,
    load_json,
    load_schema,
    normalize_runtime_root,
    refresh_commander_task_catalog,
    refresh_status,
    resolve_task_paths,
    utc_now,
    validate_instance,
    write_json,
)
from commander.transport.scripts.commander_propose_improvement import (
    IMPROVEMENT_SCHEMA_PATH,
    build_candidate,
    build_observed_pattern,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest a structured worker report into commander runtime."
    )
    parser.add_argument(
        "--runtime-root",
        default=None,
        help="Override runtime root. Defaults to .runtime/commander",
    )
    parser.add_argument(
        "--report", required=True, help="Path to a worker-produced report JSON file"
    )
    parser.add_argument(
        "--idempotency-key", default=None, help="Optional graph node idempotency key"
    )
    return parser.parse_args(argv)


def _safe_idempotency_key(idempotency_key: str) -> str:
    return (
        re.sub(r"[^A-Za-z0-9_.-]+", "-", idempotency_key).strip("-")
        or "idempotent-report"
    )


def archived_report_name(idempotency_key: str | None = None) -> str:
    if idempotency_key:
        return f"{_safe_idempotency_key(idempotency_key)}.json"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}.json"


def _has_idempotent_event(paths, event_type: str, idempotency_key: str | None) -> bool:
    if not idempotency_key:
        return False
    for event in load_events(paths.events_path):
        detail = event.get("detail") if isinstance(event.get("detail"), dict) else {}
        if (
            event.get("event_type") == event_type
            and detail.get("idempotency_key") == idempotency_key
        ):
            return True
    return False


def _normalize_repo_path(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    normalized = normalized.strip("/")
    return normalized or None


def _paths_overlap(left: str, right: str) -> bool:
    if left == right:
        return True
    return left.startswith(f"{right}/") or right.startswith(f"{left}/")


def _validate_changed_files_against_packet(
    report_payload: dict[str, object],
    packet_payload: dict[str, object],
) -> dict[str, object]:
    changed_files = [
        normalized
        for item in report_payload.get("changed_files", [])
        if (normalized := _normalize_repo_path(item)) is not None
    ]
    forbidden_paths = [
        normalized
        for item in packet_payload.get("forbidden_paths", [])
        if (normalized := _normalize_repo_path(item)) is not None
    ]
    owned_paths = [
        normalized
        for item in packet_payload.get("owned_paths", [])
        if (normalized := _normalize_repo_path(item)) is not None
    ]
    forbidden_hits: list[dict[str, str]] = []
    owned_scope_misses: list[str] = []

    for changed_path in changed_files:
        for forbidden_path in forbidden_paths:
            if _paths_overlap(changed_path, forbidden_path):
                forbidden_hits.append(
                    {
                        "changed_file": changed_path,
                        "forbidden_path": forbidden_path,
                    }
                )
        if owned_paths and not any(
            _paths_overlap(changed_path, owned_path) for owned_path in owned_paths
        ):
            owned_scope_misses.append(changed_path)

    if forbidden_hits:
        first_hit = forbidden_hits[0]
        raise SchemaValidationError(
            "Report changed_files touches forbidden_path: "
            f"{first_hit['changed_file']} overlaps {first_hit['forbidden_path']}"
        )
    if owned_scope_misses:
        raise SchemaValidationError(
            "Report changed_files escapes owned_paths: "
            + ", ".join(owned_scope_misses)
        )
    return {
        "changed_files": changed_files,
        "forbidden_paths": forbidden_paths,
        "owned_paths": owned_paths,
        "forbidden_hit_count": len(forbidden_hits),
        "owned_scope_miss_count": len(owned_scope_misses),
    }


def ingest_worker_report(
    runtime_root: str | Path | None,
    report_payload: dict[str, object],
    *,
    source_report_path: str | Path | None = None,
    idempotency_key: str | None = None,
) -> dict[str, object]:
    resolved_runtime_root = normalize_runtime_root(runtime_root)
    validate_instance(report_payload, load_schema(REPORT_SCHEMA_PATH))
    ensure_report_ready_for_ingest(report_payload)

    task_id = str(report_payload["task_id"])
    paths = resolve_task_paths(resolved_runtime_root, task_id)
    if not paths.packet_path.exists():
        raise SchemaValidationError(
            f"Missing packet for task {task_id}: {paths.packet_path}"
        )

    packet_payload = load_json(paths.packet_path)
    validate_instance(packet_payload, load_schema(PACKET_SCHEMA_PATH))
    changed_file_governance = _validate_changed_files_against_packet(
        report_payload, packet_payload
    )

    report_payload.setdefault("created_at", utc_now())
    report_payload.setdefault("schema_version", "commander-harness-v1")
    write_json(paths.report_path, report_payload)
    archived_report_path = paths.reports_dir / archived_report_name(idempotency_key)
    archived_report_written = False
    if not archived_report_path.exists() or not idempotency_key:
        write_json(archived_report_path, report_payload)
        archived_report_written = True

    report_event_appended = False
    if not _has_idempotent_event(paths, "task_report_ingested", idempotency_key):
        append_event(
            paths,
            "task_report_ingested",
            {
                "worker_status": report_payload["status"],
                "needs_commander_decision": report_payload["needs_commander_decision"],
                "changed_file_governance": changed_file_governance,
                "idempotency_key": idempotency_key,
            },
        )
        report_event_appended = True

    candidate_created = False
    candidate_event_appended = False
    if idempotency_key and paths.improvement_candidate_path.exists():
        candidate = load_json(paths.improvement_candidate_path)
    else:
        candidate = build_candidate(
            report_payload,
            Path(source_report_path).resolve()
            if source_report_path is not None
            else paths.report_path,
            observed_pattern=build_observed_pattern(report_payload, None),
        )
        validate_instance(candidate, load_schema(IMPROVEMENT_SCHEMA_PATH))
        write_json(paths.improvement_candidate_path, candidate)
        candidate_created = True

    if not _has_idempotent_event(
        paths, "task_improvement_candidate_emitted", idempotency_key
    ):
        append_event(
            paths,
            "task_improvement_candidate_emitted",
            {
                "candidate_id": candidate["candidate_id"],
                "candidate_path": str(paths.improvement_candidate_path),
                "recommended_layer": candidate["recommended_layer"],
                "recommended_target": candidate["recommended_target"],
                "idempotency_key": idempotency_key,
            },
        )
        candidate_event_appended = True

    status = refresh_status(paths)
    refresh_commander_task_catalog(paths, event_type="task_report_ingested")
    return {
        "task_id": task_id,
        "worker_status": report_payload["status"],
        "needs_commander_decision": report_payload["needs_commander_decision"],
        "report_path": str(paths.report_path),
        "archived_report_path": str(archived_report_path),
        "archived_report_written": archived_report_written,
        "report_event_appended": report_event_appended,
        "candidate_created": candidate_created,
        "candidate_event_appended": candidate_event_appended,
        "idempotency_key": idempotency_key,
        "improvement_candidate_path": str(paths.improvement_candidate_path),
        "status_path": str(paths.status_path),
        "status": status,
        "changed_file_governance": changed_file_governance,
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report_path = Path(args.report).resolve()
    report_payload = load_json(report_path)
    payload = ingest_worker_report(
        args.runtime_root,
        report_payload,
        source_report_path=report_path,
        idempotency_key=args.idempotency_key,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
