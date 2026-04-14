from __future__ import annotations

from commander.graph.state import CommanderGraphState


def _has_promotable_phase_goal(state: CommanderGraphState) -> bool:
    phase_plan = state.get("phase_plan")
    if not isinstance(phase_plan, dict):
        return False
    promotable_goal_id = phase_plan.get("promotable_goal_id")
    return isinstance(promotable_goal_id, str) and bool(promotable_goal_id.strip())


def _has_promotable_objective_phase(state: CommanderGraphState) -> bool:
    objective_plan = state.get("objective_plan")
    if not isinstance(objective_plan, dict):
        return False
    promotable_phase_id = objective_plan.get("promotable_phase_id")
    return isinstance(promotable_phase_id, str) and bool(promotable_phase_id.strip())


def decide_next_node(state: CommanderGraphState) -> CommanderGraphState:
    stop_allowed = bool(state.get("stop_allowed"))
    if isinstance(state.get("worker_report_payload"), dict):
        route = "ingest_worker"
    elif isinstance(state.get("worker_task_packet"), dict):
        route = "assign_worker"
    elif _has_promotable_phase_goal(state):
        route = "promote_phase_goal"
    elif _has_promotable_objective_phase(state):
        route = "promote_objective_phase"
    elif stop_allowed:
        route = "deliver_result"
    else:
        route = "continue_internal"
    return {
        "route": route,
    }


def route_after_decide(state: CommanderGraphState) -> str:
    return state.get("route") or "continue_internal"
