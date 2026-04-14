from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from commander.graph.runners.resume import resume_once
from commander.graph.runners.run_once import run_once
from commander.transport.scripts.commander_host_runtime import (
    build_task_host_wait_summary,
    find_task_report_candidate,
    mark_task_host_session_report_ready,
    request_task_host_session_resume,
)
from commander.transport.scripts.commander_harness import (
    normalize_runtime_root,
    record_task_compaction_event,
    resolve_task_paths,
)


def _state_signature(state: dict[str, Any]) -> str:
    payload = {
        "task_id": state.get("task_id"),
        "route": state.get("route"),
        "stop_allowed": state.get("stop_allowed"),
        "continuation_required": state.get("continuation_required"),
        "continuation_mode": state.get("continuation_mode"),
        "next_actions": state.get("next_actions", []),
        "user_delivery": state.get("user_delivery"),
        "worker_dispatch_status": (
            state.get("worker_dispatch", {}).get("status")
            if isinstance(state.get("worker_dispatch"), dict)
            else None
        ),
        "worker_ingest_phase": (
            state.get("worker_ingest", {}).get("status", {}).get("current_phase")
            if isinstance(state.get("worker_ingest"), dict)
            and isinstance(state.get("worker_ingest", {}).get("status"), dict)
            else None
        ),
        "task_closure_phase": (
            state.get("task_closure", {}).get("status", {}).get("current_phase")
            if isinstance(state.get("task_closure"), dict)
            and isinstance(state.get("task_closure", {}).get("status"), dict)
            else None
        ),
        "task_archive_phase": (
            state.get("task_archive", {}).get("status", {}).get("current_phase")
            if isinstance(state.get("task_archive"), dict)
            and isinstance(state.get("task_archive", {}).get("status"), dict)
            else None
        ),
        "objective_plan": state.get("objective_plan"),
        "objective_phase_promotion": state.get("objective_phase_promotion"),
        "phase_plan": state.get("phase_plan"),
        "phase_goal_promotion": state.get("phase_goal_promotion"),
        "intent_binding": state.get("intent_binding"),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _round_summary(index: int, state: dict[str, Any]) -> dict[str, Any]:
    return {
        "round": index,
        "task_id": state.get("task_id"),
        "route": state.get("route"),
        "stop_allowed": state.get("stop_allowed"),
        "continuation_required": state.get("continuation_required"),
        "continuation_mode": state.get("continuation_mode"),
        "next_actions": state.get("next_actions", []),
        "user_delivery": state.get("user_delivery"),
        "objective_plan": state.get("objective_plan"),
        "objective_phase_promotion": state.get("objective_phase_promotion"),
        "phase_plan": state.get("phase_plan"),
        "phase_goal_promotion": state.get("phase_goal_promotion"),
        "intent_binding": state.get("intent_binding"),
    }


def _wait_for_worker_report(
    *,
    runtime_root: str | Path | None,
    task_id: str | None,
    wait_timeout_seconds: float,
    poll_interval_seconds: float,
) -> tuple[dict[str, object] | None, dict[str, Any] | None]:
    if task_id is None or wait_timeout_seconds <= 0:
        return None, build_task_host_wait_summary(runtime_root, task_id)

    resolved_runtime_root = normalize_runtime_root(runtime_root)
    deadline = time.monotonic() + wait_timeout_seconds
    while time.monotonic() < deadline:
        candidate = find_task_report_candidate(resolved_runtime_root, task_id)
        if isinstance(candidate, dict):
            payload = candidate.get("report_payload")
            report_path = candidate.get("report_path")
            if isinstance(payload, dict) and isinstance(report_path, str) and report_path:
                mark_task_host_session_report_ready(
                    resolved_runtime_root,
                    task_id,
                    report_path,
                )
                return payload, build_task_host_wait_summary(
                    resolved_runtime_root,
                    task_id,
                    wait_timeout_seconds=wait_timeout_seconds,
                )
        time.sleep(max(poll_interval_seconds, 0.1))
    request_task_host_session_resume(
        resolved_runtime_root,
        task_id,
        note=f"wait_timeout_after_{wait_timeout_seconds:.2f}s",
    )
    return None, build_task_host_wait_summary(
        resolved_runtime_root,
        task_id,
        timed_out=True,
        wait_timeout_seconds=wait_timeout_seconds,
    )


def _load_existing_report(
    *,
    runtime_root: str | Path | None,
    task_id: str | None,
) -> dict[str, object] | None:
    if task_id is None:
        return None

    resolved_runtime_root = normalize_runtime_root(runtime_root)
    candidate = find_task_report_candidate(resolved_runtime_root, task_id)
    if not isinstance(candidate, dict):
        return None
    payload = candidate.get("report_payload")
    report_path = candidate.get("report_path")
    if isinstance(payload, dict) and isinstance(report_path, str) and report_path:
        mark_task_host_session_report_ready(
            resolved_runtime_root,
            task_id,
            report_path,
        )
        return payload
    return None


def _resolve_tracked_task_id(
    current_task_id: str | None,
    state: dict[str, Any],
) -> str | None:
    candidates: list[object] = [
        state.get("task_id"),
        (
            state.get("worker_dispatch", {}).get("task_id")
            if isinstance(state.get("worker_dispatch"), dict)
            else None
        ),
        (
            state.get("worker_ingest", {}).get("task_id")
            if isinstance(state.get("worker_ingest"), dict)
            else None
        ),
        (
            state.get("task_closure", {}).get("task_id")
            if isinstance(state.get("task_closure"), dict)
            else None
        ),
        (
            state.get("task_archive", {}).get("task_id")
            if isinstance(state.get("task_archive"), dict)
            else None
        ),
        (
            state.get("phase_goal_promotion", {}).get("phase_summary", {}).get(
                "current_task_id"
            )
            if isinstance(state.get("phase_goal_promotion"), dict)
            and isinstance(state.get("phase_goal_promotion", {}).get("phase_summary"), dict)
            else None
        ),
        (
            state.get("objective_phase_promotion", {}).get("phase_summary", {}).get(
                "current_task_id"
            )
            if isinstance(state.get("objective_phase_promotion"), dict)
            and isinstance(
                state.get("objective_phase_promotion", {}).get("phase_summary"),
                dict,
            )
            else None
        ),
        current_task_id,
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None


def _finalize_handoff_result(
    *,
    thread_id: str,
    runtime_root: str | None,
    task_id: str | None,
    driver_status: str,
    stop_reason: str,
    round_count: int,
    rounds: list[dict[str, Any]],
    final_state: dict[str, Any] | None,
    wait_monitor: dict[str, Any] | None,
    record_compaction: bool,
) -> dict[str, Any]:
    payload = {
        "thread_id": thread_id,
        "driver_status": driver_status,
        "stop_reason": stop_reason,
        "round_count": round_count,
        "rounds": rounds,
        "task_id": task_id,
        "final_state": final_state,
        "wait_monitor": wait_monitor,
    }
    if not record_compaction or task_id is None:
        return payload

    paths = resolve_task_paths(normalize_runtime_root(runtime_root), task_id)
    if not paths.task_dir.exists():
        return payload

    payload["compaction_event"] = record_task_compaction_event(
        paths,
        source="run_until_handoff",
        trigger="driver_handoff",
        thread_id=thread_id,
        driver_status=driver_status,
        stop_reason=stop_reason,
        round_count=round_count,
        payload={
            "rounds": rounds,
            "final_state": final_state,
            "wait_monitor": wait_monitor,
        },
    )
    return payload


def run_until_handoff(
    *,
    thread_id: str | None = None,
    runtime_root: str | None = None,
    task_card_path: str | None = None,
    task_id: str | None = None,
    checkpoint_db: str | None = None,
    worker_task_packet: dict[str, object] | None = None,
    worker_provider_id: str | None = None,
    worker_report_payload: dict[str, object] | None = None,
    last_open_offer: dict[str, object] | None = None,
    pending_user_reply_target: str | None = None,
    offer_confirmed: bool | None = None,
    latest_user_reply_text: str | None = None,
    max_rounds: int = 8,
    wait_timeout_seconds: float = 0.0,
    poll_interval_seconds: float = 1.0,
    record_compaction: bool = True,
) -> dict[str, Any]:
    resolved_thread_id = thread_id or f"commander-{uuid4().hex}"
    rounds: list[dict[str, Any]] = []
    previous_signature: str | None = None
    tracked_task_id = task_id
    if tracked_task_id is None:
        if isinstance(worker_task_packet, dict):
            packet_task_id = worker_task_packet.get("task_id")
            if isinstance(packet_task_id, str) and packet_task_id.strip():
                tracked_task_id = packet_task_id.strip()
        if tracked_task_id is None and isinstance(worker_report_payload, dict):
            report_task_id = worker_report_payload.get("task_id")
            if isinstance(report_task_id, str) and report_task_id.strip():
                tracked_task_id = report_task_id.strip()
    pending_packet = worker_task_packet
    pending_report = worker_report_payload
    pending_last_open_offer = last_open_offer
    pending_user_reply_target_value = pending_user_reply_target
    pending_offer_confirmed = offer_confirmed
    pending_latest_user_reply_text = latest_user_reply_text
    final_state: dict[str, Any] | None = None
    wait_monitor: dict[str, Any] | None = None

    for index in range(1, max(max_rounds, 1) + 1):
        if index == 1:
            state = run_once(
                thread_id=resolved_thread_id,
                runtime_root=runtime_root,
                task_card_path=task_card_path,
                task_id=tracked_task_id,
                checkpoint_db=checkpoint_db,
                worker_task_packet=pending_packet,
                worker_provider_id=worker_provider_id,
                worker_report_payload=pending_report,
                last_open_offer=pending_last_open_offer,
                pending_user_reply_target=pending_user_reply_target_value,
                offer_confirmed=pending_offer_confirmed,
                latest_user_reply_text=pending_latest_user_reply_text,
            )
        else:
            state = resume_once(
                thread_id=resolved_thread_id,
                runtime_root=runtime_root,
                task_card_path=task_card_path,
                task_id=tracked_task_id,
                checkpoint_db=checkpoint_db,
                worker_task_packet=pending_packet,
                worker_provider_id=worker_provider_id,
                worker_report_payload=pending_report,
                last_open_offer=pending_last_open_offer,
                pending_user_reply_target=pending_user_reply_target_value,
                offer_confirmed=pending_offer_confirmed,
                latest_user_reply_text=pending_latest_user_reply_text,
            )

        final_state = state
        tracked_task_id = _resolve_tracked_task_id(tracked_task_id, state)
        rounds.append(_round_summary(index, state))
        pending_packet = None
        pending_report = None
        pending_last_open_offer = None
        pending_user_reply_target_value = None
        pending_offer_confirmed = None
        pending_latest_user_reply_text = None
        wait_monitor = None

        if bool(state.get("stop_allowed")):
            mode = str(state.get("continuation_mode") or "").strip() or "terminal"
            return _finalize_handoff_result(
                thread_id=resolved_thread_id,
                runtime_root=runtime_root,
                task_id=tracked_task_id,
                driver_status="stopped",
                stop_reason=mode,
                round_count=len(rounds),
                rounds=rounds,
                final_state=final_state,
                wait_monitor=wait_monitor,
                record_compaction=record_compaction,
            )

        if not bool(state.get("continuation_required")):
            return _finalize_handoff_result(
                thread_id=resolved_thread_id,
                runtime_root=runtime_root,
                task_id=tracked_task_id,
                driver_status="completed_without_handoff",
                stop_reason="continuation_not_required",
                round_count=len(rounds),
                rounds=rounds,
                final_state=final_state,
                wait_monitor=wait_monitor,
                record_compaction=record_compaction,
            )

        continuation_mode = str(state.get("continuation_mode") or "").strip()
        if continuation_mode == "wait_external_result":
            pending_report, wait_monitor = _wait_for_worker_report(
                runtime_root=runtime_root,
                task_id=tracked_task_id,
                wait_timeout_seconds=wait_timeout_seconds,
                poll_interval_seconds=poll_interval_seconds,
            )
            if pending_report is not None:
                continue
            if final_state is not None:
                final_state["host_wait"] = wait_monitor
            return _finalize_handoff_result(
                thread_id=resolved_thread_id,
                runtime_root=runtime_root,
                task_id=tracked_task_id,
                driver_status="waiting_external_result",
                stop_reason="wait_timeout_or_missing_report",
                round_count=len(rounds),
                rounds=rounds,
                final_state=final_state,
                wait_monitor=wait_monitor,
                record_compaction=record_compaction,
            )

        if (
            pending_report is None
            and not isinstance(state.get("worker_ingest"), dict)
            and continuation_mode in {"commander_internal", "wait_external_result"}
        ):
            pending_report = _load_existing_report(
                runtime_root=runtime_root,
                task_id=tracked_task_id,
            )
            if pending_report is not None:
                continue

        signature = _state_signature(state)
        if previous_signature == signature:
            return _finalize_handoff_result(
                thread_id=resolved_thread_id,
                runtime_root=runtime_root,
                task_id=tracked_task_id,
                driver_status="paused_no_progress",
                stop_reason=continuation_mode or "commander_internal",
                round_count=len(rounds),
                rounds=rounds,
                final_state=final_state,
                wait_monitor=wait_monitor,
                record_compaction=record_compaction,
            )
        previous_signature = signature

    return _finalize_handoff_result(
        thread_id=resolved_thread_id,
        runtime_root=runtime_root,
        task_id=tracked_task_id,
        driver_status="max_rounds_exhausted",
        stop_reason="max_rounds_exhausted",
        round_count=len(rounds),
        rounds=rounds,
        final_state=final_state,
        wait_monitor=wait_monitor,
        record_compaction=record_compaction,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the commander graph continuously until user handoff, terminal state, or no-progress pause."
    )
    parser.add_argument("--thread-id", default=None, help="Stable LangGraph thread id")
    parser.add_argument("--runtime-root", default=None, help="Override runtime root")
    parser.add_argument(
        "--task-card-path", default=None, help="Override current task card path"
    )
    parser.add_argument("--task-id", default=None, help="Optional runtime task id")
    parser.add_argument(
        "--checkpoint-db", default=None, help="Override graph checkpoint SQLite path"
    )
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=8,
        help="Maximum number of graph rounds before pausing",
    )
    parser.add_argument(
        "--wait-timeout-seconds",
        type=float,
        default=0.0,
        help="When waiting for an external worker report, poll report.json for up to this many seconds",
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=1.0,
        help="Polling interval used with --wait-timeout-seconds",
    )
    parser.add_argument(
        "--latest-user-reply-text",
        default=None,
        help="Optional latest user reply used for intent binding.",
    )
    parser.add_argument(
        "--pending-user-reply-target",
        default=None,
        help="Optional explicit pending reply target override.",
    )
    parser.add_argument(
        "--offer-confirmed",
        action="store_true",
        help="Explicitly mark the current open offer as confirmed.",
    )
    parser.add_argument(
        "--last-open-offer-json",
        default=None,
        help="Optional JSON object describing the latest explicit assistant offer.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = run_until_handoff(
        thread_id=args.thread_id,
        runtime_root=args.runtime_root,
        task_card_path=args.task_card_path,
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
        max_rounds=args.max_rounds,
        wait_timeout_seconds=args.wait_timeout_seconds,
        poll_interval_seconds=args.poll_interval_seconds,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
