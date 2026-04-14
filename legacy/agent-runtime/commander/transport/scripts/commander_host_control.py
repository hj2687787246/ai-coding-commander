from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from commander.graph.runners.run_until_handoff import run_until_handoff
from commander.graph.runners.run_until_objective_handoff import (
    run_until_objective_handoff,
)
from commander.transport.scripts.commander_harness import (
    load_json,
    normalize_runtime_root,
    refresh_status,
    resolve_task_paths,
)
from commander.transport.scripts.commander_host_daemon import (
    build_host_daemon_summary,
    load_host_daemon_logs,
    request_resume_host_daemon,
    request_stop_host_daemon,
    start_host_daemon,
)
from commander.transport.scripts.commander_host_runtime import (
    build_host_runtime_summary,
    heartbeat_host_session,
    load_host_session,
    resume_waiting_host_sessions,
    resume_host_session,
    stop_host_session,
)
from commander.transport.scripts.commander_objective_plan import (
    build_objective_plan_summary,
    load_primary_active_objective_plan_summary,
    reconcile_objective_plan,
)
from commander.transport.scripts.commander_phase_plan import (
    build_phase_plan_summary,
    load_primary_active_phase_plan_summary,
    reconcile_phase_plan,
)


def _load_packet_file(packet_file: str | None) -> dict[str, object] | None:
    if not isinstance(packet_file, str) or not packet_file.strip():
        return None
    payload = load_json(Path(packet_file))
    if not isinstance(payload, dict):
        raise ValueError(f"Packet file must contain a JSON object: {packet_file}")
    return payload


def _collect_task_snapshots(
    runtime_root: Path,
    *,
    task_id: str | None = None,
) -> list[dict[str, Any]]:
    if isinstance(task_id, str) and task_id.strip():
        paths = resolve_task_paths(runtime_root, task_id.strip())
        if not paths.task_dir.exists():
            return []
        return [refresh_status(paths)]

    tasks_root = runtime_root / "tasks"
    if not tasks_root.exists():
        return []
    return [
        refresh_status(resolve_task_paths(runtime_root, task_dir.name))
        for task_dir in sorted(path for path in tasks_root.iterdir() if path.is_dir())
    ]


def _load_objective_summary(
    runtime_root: Path,
    *,
    objective_id: str | None = None,
) -> dict[str, Any] | None:
    if isinstance(objective_id, str) and objective_id.strip():
        return build_objective_plan_summary(
            runtime_root,
            reconcile_objective_plan(runtime_root, objective_id=objective_id.strip()),
        )
    return load_primary_active_objective_plan_summary(runtime_root)


def _load_phase_summary(
    runtime_root: Path,
    *,
    phase_id: str | None = None,
) -> dict[str, Any] | None:
    if isinstance(phase_id, str) and phase_id.strip():
        return build_phase_plan_summary(
            reconcile_phase_plan(runtime_root, phase_id=phase_id.strip())
        )
    return load_primary_active_phase_plan_summary(runtime_root)


def build_host_control_snapshot(
    runtime_root: str | Path | None,
    *,
    task_id: str | None = None,
    objective_id: str | None = None,
    phase_id: str | None = None,
) -> dict[str, Any]:
    resolved_runtime_root = normalize_runtime_root(runtime_root)
    task_snapshots = _collect_task_snapshots(resolved_runtime_root, task_id=task_id)
    waits: list[dict[str, Any]] = []
    for snapshot in task_snapshots:
        if not isinstance(snapshot, dict):
            continue
        host_wait = snapshot.get("host_wait")
        if not isinstance(host_wait, dict):
            continue
        waits.append(
            {
                "task_id": snapshot.get("task_id"),
                "current_phase": snapshot.get("current_phase"),
                **host_wait,
            }
        )
    wait_provider_counts: dict[str, int] = {}
    timed_out_wait_count = 0
    resume_requested_wait_count = 0
    for wait in waits:
        provider_id = str(wait.get("provider_id") or "unknown")
        wait_provider_counts[provider_id] = (
            wait_provider_counts.get(provider_id, 0) + 1
        )
        if bool(wait.get("timed_out")):
            timed_out_wait_count += 1
        if str(wait.get("session_status") or "").strip() == "resume_requested":
            resume_requested_wait_count += 1
    return {
        "runtime_root": str(resolved_runtime_root),
        "host_daemon": build_host_daemon_summary(resolved_runtime_root),
        "host_runtime": build_host_runtime_summary(
            resolved_runtime_root,
            task_id=task_id,
        ),
        "objective": _load_objective_summary(
            resolved_runtime_root,
            objective_id=objective_id,
        ),
        "phase": _load_phase_summary(
            resolved_runtime_root,
            phase_id=phase_id,
        ),
        "tasks": task_snapshots,
        "waits": waits,
        "wait_summary": {
            "wait_count": len(waits),
            "timed_out_wait_count": timed_out_wait_count,
            "resume_requested_wait_count": resume_requested_wait_count,
            "provider_counts": wait_provider_counts,
        },
    }


