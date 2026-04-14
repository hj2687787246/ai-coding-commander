from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict


CommanderGraphRoute = Literal[
    "assign_worker",
    "continue_internal",
    "deliver_result",
    "ingest_worker",
    "promote_objective_phase",
    "promote_phase_goal",
]


class CommanderGraphState(TypedDict):
    """State shared by the first commander graph.

    This state intentionally keeps the transport payloads as dictionaries: the
    existing harness scripts already own those JSON contracts, and the graph
    should orchestrate them rather than redefine them.
    """

    thread_id: str
    runtime_root: NotRequired[str | None]
    task_card_path: NotRequired[str | None]
    task_id: NotRequired[str | None]
    objective_plan: NotRequired[dict[str, Any] | None]
    objective_phase_promotion: NotRequired[dict[str, Any] | None]
    phase_plan: NotRequired[dict[str, Any] | None]
    phase_goal_promotion: NotRequired[dict[str, Any] | None]
    last_open_offer: NotRequired[dict[str, Any] | None]
    pending_user_reply_target: NotRequired[str | None]
    offer_confirmed: NotRequired[bool]
    latest_user_reply_text: NotRequired[str | None]
    intent_binding: NotRequired[dict[str, Any] | None]
    restore_anchor: NotRequired[dict[str, Any] | None]
    audit_report: NotRequired[dict[str, Any] | None]
    stop_gate_report: NotRequired[dict[str, Any] | None]
    worker_task_packet: NotRequired[dict[str, Any] | None]
    worker_provider_id: NotRequired[str | None]
    worker_report_payload: NotRequired[dict[str, Any] | None]
    worker_assignment: NotRequired[dict[str, Any] | None]
    worker_dispatch: NotRequired[dict[str, Any] | None]
    worker_ingest: NotRequired[dict[str, Any] | None]
    worker_orchestration: NotRequired[dict[str, Any] | None]
    task_closure: NotRequired[dict[str, Any] | None]
    task_archive: NotRequired[dict[str, Any] | None]
    stop_allowed: NotRequired[bool]
    continuation_required: NotRequired[bool]
    continuation_mode: NotRequired[str]
    route: NotRequired[CommanderGraphRoute]
    next_actions: NotRequired[list[str]]
    user_delivery: NotRequired[dict[str, Any] | None]
    errors: NotRequired[list[str]]
