from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from commander.transport.scripts.commander_harness import (
    append_event,
    load_json,
    mark_task_stale,
    normalize_runtime_root,
    parse_utc_timestamp,
    refresh_commander_task_catalog,
    refresh_status,
    reopen_task,
    resolve_task_paths,
)
from commander.transport.scripts.commander_task_catalog import discover_task_ids


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reconcile commander runtime task lifecycle and stale tasks.")
    parser.add_argument("--runtime-root", default=None, help="Override runtime root. Defaults to .runtime/commander")
    parser.add_argument("--task-id", default=None, help="Reconcile a single task instead of all tasks")
    parser.add_argument(
        "--stale-after-hours",
        type=int,
        default=24,
        help="Mark active tasks stale after this many hours without new activity",
    )
    return parser.parse_args(argv)


def _latest_activity_at(snapshot: dict[str, Any], packet: dict[str, Any], report: dict[str, Any], lifecycle: dict[str, Any]) -> str | None:
    candidates = [
        snapshot.get("last_event_at"),
        report.get("created_at"),
        packet.get("updated_at"),
        packet.get("created_at"),
        lifecycle.get("updated_at"),
        lifecycle.get("created_at"),
    ]
    resolved: tuple[datetime, str] | None = None
    for value in candidates:
        parsed = parse_utc_timestamp(value)
        if parsed is None or not isinstance(value, str):
            continue
        if resolved is None or parsed > resolved[0]:
            resolved = (parsed, value)
    return resolved[1] if resolved is not None else None


def reconcile_task(runtime_root: Path, task_id: str, *, stale_after_hours: int) -> dict[str, Any]:
    paths = resolve_task_paths(runtime_root, task_id)
    snapshot = refresh_status(paths)
    lifecycle = load_json(paths.lifecycle_path)
    packet = load_json(paths.packet_path) if paths.packet_path.exists() else {}
    report = load_json(paths.report_path) if paths.report_path.exists() else {}

    current_phase = snapshot.get("current_phase")
    lifecycle_status = snapshot.get("lifecycle_status")
    stale_at = parse_utc_timestamp(snapshot.get("stale_at"))
    latest_activity_at = _latest_activity_at(snapshot, packet, report, lifecycle)
    latest_activity_dt = parse_utc_timestamp(latest_activity_at)
    now = datetime.now(timezone.utc)
    changed = False
    action = "noop"
    reason = None
    error = None

    if lifecycle_status == "stale" and stale_at is not None and latest_activity_dt is not None and latest_activity_dt > stale_at:
        reason = "new_activity_detected_after_stale_mark"
        lifecycle = reopen_task(paths, reason=reason)
        append_event(
            paths,
            "task_reopened",
            {
                "reason": reason,
                "latest_activity_at": latest_activity_at,
                "previous_stale_at": snapshot.get("stale_at"),
            },
        )
        changed = True
        action = "reopened"
    elif lifecycle_status == "active":
        if latest_activity_dt is None:
            action = "missing_activity"
            error = "missing_activity_timestamp"
        else:
            inactive_for = now - latest_activity_dt
            if inactive_for >= timedelta(hours=max(stale_after_hours, 1)):
                reason = f"no_runtime_activity_for_{max(stale_after_hours, 1)}h_phase_{current_phase}"
                lifecycle = mark_task_stale(paths, reason=reason)
                append_event(
                    paths,
                    "task_stale_marked",
                    {
                        "reason": reason,
                        "current_phase": current_phase,
                        "latest_activity_at": latest_activity_at,
                    },
                )
                changed = True
                action = "marked_stale"

    status = refresh_status(paths)
    if action == "marked_stale":
        refresh_commander_task_catalog(paths, event_type="task_stale_marked")
    elif action == "reopened":
        refresh_commander_task_catalog(paths, event_type="task_reopened")
    else:
        refresh_commander_task_catalog(paths)

    return {
        "task_id": task_id,
        "changed": changed,
        "action": action,
        "reason": reason,
        "error": error,
        "latest_activity_at": latest_activity_at,
        "lifecycle_path": str(paths.lifecycle_path),
        "status_path": str(paths.status_path),
        "checkpoint_path": str(paths.checkpoint_path),
        "lifecycle": lifecycle,
        "status": status,
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    runtime_root = normalize_runtime_root(args.runtime_root)
    task_ids = [args.task_id] if args.task_id else discover_task_ids(runtime_root)
    results = [reconcile_task(runtime_root, task_id, stale_after_hours=args.stale_after_hours) for task_id in task_ids]
    print(
        json.dumps(
            {
                "runtime_root": str(runtime_root),
                "task_count": len(results),
                "changed_count": sum(1 for item in results if item["changed"]),
                "tasks": results,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
