from __future__ import annotations

import argparse
import json
from typing import cast

from commander.graph.policies import build_intent_binding_state
from commander.graph.checkpoints import open_commander_checkpointer
from commander.graph.graph import build_commander_graph
from commander.graph.runners.run_once import build_config
from commander.graph.state import CommanderGraphState
from commander.transport.scripts.commander_harness import (
    normalize_runtime_root,
    refresh_status,
    resolve_task_paths,
)


def _prime_runtime_intent_binding(
    *,
    runtime_root: str | None,
    task_id: str | None,
    intent_binding_update: dict[str, object] | None,
) -> dict[str, object] | None:
    if task_id is None or not intent_binding_update:
        return intent_binding_update
    paths = resolve_task_paths(normalize_runtime_root(runtime_root), task_id)
    if not paths.task_dir.exists():
        return intent_binding_update
    snapshot = refresh_status(paths, intent_binding_update=intent_binding_update)
    return snapshot.get("intent_binding") if isinstance(snapshot, dict) else intent_binding_update


def resume_once(
    *,
    thread_id: str,
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
) -> dict[str, object]:
    intent_binding_update = {
        key: value
        for key, value in {
            "last_open_offer": last_open_offer,
            "pending_user_reply_target": pending_user_reply_target,
            "offer_confirmed": offer_confirmed,
            "latest_user_reply_text": latest_user_reply_text,
        }.items()
        if value is not None
    }
    primed_intent_binding = build_intent_binding_state(update=intent_binding_update)
    persisted_intent_binding = _prime_runtime_intent_binding(
        runtime_root=runtime_root,
        task_id=task_id,
        intent_binding_update=intent_binding_update or None,
    )
    effective_intent_binding = (
        persisted_intent_binding
        if isinstance(persisted_intent_binding, dict)
        else primed_intent_binding
    )
    with open_commander_checkpointer(
        runtime_root=runtime_root, checkpoint_db=checkpoint_db
    ) as checkpointer:
        graph = build_commander_graph(checkpointer=checkpointer)
        config = build_config(thread_id)
        previous = graph.get_state(config)
        previous_values = dict(previous.values) if previous.values else {}
        had_checkpoint = bool(previous_values)
        state: CommanderGraphState = {
            "thread_id": thread_id,
            "runtime_root": runtime_root,
            "task_card_path": task_card_path,
            "task_id": task_id,
            "worker_task_packet": worker_task_packet,
            "worker_provider_id": worker_provider_id,
            "worker_report_payload": worker_report_payload,
            "intent_binding": effective_intent_binding,
            "last_open_offer": effective_intent_binding.get("last_open_offer"),
            "pending_user_reply_target": effective_intent_binding.get(
                "pending_user_reply_target"
            ),
            "latest_user_reply_text": effective_intent_binding.get(
                "latest_user_reply_text"
            ),
        }
        if offer_confirmed is not None:
            state["offer_confirmed"] = offer_confirmed
        if had_checkpoint:
            previous_values.update(
                {key: value for key, value in state.items() if value is not None}
            )
            state = cast(CommanderGraphState, previous_values)
        result = dict(graph.invoke(state, config=config))
        result["resume"] = {
            "had_checkpoint": had_checkpoint,
            "previous_route": previous_values.get("route"),
        }
        return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Resume the commander LangGraph runtime by thread id."
    )
    parser.add_argument("--thread-id", required=True, help="Stable LangGraph thread id")
    parser.add_argument("--runtime-root", default=None, help="Override runtime root")
    parser.add_argument(
        "--task-card-path", default=None, help="Override current task card path"
    )
    parser.add_argument("--task-id", default=None, help="Optional runtime task id")
    parser.add_argument(
        "--checkpoint-db", default=None, help="Override graph checkpoint SQLite path"
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
    payload = resume_once(
        thread_id=args.thread_id,
        runtime_root=args.runtime_root,
        task_card_path=args.task_card_path,
        task_id=args.task_id,
        checkpoint_db=args.checkpoint_db,
        latest_user_reply_text=args.latest_user_reply_text,
        pending_user_reply_target=args.pending_user_reply_target,
        offer_confirmed=True if args.offer_confirmed else None,
        last_open_offer=(
            json.loads(args.last_open_offer_json)
            if args.last_open_offer_json
            else None
        ),
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