def run_host_task(
    *,
    thread_id: str | None = None,
    runtime_root: str | None = None,
    task_card_path: str | None = None,
    task_id: str | None = None,
    checkpoint_db: str | None = None,
    packet_file: str | None = None,
    worker_provider_id: str | None = None,
    last_open_offer: dict[str, object] | None = None,
    pending_user_reply_target: str | None = None,
    offer_confirmed: bool | None = None,
    latest_user_reply_text: str | None = None,
    max_rounds: int = 8,
    wait_timeout_seconds: float = 0.0,
    poll_interval_seconds: float = 1.0,
) -> dict[str, Any]:
    return run_until_handoff(
        thread_id=thread_id,
        runtime_root=runtime_root,
        task_card_path=task_card_path,
        task_id=task_id,
        checkpoint_db=checkpoint_db,
        worker_task_packet=_load_packet_file(packet_file),
        worker_provider_id=worker_provider_id,
        last_open_offer=last_open_offer,
        pending_user_reply_target=pending_user_reply_target,
        offer_confirmed=offer_confirmed,
        latest_user_reply_text=latest_user_reply_text,
        max_rounds=max_rounds,
        wait_timeout_seconds=wait_timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )


def run_host_objective(
    *,
    thread_id: str | None = None,
    runtime_root: str | None = None,
    task_card_path: str | None = None,
    objective_id: str | None = None,
    task_id: str | None = None,
    checkpoint_db: str | None = None,
    last_open_offer: dict[str, object] | None = None,
    pending_user_reply_target: str | None = None,
    offer_confirmed: bool | None = None,
    latest_user_reply_text: str | None = None,
    max_objective_rounds: int = 6,
    max_graph_rounds: int = 8,
    wait_timeout_seconds: float = 0.0,
    poll_interval_seconds: float = 1.0,
) -> dict[str, Any]:
    return run_until_objective_handoff(
        thread_id=thread_id,
        runtime_root=runtime_root,
        task_card_path=task_card_path,
        objective_id=objective_id,
        task_id=task_id,
        checkpoint_db=checkpoint_db,
        last_open_offer=last_open_offer,
        pending_user_reply_target=pending_user_reply_target,
        offer_confirmed=offer_confirmed,
        latest_user_reply_text=latest_user_reply_text,
        max_objective_rounds=max_objective_rounds,
        max_graph_rounds=max_graph_rounds,
        wait_timeout_seconds=wait_timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )


