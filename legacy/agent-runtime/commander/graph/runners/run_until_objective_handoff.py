from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from commander.graph.runners.run_until_handoff import run_until_handoff
from commander.transport.scripts.commander_harness import (
    normalize_runtime_root,
    record_task_compaction_event,
    resolve_task_paths,
)
from commander.transport.scripts.commander_objective_plan import (
    build_objective_plan_summary,
    load_primary_active_objective_plan_summary,
    reconcile_objective_plan,
)


def _objective_signature(
    handoff_result: dict[str, Any],
    objective_summary: dict[str, Any] | None,
) -> str:
    payload = {
        "driver_status": handoff_result.get("driver_status"),
        "stop_reason": handoff_result.get("stop_reason"),
        "task_id": handoff_result.get("task_id"),
        "objective_summary": objective_summary,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _load_objective_summary(
    *,
    runtime_root: str | Path | None,
    objective_id: str | None,
) -> dict[str, Any] | None:
    resolved_runtime_root = normalize_runtime_root(runtime_root)
    if isinstance(objective_id, str) and objective_id.strip():
        return build_objective_plan_summary(
            resolved_runtime_root,
            reconcile_objective_plan(resolved_runtime_root, objective_id=objective_id),
        )
    return load_primary_active_objective_plan_summary(resolved_runtime_root)


def _objective_round_summary(
    index: int,
    handoff_result: dict[str, Any],
    objective_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "round": index,
        "handoff_driver_status": handoff_result.get("driver_status"),
        "handoff_stop_reason": handoff_result.get("stop_reason"),
        "task_id": handoff_result.get("task_id"),
        "objective_summary": objective_summary,
    }


def _finalize_objective_handoff_result(
    *,
    thread_id: str,
    runtime_root: str | None,
    objective_id: str | None,
    task_id: str | None,
    driver_status: str,
    stop_reason: str,
    objective_rounds: list[dict[str, Any]],
    final_handoff_result: dict[str, Any] | None,
    final_objective_summary: dict[str, Any] | None,
    record_compaction: bool,
) -> dict[str, Any]:
    payload = {
        "thread_id": thread_id,
        "driver_status": driver_status,
        "stop_reason": stop_reason,
        "objective_id": objective_id,
        "objective_round_count": len(objective_rounds),
        "objective_rounds": objective_rounds,
        "task_id": task_id,
        "final_handoff_result": final_handoff_result,
        "final_objective_summary": final_objective_summary,
    }
    if not record_compaction or task_id is None:
        return payload

    paths = resolve_task_paths(normalize_runtime_root(runtime_root), task_id)
    if not paths.task_dir.exists():
        return payload

    payload["compaction_event"] = record_task_compaction_event(
        paths,
        source="run_until_objective_handoff",
        trigger="objective_handoff",
        thread_id=thread_id,
        objective_id=objective_id,
        driver_status=driver_status,
        stop_reason=stop_reason,
        round_count=len(objective_rounds),
        payload={
            "objective_rounds": objective_rounds,
            "final_handoff_result": final_handoff_result,
            "final_objective_summary": final_objective_summary,
        },
    )
    return payload


def run_until_objective_handoff(
    *,
    thread_id: str | None = None,
    runtime_root: str | None = None,
    task_card_path: str | None = None,
    objective_id: str | None = None,
    task_id: str | None = None,
    checkpoint_db: str | None = None,
    worker_task_packet: dict[str, object] | None = None,
    worker_provider_id: str | None = None,
    worker_report_payload: dict[str, object] | None = None,
    last_open_offer: dict[str, object] | None = None,
    pending_user_reply_target: str | None = None,
    offer_confirmed: bool | None = None,
    latest_user_reply_text: str | None = None,
    max_objective_rounds: int = 6,
    max_graph_rounds: int = 8,
    wait_timeout_seconds: float = 0.0,
    poll_interval_seconds: float = 1.0,
    record_compaction: bool = True,
) -> dict[str, Any]:
    resolved_thread_id = thread_id or f"commander-objective-{uuid4().hex}"
    objective_rounds: list[dict[str, Any]] = []
    previous_signature: str | None = None
    tracked_task_id = task_id
    pending_packet = worker_task_packet
    pending_report = worker_report_payload
    pending_last_open_offer = last_open_offer
    pending_user_reply_target_value = pending_user_reply_target
    pending_offer_confirmed = offer_confirmed
    pending_latest_user_reply_text = latest_user_reply_text
    final_handoff_result: dict[str, Any] | None = None
    final_objective_summary: dict[str, Any] | None = None

    for index in range(1, max(max_objective_rounds, 1) + 1):
        handoff_result = run_until_handoff(
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
            max_rounds=max_graph_rounds,
            wait_timeout_seconds=wait_timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            record_compaction=False,
        )
        final_handoff_result = handoff_result
        tracked_task_id = (
            str(handoff_result.get("task_id")).strip()
            if isinstance(handoff_result.get("task_id"), str)
            and str(handoff_result.get("task_id")).strip()
            else tracked_task_id
        )
        objective_summary = _load_objective_summary(
            runtime_root=runtime_root,
            objective_id=objective_id,
        )
        if objective_id is None and isinstance(objective_summary, dict):
            resolved_objective_id = objective_summary.get("objective_id")
            if isinstance(resolved_objective_id, str) and resolved_objective_id.strip():
                objective_id = resolved_objective_id.strip()
        final_objective_summary = objective_summary
        objective_rounds.append(
            _objective_round_summary(index, handoff_result, objective_summary)
        )

        pending_packet = None
        pending_report = None
        pending_last_open_offer = None
        pending_user_reply_target_value = None
        pending_offer_confirmed = None
        pending_latest_user_reply_text = None

        driver_status = str(handoff_result.get("driver_status") or "").strip()
        stop_reason = str(handoff_result.get("stop_reason") or "").strip()
        final_state = (
            handoff_result.get("final_state")
            if isinstance(handoff_result.get("final_state"), dict)
            else {}
        )
        continuation_mode = str(final_state.get("continuation_mode") or "").strip()

        if driver_status == "waiting_external_result":
            return _finalize_objective_handoff_result(
                thread_id=resolved_thread_id,
                runtime_root=runtime_root,
                objective_id=objective_id,
                task_id=tracked_task_id,
                driver_status="waiting_external_result",
                stop_reason=stop_reason or "wait_external_result",
                objective_rounds=objective_rounds,
                final_handoff_result=final_handoff_result,
                final_objective_summary=final_objective_summary,
                record_compaction=record_compaction,
            )

        if continuation_mode == "user_handoff" or stop_reason == "user_handoff":
            return _finalize_objective_handoff_result(
                thread_id=resolved_thread_id,
                runtime_root=runtime_root,
                objective_id=objective_id,
                task_id=tracked_task_id,
                driver_status="stopped",
                stop_reason="user_handoff",
                objective_rounds=objective_rounds,
                final_handoff_result=final_handoff_result,
                final_objective_summary=final_objective_summary,
                record_compaction=record_compaction,
            )

        signature = _objective_signature(handoff_result, objective_summary)
        if previous_signature == signature:
            return _finalize_objective_handoff_result(
                thread_id=resolved_thread_id,
                runtime_root=runtime_root,
                objective_id=objective_id,
                task_id=tracked_task_id,
                driver_status="paused_no_progress",
                stop_reason=stop_reason or driver_status or "paused_no_progress",
                objective_rounds=objective_rounds,
                final_handoff_result=final_handoff_result,
                final_objective_summary=final_objective_summary,
                record_compaction=record_compaction,
            )
        previous_signature = signature

        has_remaining_phases = bool(
            isinstance(objective_summary, dict)
            and objective_summary.get("has_remaining_phases")
        )
        if driver_status in {"paused_no_progress", "max_rounds_exhausted"}:
            return _finalize_objective_handoff_result(
                thread_id=resolved_thread_id,
                runtime_root=runtime_root,
                objective_id=objective_id,
                task_id=tracked_task_id,
                driver_status=driver_status,
                stop_reason=stop_reason or driver_status,
                objective_rounds=objective_rounds,
                final_handoff_result=final_handoff_result,
                final_objective_summary=final_objective_summary,
                record_compaction=record_compaction,
            )
        if driver_status == "stopped" and stop_reason == "terminal" and has_remaining_phases:
            continue
        if driver_status == "completed_without_handoff" and has_remaining_phases:
            continue
        return _finalize_objective_handoff_result(
            thread_id=resolved_thread_id,
            runtime_root=runtime_root,
            objective_id=objective_id,
            task_id=tracked_task_id,
            driver_status=driver_status or "stopped",
            stop_reason=stop_reason or "terminal",
            objective_rounds=objective_rounds,
            final_handoff_result=final_handoff_result,
            final_objective_summary=final_objective_summary,
            record_compaction=record_compaction,
        )

    return _finalize_objective_handoff_result(
        thread_id=resolved_thread_id,
        runtime_root=runtime_root,
        objective_id=objective_id,
        task_id=tracked_task_id,
        driver_status="max_objective_rounds_exhausted",
        stop_reason="max_objective_rounds_exhausted",
        objective_rounds=objective_rounds,
        final_handoff_result=final_handoff_result,
        final_objective_summary=final_objective_summary,
        record_compaction=record_compaction,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the commander graph continuously until the active objective reaches a real stop gate."
    )
    parser.add_argument("--thread-id", default=None, help="Stable LangGraph thread id")
    parser.add_argument("--runtime-root", default=None, help="Override runtime root")
    parser.add_argument(
        "--task-card-path", default=None, help="Override current task card path"
    )
    parser.add_argument("--objective-id", default=None, help="Optional objective plan id")
    parser.add_argument("--task-id", default=None, help="Optional runtime task id")
    parser.add_argument(
        "--checkpoint-db", default=None, help="Override graph checkpoint SQLite path"
    )
    parser.add_argument(
        "--max-objective-rounds",
        type=int,
        default=6,
        help="Maximum number of objective-level loops before pausing",
    )
    parser.add_argument(
        "--max-graph-rounds",
        type=int,
        default=8,
        help="Maximum graph rounds per inner handoff run",
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
    payload = run_until_objective_handoff(
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
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
