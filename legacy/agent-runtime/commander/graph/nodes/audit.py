from __future__ import annotations

from commander.graph.adapters.commander_runtime import audit_commander_state
from commander.graph.state import CommanderGraphState


def audit_node(state: CommanderGraphState) -> CommanderGraphState:
    report = audit_commander_state(
        state.get("runtime_root"), task_card_path=state.get("task_card_path")
    )
    return {
        "audit_report": report,
    }
