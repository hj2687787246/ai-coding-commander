from __future__ import annotations

from commander.graph.adapters.commander_runtime import run_stop_gate
from commander.graph.state import CommanderGraphState


def stop_gate_node(state: CommanderGraphState) -> CommanderGraphState:
    report = run_stop_gate(
        state.get("runtime_root"),
        task_id=state.get("task_id"),
        task_card_path=state.get("task_card_path"),
    )
    return {
        "stop_gate_report": report,
        "stop_allowed": bool(report.get("stop_allowed")),
        "continuation_required": bool(report.get("continuation_required")),
        "continuation_mode": str(report.get("continuation_mode") or "").strip(),
        "next_actions": [
            item for item in report.get("next_actions", []) if isinstance(item, str)
        ],
    }