def resume_host_waits(
    *,
    runtime_root: str | None = None,
    provider_id: str | None = None,
    only_resume_requested: bool = False,
    note: str | None = None,
) -> dict[str, Any]:
    return resume_waiting_host_sessions(
        runtime_root,
        provider_id=provider_id,
        only_resume_requested=only_resume_requested,
        note=note,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Visible host control entry for the commander runtime."
    )
    parser.add_argument("--runtime-root", default=None, help="Override runtime root")
    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--task-id", default=None)
    status_parser.add_argument("--objective-id", default=None)
    status_parser.add_argument("--phase-id", default=None)

    run_task_parser = subparsers.add_parser("run-task")
    run_task_parser.add_argument("--thread-id", default=None)
    run_task_parser.add_argument("--task-card-path", default=None)
    run_task_parser.add_argument("--task-id", default=None)
    run_task_parser.add_argument("--checkpoint-db", default=None)
    run_task_parser.add_argument("--packet-file", default=None)
    run_task_parser.add_argument("--worker-provider-id", default=None)
    run_task_parser.add_argument("--last-open-offer-json", default=None)
    run_task_parser.add_argument("--pending-user-reply-target", default=None)
    run_task_parser.add_argument("--offer-confirmed", action="store_true")
    run_task_parser.add_argument("--latest-user-reply-text", default=None)
    run_task_parser.add_argument("--max-rounds", type=int, default=8)
    run_task_parser.add_argument("--wait-timeout-seconds", type=float, default=0.0)
    run_task_parser.add_argument("--poll-interval-seconds", type=float, default=1.0)

    run_objective_parser = subparsers.add_parser("run-objective")
    run_objective_parser.add_argument("--thread-id", default=None)
    run_objective_parser.add_argument("--task-card-path", default=None)
    run_objective_parser.add_argument("--objective-id", default=None)
    run_objective_parser.add_argument("--task-id", default=None)
    run_objective_parser.add_argument("--checkpoint-db", default=None)
    run_objective_parser.add_argument("--last-open-offer-json", default=None)
    run_objective_parser.add_argument("--pending-user-reply-target", default=None)
    run_objective_parser.add_argument("--offer-confirmed", action="store_true")
    run_objective_parser.add_argument("--latest-user-reply-text", default=None)
    run_objective_parser.add_argument("--max-objective-rounds", type=int, default=6)
    run_objective_parser.add_argument("--max-graph-rounds", type=int, default=8)
    run_objective_parser.add_argument("--wait-timeout-seconds", type=float, default=0.0)
    run_objective_parser.add_argument("--poll-interval-seconds", type=float, default=1.0)

    start_daemon_parser = subparsers.add_parser("start-daemon")
    start_daemon_parser.add_argument("--thread-id", default=None)
    start_daemon_parser.add_argument("--task-card-path", default=None)
    start_daemon_parser.add_argument("--objective-id", default=None)
    start_daemon_parser.add_argument("--task-id", default=None)
    start_daemon_parser.add_argument("--checkpoint-db", default=None)
    start_daemon_parser.add_argument("--max-objective-rounds", type=int, default=6)
    start_daemon_parser.add_argument("--max-graph-rounds", type=int, default=8)
    start_daemon_parser.add_argument("--wait-timeout-seconds", type=float, default=0.0)
    start_daemon_parser.add_argument("--poll-interval-seconds", type=float, default=1.0)
    start_daemon_parser.add_argument("--idle-sleep-seconds", type=float, default=5.0)
    start_daemon_parser.add_argument("--wait-sleep-seconds", type=float, default=2.0)
    start_daemon_parser.add_argument("--user-sleep-seconds", type=float, default=5.0)
    start_daemon_parser.add_argument("--attention-sleep-seconds", type=float, default=5.0)

    daemon_status_parser = subparsers.add_parser("daemon-status")
    daemon_status_parser.add_argument("--log-limit", type=int, default=20)

    daemon_logs_parser = subparsers.add_parser("daemon-logs")
    daemon_logs_parser.add_argument("--limit", type=int, default=40)

    stop_daemon_parser = subparsers.add_parser("stop-daemon")
    stop_daemon_parser.add_argument("--reason", default="manual_stop")

    resume_daemon_parser = subparsers.add_parser("resume-daemon")
    resume_daemon_parser.add_argument("--note", default=None)
    resume_daemon_parser.add_argument("--last-open-offer-json", default=None)
    resume_daemon_parser.add_argument("--pending-user-reply-target", default=None)
    resume_daemon_parser.add_argument("--offer-confirmed", action="store_true")
    resume_daemon_parser.add_argument("--latest-user-reply-text", default=None)

    inspect_parser = subparsers.add_parser("inspect-session")
    inspect_parser.add_argument("--session-id", required=True)

    resume_parser = subparsers.add_parser("resume-session")
    resume_parser.add_argument("--session-id", required=True)

    stop_parser = subparsers.add_parser("stop-session")
    stop_parser.add_argument("--session-id", required=True)
    stop_parser.add_argument("--reason", default="manual_stop")

    heartbeat_parser = subparsers.add_parser("heartbeat-session")
    heartbeat_parser.add_argument("--session-id", required=True)
    heartbeat_parser.add_argument("--note", default=None)

    resume_waits_parser = subparsers.add_parser("resume-waits")
    resume_waits_parser.add_argument("--provider-id", default=None)
    resume_waits_parser.add_argument("--only-resume-requested", action="store_true")
    resume_waits_parser.add_argument("--note", default=None)

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "status":
        payload = build_host_control_snapshot(
            args.runtime_root,
            task_id=args.task_id,
            objective_id=args.objective_id,
            phase_id=args.phase_id,
        )
    elif args.command == "run-task":
        payload = run_host_task(
            thread_id=args.thread_id,
            runtime_root=args.runtime_root,
            task_card_path=args.task_card_path,
            task_id=args.task_id,
            checkpoint_db=args.checkpoint_db,
            packet_file=args.packet_file,
            worker_provider_id=args.worker_provider_id,
            last_open_offer=(
                json.loads(args.last_open_offer_json)
                if args.last_open_offer_json
                else None
            ),
            pending_user_reply_target=args.pending_user_reply_target,
            offer_confirmed=True if args.offer_confirmed else None,
            latest_user_reply_text=args.latest_user_reply_text,
            max_rounds=args.max_rounds,
            wait_timeout_seconds=args.wait_timeout_seconds,
            poll_interval_seconds=args.poll_interval_seconds,
        )
    elif args.command == "run-objective":
        payload = run_host_objective(
            thread_id=args.thread_id,
            runtime_root=args.runtime_root,
            task_card_path=args.task_card_path,
            objective_id=args.objective_id,
            task_id=args.task_id,
            checkpoint_db=args.checkpoint_db,
            last_open_offer=(
                json.loads(args.last_open_offer_json)
                if args.last_open_offer_json
                else None
            ),
            pending_user_reply_target=args.pending_user_reply_target,
            offer_confirmed=True if args.offer_confirmed else None,
            latest_user_reply_text=args.latest_user_reply_text,
            max_objective_rounds=args.max_objective_rounds,
            max_graph_rounds=args.max_graph_rounds,
            wait_timeout_seconds=args.wait_timeout_seconds,
            poll_interval_seconds=args.poll_interval_seconds,
        )
    elif args.command == "start-daemon":
        payload = start_host_daemon(
            args.runtime_root,
            thread_id=args.thread_id,
            task_card_path=args.task_card_path,
            objective_id=args.objective_id,
            task_id=args.task_id,
            checkpoint_db=args.checkpoint_db,
            max_objective_rounds=args.max_objective_rounds,
            max_graph_rounds=args.max_graph_rounds,
            wait_timeout_seconds=args.wait_timeout_seconds,
            poll_interval_seconds=args.poll_interval_seconds,
            idle_sleep_seconds=args.idle_sleep_seconds,
            wait_sleep_seconds=args.wait_sleep_seconds,
            user_sleep_seconds=args.user_sleep_seconds,
            attention_sleep_seconds=args.attention_sleep_seconds,
        )
    elif args.command == "daemon-status":
        payload = build_host_daemon_summary(args.runtime_root)
        payload["logs"] = load_host_daemon_logs(
            args.runtime_root,
            limit=args.log_limit,
        )
    elif args.command == "daemon-logs":
        payload = load_host_daemon_logs(
            args.runtime_root,
            limit=args.limit,
        )
    elif args.command == "stop-daemon":
        payload = request_stop_host_daemon(
            args.runtime_root,
            reason=args.reason,
        )
    elif args.command == "resume-daemon":
        payload = request_resume_host_daemon(
            args.runtime_root,
            note=args.note,
            last_open_offer=(
                json.loads(args.last_open_offer_json)
                if args.last_open_offer_json
                else None
            ),
            pending_user_reply_target=args.pending_user_reply_target,
            offer_confirmed=True if args.offer_confirmed else None,
            latest_user_reply_text=args.latest_user_reply_text,
        )
    elif args.command == "inspect-session":
        payload = load_host_session(args.runtime_root, args.session_id)
        if payload is None:
            raise SystemExit(f"Host session not found: {args.session_id}")
    elif args.command == "resume-session":
        payload = resume_host_session(args.runtime_root, args.session_id)
    elif args.command == "stop-session":
        payload = stop_host_session(
            args.runtime_root,
            args.session_id,
            reason=args.reason,
        )
    elif args.command == "heartbeat-session":
        payload = heartbeat_host_session(
            args.runtime_root,
            args.session_id,
            note=args.note,
        )
    elif args.command == "resume-waits":
        payload = resume_host_waits(
            runtime_root=args.runtime_root,
            provider_id=args.provider_id,
            only_resume_requested=bool(args.only_resume_requested),
            note=args.note,
        )
    else:
        raise SystemExit(f"Unsupported command: {args.command}")

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
