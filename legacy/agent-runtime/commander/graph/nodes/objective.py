from __future__ import annotations

from commander.graph.adapters.commander_runtime import (
    promote_commander_objective_phase,
    restore_active_objective_plan,
    restore_active_phase_plan,
)
from commander.graph.state import CommanderGraphState


def promote_objective_phase_node(state: CommanderGraphState) -> CommanderGraphState:
    promotion = promote_commander_objective_phase(state.get("runtime_root"))
    objective_summary = (
        promotion.get("objective_summary")
        if isinstance(promotion.get("objective_summary"), dict)
        else restore_active_objective_plan(state.get("runtime_root"))
    )
    phase_summary = (
        promotion.get("phase_summary")
        if isinstance(promotion.get("phase_summary"), dict)
        else restore_active_phase_plan(state.get("runtime_root"))
    )
    promoted_task_id = (
        phase_summary.get("current_task_id")
        if isinstance(phase_summary, dict)
        else state.get("task_id")
    )
    return {
        "objective_phase_promotion": promotion,
        "objective_plan": objective_summary,
        "phase_plan": phase_summary,
        "task_id": promoted_task_id,
    }


def route_after_objective_promotion(state: CommanderGraphState) -> str:
    if isinstance(state.get("phase_plan"), dict):
        return "promote_phase_goal"
    return "continue_internal"
