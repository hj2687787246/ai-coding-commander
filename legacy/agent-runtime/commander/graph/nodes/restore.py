from __future__ import annotations

from commander.graph.adapters.commander_runtime import (
    restore_active_objective_plan,
    restore_active_phase_plan,
    restore_commander_state,
)
from commander.graph.policies import build_intent_binding_state
from commander.graph.state import CommanderGraphState


def restore_node(state: CommanderGraphState) -> CommanderGraphState:
    anchor = restore_commander_state(
        state.get("runtime_root"), task_id=state.get("task_id")
    )
    objective_plan = restore_active_objective_plan(state.get("runtime_root"))
    phase_plan = restore_active_phase_plan(state.get("runtime_root"))
    anchor_binding = anchor.get("intent_binding") if isinstance(anchor, dict) else None
    state_binding = (
        state.get("intent_binding")
        if isinstance(state.get("intent_binding"), dict)
        else None
    )
    if isinstance(state_binding, dict) and (
        state_binding.get("last_open_offer") is None
        and state_binding.get("pending_user_reply_target") is None
        and not state_binding.get("offer_confirmed")
        and state_binding.get("latest_user_reply_text") is None
    ):
        state_binding = None
    update: dict[str, object] = {}
    for key in ("last_open_offer", "pending_user_reply_target", "latest_user_reply_text"):
        value = state.get(key)
        if value is not None:
            update[key] = value
    if state.get("offer_confirmed") is True:
        update["offer_confirmed"] = True
    intent_binding = build_intent_binding_state(
        existing=state_binding or anchor_binding, update=update or None
    )
    return {
        "restore_anchor": anchor,
        "objective_plan": objective_plan,
        "phase_plan": phase_plan,
        "intent_binding": intent_binding,
        "last_open_offer": intent_binding.get("last_open_offer"),
        "pending_user_reply_target": intent_binding.get(
            "pending_user_reply_target"
        ),
        "offer_confirmed": bool(intent_binding.get("offer_confirmed")),
        "latest_user_reply_text": intent_binding.get("latest_user_reply_text"),
    }
