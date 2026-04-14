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
    load_json,
    normalize_runtime_root,
    refresh_commander_task_catalog,
    refresh_status,
    reopen_task,
    resolve_task_paths,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reopen a stale or canceled commander runtime task.")
    parser.add_argument("--runtime-root", default=None, help="Override runtime root. Defaults to .runtime/commander")
    parser.add_argument("--task-id", required=True, help="Stable task identifier")
    parser.add_argument("--reason", default="commander_reopened_task", help="Why the task is being reopened")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    runtime_root = normalize_runtime_root(args.runtime_root)
    paths = resolve_task_paths(runtime_root, args.task_id)

    snapshot = refresh_status(paths)
    lifecycle_status = snapshot.get("lifecycle_status")
    changed = False

    if lifecycle_status == "active":
        lifecycle = load_json(paths.lifecycle_path)
    else:
        if lifecycle_status not in {"stale", "canceled"}:
            raise SchemaValidationError(
                f"Task {args.task_id} can only be reopened from stale/canceled, got {lifecycle_status!r}"
            )
        lifecycle = reopen_task(paths, reason=args.reason)
        append_event(
            paths,
            "task_reopened",
            {
                "reason": args.reason,
                "previous_lifecycle_status": lifecycle_status,
                "previous_phase": snapshot.get("current_phase"),
            },
        )
        changed = True

    status = refresh_status(paths)
    refresh_commander_task_catalog(paths, event_type="task_reopened" if changed else None)
    print(
        json.dumps(
            {
                "task_id": args.task_id,
                "changed": changed,
                "lifecycle_path": str(paths.lifecycle_path),
                "status_path": str(paths.status_path),
                "checkpoint_path": str(paths.checkpoint_path),
                "lifecycle": lifecycle,
                "status": status,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
