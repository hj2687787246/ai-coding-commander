from __future__ import annotations

from commander.graph.state import CommanderGraphState


def deliver_result_node(state: CommanderGraphState) -> CommanderGraphState:
    stop_gate_report = state.get("stop_gate_report") or {}
    return {
        "user_delivery": {
            "outcome": stop_gate_report.get("outcome"),
            "reason": stop_gate_report.get("reason"),
            "next_actions": stop_gate_report.get("next_actions", []),
            "continuation_required": bool(
                stop_gate_report.get("continuation_required")
            ),
            "continuation_mode": stop_gate_report.get("continuation_mode"),
        }
    }


def continue_internal_node(state: CommanderGraphState) -> CommanderGraphState:
    stop_gate_report = state.get("stop_gate_report") or {}
    return {
        "user_delivery": None,
        "continuation_required": bool(stop_gate_report.get("continuation_required")),
        "continuation_mode": str(stop_gate_report.get("continuation_mode") or "").strip(),
        "next_actions": [
            item
            for item in stop_gate_report.get("next_actions", [])
            if isinstance(item, str)
        ],
    }
