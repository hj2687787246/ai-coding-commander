from __future__ import annotations

from commander.graph.adapters.commander_runtime import (
    promote_commander_phase_goal,
    restore_active_phase_plan,
)
from commander.graph.state import CommanderGraphState


def promote_phase_goal_node(state: CommanderGraphState) -> CommanderGraphState:
    promotion = promote_commander_phase_goal(state.get("runtime_root"))
    phase_summary = (
        promotion.get("phase_summary")
        if isinstance(promotion.get("phase_summary"), dict)
        else restore_active_phase_plan(state.get("runtime_root"))
    )
    worker_task_packet = (
        promotion.get("worker_task_packet")
        if isinstance(promotion.get("worker_task_packet"), dict)
        else None
    )
    worker_provider_id = promotion.get("worker_provider_id")
    promoted_task_id = (
        worker_task_packet.get("task_id")
        if isinstance(worker_task_packet, dict)
        else state.get("task_id")
    )
    return {
        "phase_goal_promotion": promotion,
        "phase_plan": phase_summary,
        "worker_task_packet": worker_task_packet,
        "worker_provider_id": (
            str(worker_provider_id).strip()
            if isinstance(worker_provider_id, str)
            else state.get("worker_provider_id")
        ),
        "task_id": promoted_task_id,
    }


def route_after_phase_promotion(state: CommanderGraphState) -> str:
    if isinstance(state.get("worker_task_packet"), dict):
        return "assign_worker"
    return "continue_internal"
