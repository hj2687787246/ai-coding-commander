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
    describe_active_subagent_blocker,
    load_events,
    load_json,
    mark_task_closed,
    normalize_runtime_root,
    refresh_commander_task_catalog,
    refresh_status,
    resolve_task_paths,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mark a commander task as closed after report review."
    )
    parser.add_argument(
        "--runtime-root",
        default=None,
        help="Override runtime root. Defaults to .runtime/commander",
    )
    parser.add_argument("--task-id", required=True, help="Stable task identifier")
    parser.add_argument(
        "--reason",
        default="commander_review_complete",
        help="Why the task is being closed",
    )
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


def close_task(
    runtime_root: str | Path | None,
    task_id: str,
    *,
    reason: str = "commander_review_complete",
    idempotency_key: str | None = None,
) -> dict[str, object]:
    resolved_runtime_root = normalize_runtime_root(runtime_root)
    paths = resolve_task_paths(resolved_runtime_root, task_id)

    snapshot = refresh_status(paths)
    checkpoint = load_json(paths.checkpoint_path)
    current_phase = checkpoint.get("current_phase")
    lifecycle_status = snapshot.get("lifecycle_status")

    changed = False
    if lifecycle_status == "archived":
        lifecycle = load_json(paths.lifecycle_path)
    elif lifecycle_status == "closed":
        lifecycle = load_json(paths.lifecycle_path)
    else:
        if current_phase != "ready_to_close":
            raise SchemaValidationError(
                f"Task {task_id} is not ready to close; current_phase={current_phase!r}, lifecycle_status={lifecycle_status!r}"
            )
        active_subagents_summary = checkpoint.get("active_subagents_summary", {})
        blocker = describe_active_subagent_blocker(active_subagents_summary)
        if blocker is not None:
            open_count = int(active_subagents_summary.get("open_count") or 0)
            running_count = int(active_subagents_summary.get("running_count") or 0)
            blocked_count = int(active_subagents_summary.get("blocked_count") or 0)
            waiting_close_count = int(active_subagents_summary.get("completed_waiting_close_count") or 0)
            raise SchemaValidationError(
                (
                    f"Task {task_id} still has open sub-agents "
                    f"(open_count={open_count}, running={running_count}, blocked={blocked_count}, "
                    f"completed_waiting_close={waiting_close_count}) "
                    f"and cannot be closed yet: {blocker['reason']} -> {blocker['next_action']}"
                )
            )

        lifecycle = mark_task_closed(paths, reason=reason)
        if not _has_idempotent_event(paths, "task_closed", idempotency_key):
            append_event(
                paths,
                "task_closed",
                {
                    "reason": reason,
                    "previous_phase": current_phase,
                    "worker_status": snapshot.get("worker_status"),
                    "idempotency_key": idempotency_key,
                },
            )
        changed = True

    status = refresh_status(paths)
    refresh_commander_task_catalog(paths, event_type="task_closed" if changed else None)
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
    payload = close_task(
        args.runtime_root,
        args.task_id,
        reason=args.reason,
        idempotency_key=args.idempotency_key,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
