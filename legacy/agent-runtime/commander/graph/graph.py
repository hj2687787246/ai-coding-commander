from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from commander.graph.nodes.audit import audit_node
from commander.graph.nodes.decide import decide_next_node, route_after_decide
from commander.graph.nodes.deliver import continue_internal_node, deliver_result_node
from commander.graph.nodes.objective import (
    promote_objective_phase_node,
    route_after_objective_promotion,
)
from commander.graph.nodes.phase import (
    promote_phase_goal_node,
    route_after_phase_promotion,
)
from commander.graph.nodes.restore import restore_node
from commander.graph.nodes.stop_gate import stop_gate_node
from commander.graph.nodes.worker import (
    archive_task_node,
    assign_worker_node,
    close_task_node,
    dispatch_worker_node,
    ingest_worker_node,
    route_after_dispatch,
    route_after_close,
    route_after_ingest,
    user_handoff_node,
)
from commander.graph.state import CommanderGraphState


def build_commander_graph(*, checkpointer: InMemorySaver | None = None):
    workflow = StateGraph(CommanderGraphState)
    workflow.add_node("restore", restore_node)
    workflow.add_node("audit", audit_node)
    workflow.add_node("stop_gate", stop_gate_node)
    workflow.add_node("decide_next", decide_next_node)
    workflow.add_node("deliver_result", deliver_result_node)
    workflow.add_node("continue_internal", continue_internal_node)
    workflow.add_node("promote_objective_phase", promote_objective_phase_node)
    workflow.add_node("promote_phase_goal", promote_phase_goal_node)
    workflow.add_node("assign_worker", assign_worker_node)
    workflow.add_node("dispatch_worker", dispatch_worker_node)
    workflow.add_node("ingest_worker", ingest_worker_node)
    workflow.add_node("close_task", close_task_node)
    workflow.add_node("archive_task", archive_task_node)
    workflow.add_node("user_handoff", user_handoff_node)

    workflow.add_edge(START, "restore")
    workflow.add_edge("restore", "audit")
    workflow.add_edge("audit", "stop_gate")
    workflow.add_edge("stop_gate", "decide_next")
    workflow.add_conditional_edges(
        "decide_next",
        route_after_decide,
        {
            "assign_worker": "assign_worker",
            "deliver_result": "deliver_result",
            "continue_internal": "continue_internal",
            "ingest_worker": "ingest_worker",
            "promote_objective_phase": "promote_objective_phase",
            "promote_phase_goal": "promote_phase_goal",
        },
    )
    workflow.add_conditional_edges(
        "promote_objective_phase",
        route_after_objective_promotion,
        {
            "promote_phase_goal": "promote_phase_goal",
            "continue_internal": "continue_internal",
        },
    )
    workflow.add_conditional_edges(
        "promote_phase_goal",
        route_after_phase_promotion,
        {
            "assign_worker": "assign_worker",
            "continue_internal": "continue_internal",
        },
    )
    workflow.add_edge("assign_worker", "dispatch_worker")
    workflow.add_conditional_edges(
        "dispatch_worker",
        route_after_dispatch,
        {
            "end": END,
            "ingest_worker": "ingest_worker",
        },
    )
    workflow.add_conditional_edges(
        "ingest_worker",
        route_after_ingest,
        {
            "archive_task": "archive_task",
            "close_task": "close_task",
            "continue_internal": "continue_internal",
            "user_handoff": "user_handoff",
        },
    )
    workflow.add_conditional_edges(
        "close_task",
        route_after_close,
        {
            "archive_task": "archive_task",
            "continue_internal": "continue_internal",
            "user_handoff": "user_handoff",
        },
    )
    workflow.add_edge("archive_task", END)
    workflow.add_edge("user_handoff", END)
    workflow.add_edge("deliver_result", END)
    workflow.add_edge("continue_internal", END)
    return workflow.compile(checkpointer=checkpointer or InMemorySaver())
