from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from commander.transport.scripts.commander_harness import (
    DEFAULT_WORKER_LEASE_SECONDS,
    WORKER_SLOT_COMPLETED_WAITING_CLOSE,
    WORKER_SLOT_CLOSED,
    WORKER_SLOT_WARM_IDLE,
    acquire_worker_slot,
    heartbeat_worker_slot,
    list_worker_slots,
    normalize_runtime_root,
    reconcile_worker_slots,
    refresh_worker_registry,
    release_worker_slot,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage commander warm worker slots.")
    parser.add_argument("--runtime-root", default=None, help="Override runtime root. Defaults to .runtime/commander")
    subparsers = parser.add_subparsers(dest="command", required=True)

    acquire_parser = subparsers.add_parser("acquire", help="Acquire or reuse a warm worker slot")
    acquire_parser.add_argument("--task-id", required=True, help="Stable task identifier")
    acquire_parser.add_argument("--worker-profile", required=True, help="Requested worker profile")
    acquire_parser.add_argument(
        "--preferred-worker-profile",
        default=None,
        help="Preferred warm worker profile to reuse before falling back to worker-profile",
    )
    acquire_parser.add_argument("--tool-profile", required=True, help="Tool profile carried by the packet")
    acquire_parser.add_argument("--allowed-tool", action="append", default=[], help="Allowed tool for this task")
    acquire_parser.add_argument("--no-reuse", action="store_true", help="Disable warm worker reuse")
    acquire_parser.add_argument(
        "--lease-seconds",
        type=int,
        default=DEFAULT_WORKER_LEASE_SECONDS,
        help="Lease duration for the acquired worker slot",
    )

    release_parser = subparsers.add_parser("release", help="Release a worker slot into a post-task state")
    release_parser.add_argument("--worker-id", required=True, help="Stable worker identifier")
    release_parser.add_argument(
        "--state",
        required=True,
        choices=[WORKER_SLOT_WARM_IDLE, WORKER_SLOT_COMPLETED_WAITING_CLOSE, WORKER_SLOT_CLOSED],
        help="Worker lifecycle state after release",
    )

    heartbeat_parser = subparsers.add_parser("heartbeat", help="Renew a leased worker slot heartbeat")
    heartbeat_parser.add_argument("--worker-id", required=True, help="Stable worker identifier")
    heartbeat_parser.add_argument(
        "--lease-seconds",
        type=int,
        default=None,
        help="Optional new lease duration in seconds",
    )

    reconcile_parser = subparsers.add_parser("reconcile", help="Reclaim stale worker slots and reconcile task bindings")
    reconcile_parser.add_argument("--worker-id", default=None, help="Reconcile a single worker slot")
    reconcile_parser.add_argument("--dry-run", action="store_true", help="Report drift without changing worker slots")

    status_parser = subparsers.add_parser("status", help="Inspect warm worker slots and registry")
    status_parser.add_argument("--worker-id", default=None, help="Filter by worker identifier")
    status_parser.add_argument("--worker-profile", default=None, help="Filter by worker profile")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    runtime_root = normalize_runtime_root(args.runtime_root)

    if args.command == "acquire":
        payload = acquire_worker_slot(
            runtime_root,
            task_id=args.task_id,
            worker_profile=args.worker_profile,
            preferred_worker_profile=args.preferred_worker_profile,
            tool_profile=args.tool_profile,
            allowed_tools=args.allowed_tool,
            reuse_allowed=not args.no_reuse,
            lease_seconds=args.lease_seconds,
        )
    elif args.command == "release":
        payload = release_worker_slot(runtime_root, worker_id=args.worker_id, state=args.state)
    elif args.command == "heartbeat":
        payload = heartbeat_worker_slot(runtime_root, worker_id=args.worker_id, lease_seconds=args.lease_seconds)
    elif args.command == "reconcile":
        payload = reconcile_worker_slots(
            runtime_root,
            worker_id=args.worker_id,
            dry_run=args.dry_run,
        )
    else:
        registry = refresh_worker_registry(runtime_root)
        workers = list_worker_slots(runtime_root)
        if args.worker_id:
            workers = [worker for worker in workers if worker.get("worker_id") == args.worker_id]
        if args.worker_profile:
            workers = [worker for worker in workers if worker.get("worker_profile") == args.worker_profile]
        payload = {
            "registry": registry,
            "worker_count": len(workers),
            "workers": workers,
        }

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
