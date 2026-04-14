from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from commander.transport.scripts.commander_harness import (
    SchemaValidationError,
    append_event,
    load_events,
    load_json,
    mark_task_archived,
    normalize_runtime_root,
    refresh_commander_task_catalog,
    refresh_status,
    resolve_task_paths,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Archive a closed commander task in runtime history.")
    parser.add_argument("--runtime-root", default=None, help="Override runtime root. Defaults to .runtime/commander")
    parser.add_argument("--task-id", required=True, help="Stable task identifier")
    parser.add_argument("--reason", default="runtime_archive_complete", help="Why the task is being archived")
    parser.add_argument(
        "--idempotency-key", default=None, help="Optional graph node idempotency key"
    )
    return parser.parse_args(argv)


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


def archive_task(
    runtime_root: str | Path | None,
    task_id: str,
    *,
    reason: str = "runtime_archive_complete",
    idempotency_key: str | None = None,
) -> dict[str, object]:
    resolved_runtime_root = normalize_runtime_root(runtime_root)
    paths = resolve_task_paths(resolved_runtime_root, task_id)

    snapshot = refresh_status(paths)
    lifecycle_status = snapshot.get("lifecycle_status")
    changed = False

    if lifecycle_status == "archived":
        lifecycle = load_json(paths.lifecycle_path)
    else:
        if lifecycle_status != "closed":
            raise SchemaValidationError(
                f"Task {task_id} must be closed before archive; lifecycle_status={lifecycle_status!r}"
            )
        lifecycle = mark_task_archived(paths, reason=reason)
        if not _has_idempotent_event(paths, "task_archived", idempotency_key):
            append_event(
                paths,
                "task_archived",
                {
                    "reason": reason,
                    "closed_at": lifecycle.get("closed_at"),
                    "idempotency_key": idempotency_key,
                },
            )
        changed = True

    status = refresh_status(paths)
    refresh_commander_task_catalog(paths, event_type="task_archived" if changed else None)
    return {
        "task_id": task_id,
        "changed": changed,
        "idempotency_key": idempotency_key,
        "lifecycle_path": str(paths.lifecycle_path),
        "status_path": str(paths.status_path),
        "checkpoint_path": str(paths.checkpoint_path),
        "lifecycle": lifecycle,
        "status": status,
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = archive_task(
        args.runtime_root,
        args.task_id,
        reason=args.reason,
        idempotency_key=args.idempotency_key,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
