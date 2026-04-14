from __future__ import annotations

from typing import Any

from commander.transport.scripts.commander_archive import archive_task
from commander.transport.scripts.commander_dispatch import dispatch_task
from commander.transport.scripts.commander_ingest import ingest_worker_report
from commander.transport.scripts.commander_close import close_task
from commander.transport.scripts.commander_harness import (
    normalize_runtime_root,
    resolve_task_paths,
)
from commander.transport.scripts.commander_host_runtime import (
    close_task_host_sessions,
)

from commander.graph.adapters.worker_pool import assign_worker_owner
from commander.graph.adapters.worker_providers import (
    WorkerDispatchGovernanceError,
    get_worker_provider,
    validate_worker_dispatch_governance,
)
from commander.graph.adapters.worker_providers.base import (
    WorkerProviderDispatchContext,
)
from commander.graph.policies.ownership import WorkerOwnershipError
from commander.graph.policies.tool_path_governance import (
    build_changed_file_governance_policy,
)
from commander.graph.state import CommanderGraphState


USER_HANDOFF_PHASES = {"pending_user", "ready_for_user_delivery"}


def _status_from_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    status = payload.get("status")
    return status if isinstance(status, dict) else {}


def _task_id_from_payload(*payloads: Any) -> str | None:
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        task_id = payload.get("task_id")
        if isinstance(task_id, str) and task_id.strip():
            return task_id.strip()
    return None


def _build_provider_result_post_check(
    report_payload: dict[str, Any],
    governance: dict[str, Any],
) -> dict[str, Any]:
    path_policy = (
        governance.get("path_policy")
        if isinstance(governance.get("path_policy"), dict)
        else {}
    )
    return build_changed_file_governance_policy(
        changed_files=report_payload.get("changed_files"),
        forbidden_paths=path_policy.get("forbidden_paths"),
        owned_paths=path_policy.get("owned_paths"),
        write_intent=path_policy.get("write_intent"),
    )


def assign_worker_node(state: CommanderGraphState) -> CommanderGraphState:
    task_packet = state.get("worker_task_packet")
    if not isinstance(task_packet, dict):
        return {
            "worker_assignment": None,
            "worker_orchestration": {
                "status": "skipped",
                "reason": "missing_worker_task_packet",
            },
        }

    provider_id = str(state.get("worker_provider_id") or "codex").strip() or "codex"
    try:
        governance = validate_worker_dispatch_governance(
            task_packet,
            provider_id=provider_id,
        )
    except WorkerDispatchGovernanceError as error:
        return {
            "task_id": task_packet.get("task_id"),
            "worker_assignment": None,
            "worker_orchestration": {
                "status": "blocked",
                "reason": "dispatch_governance_rejected",
                "provider_id": provider_id,
                "violations": error.violations,
                "governance": error.governance,
                "error": str(error),
            },
            "continuation_required": True,
            "continuation_mode": "commander_internal",
            "next_actions": [
                "Fix the provider/tool governance mismatch before dispatching this worker."
            ],
            "errors": [str(error), *error.violations],
        }

    try:
        result = assign_worker_owner(state.get("runtime_root"), task_packet=task_packet)
    except WorkerOwnershipError as error:
        return {
            "task_id": task_packet.get("task_id"),
            "worker_assignment": None,
            "worker_orchestration": {
                "status": "blocked",
                "reason": "active_worker_lease_exists",
                "error": str(error),
            },
        }

    return {
        "task_id": task_packet.get("task_id"),
        "worker_assignment": result,
        "worker_orchestration": {
            "status": "assigned",
            "reason": "worker_owner_acquired",
            "provider_id": provider_id,
            "governance": governance.as_dict(),
        },
    }


def dispatch_worker_node(state: CommanderGraphState) -> CommanderGraphState:
    task_packet = (
        state.get("worker_task_packet")
        if isinstance(state.get("worker_task_packet"), dict)
        else {}
    )
    task_id = task_packet.get("task_id")
    assignment = (
        state.get("worker_assignment")
        if isinstance(state.get("worker_assignment"), dict)
        else {}
    )
    if not assignment:
        reason = (
            state.get("worker_orchestration", {}).get("reason")
            if isinstance(state.get("worker_orchestration"), dict)
            else "worker_not_assigned"
        )
        if reason == "dispatch_governance_rejected":
            violations = (
                state.get("worker_orchestration", {}).get("violations")
                if isinstance(state.get("worker_orchestration"), dict)
                else []
            )
            return {
                "task_id": task_id,
                "worker_dispatch": {
                    "status": "not_dispatched",
                    "reason": reason,
                    "task_id": task_id,
                    "provider_id": (
                        state.get("worker_orchestration", {}).get("provider_id")
                        if isinstance(state.get("worker_orchestration"), dict)
                        else None
                    ),
                    "governance": (
                        state.get("worker_orchestration", {}).get("governance")
                        if isinstance(state.get("worker_orchestration"), dict)
                        else None
                    ),
                    "violations": violations if isinstance(violations, list) else [],
                },
                "continuation_required": True,
                "continuation_mode": "commander_internal",
                "next_actions": [
                    "Fix the provider/tool governance mismatch before dispatching this worker."
                ],
            }
        if reason == "active_worker_lease_exists":
            return {
                "task_id": task_id,
                "worker_dispatch": {
                    "status": "not_dispatched",
                    "reason": reason,
                    "task_id": task_id,
                },
                "continuation_required": True,
                "continuation_mode": "wait_external_result",
                "next_actions": [
                    "Wait for the existing worker lease to produce worker_report.json or inspect the host session."
                ],
            }
        return {
            "task_id": task_id,
            "worker_dispatch": {
                "status": "not_dispatched",
                "reason": reason,
            }
        }

    selected = (
        assignment.get("assignment")
        if isinstance(assignment.get("assignment"), dict)
        else {}
    )
    provider_id = str(state.get("worker_provider_id") or "codex").strip() or "codex"
    try:
        governance = validate_worker_dispatch_governance(
            task_packet,
            provider_id=provider_id,
        )
    except WorkerDispatchGovernanceError as error:
        return {
            "task_id": task_id,
            "worker_dispatch": {
                "status": "not_dispatched",
                "reason": "dispatch_governance_rejected",
                "provider_id": provider_id,
                "task_id": task_id,
                "governance": error.governance,
                "violations": error.violations,
                "error": str(error),
            },
            "worker_orchestration": {
                "status": "blocked",
                "reason": "dispatch_governance_rejected",
                "provider_id": provider_id,
            },
            "continuation_required": True,
            "continuation_mode": "commander_internal",
            "next_actions": [
                "Fix the provider/tool governance mismatch before dispatching this worker."
            ],
            "errors": [str(error), *error.violations],
        }
    dispatch_idempotency_key = f"graph-dispatch:{state.get('thread_id')}:{task_id}"
    dispatch_payload = dispatch_task(
        state.get("runtime_root"),
        task_packet,
        provider_id=provider_id,
        idempotency_key=dispatch_idempotency_key,
    )
    dispatch_context = WorkerProviderDispatchContext(
        thread_id=str(state.get("thread_id")),
        task_id=task_id,
        runtime_root=str(dispatch_payload["runtime_root"]),
        packet_path=str(dispatch_payload["packet_path"]),
        context_bundle_path=str(dispatch_payload["context_bundle_path"]),
        worker_brief_path=str(dispatch_payload["worker_brief_path"]),
        worker_report_path=str(dispatch_payload["worker_report_path"]),
        resume_anchor_path=str(dispatch_payload["resume_anchor_path"]),
        checkpoint_path=str(dispatch_payload["checkpoint_path"]),
        status_path=str(dispatch_payload["status_path"]),
        dispatch_idempotency_key=dispatch_idempotency_key,
        worker_id=(
            str(selected.get("worker_id")).strip()
            if isinstance(selected.get("worker_id"), str) and str(selected.get("worker_id")).strip()
            else None
        ),
        worker_profile=(
            str(task_packet.get("worker_profile")).strip()
            if isinstance(task_packet.get("worker_profile"), str) and str(task_packet.get("worker_profile")).strip()
            else None
        ),
        preferred_worker_profile=(
            str(task_packet.get("preferred_worker_profile")).strip()
            if isinstance(task_packet.get("preferred_worker_profile"), str)
            and str(task_packet.get("preferred_worker_profile")).strip()
            else None
        ),
        tool_profile=(
            str(task_packet.get("tool_profile")).strip()
            if isinstance(task_packet.get("tool_profile"), str) and str(task_packet.get("tool_profile")).strip()
            else None
        ),
        allowed_tools=tuple(
            item.strip()
            for item in task_packet.get("allowed_tools", [])
            if isinstance(item, str) and item.strip()
        ),
        forbidden_paths=tuple(
            item.strip()
            for item in task_packet.get("forbidden_paths", [])
            if isinstance(item, str) and item.strip()
        ),
        owned_paths=tuple(
            item.strip()
            for item in task_packet.get("owned_paths", [])
            if isinstance(item, str) and item.strip()
        ),
        reuse_allowed=bool(task_packet.get("reuse_allowed")),
        dispatch_kind=(
            str(task_packet.get("dispatch_kind")).strip()
            if isinstance(task_packet.get("dispatch_kind"), str) and str(task_packet.get("dispatch_kind")).strip()
            else None
        ),
        closure_policy=(
            str(task_packet.get("closure_policy")).strip()
            if isinstance(task_packet.get("closure_policy"), str) and str(task_packet.get("closure_policy")).strip()
            else None
        ),
        governance=governance.as_dict(),
    )
    inline_report_payload = None
    provider_execution: dict[str, Any] | None = None
    dispatch_status = "waiting_worker"
    provider = get_worker_provider(provider_id)
    provider_result = provider.dispatch(
        task_packet,
        dispatch_context=dispatch_context,
    )
    governance_dict = governance.as_dict()
    if isinstance(provider_result.worker_report, dict):
        post_check = _build_provider_result_post_check(
            provider_result.worker_report,
            governance_dict,
        )
        provider_execution = {
            "provider_id": provider.provider_id,
            "status": provider_result.status,
            "evidence": provider_result.evidence,
            "dispatch_metadata": provider_result.dispatch_metadata,
            "governance": governance_dict,
            "result_post_check": post_check,
        }
        if not post_check["ok"]:
            return {
                "task_id": task_id,
                "worker_dispatch": {
                    "status": "blocked",
                    "reason": "provider_result_governance_rejected",
                    "provider_id": provider_id,
                    "task_id": task_id,
                    "worker_id": selected.get("worker_id"),
                    "worker_profile": task_packet.get("worker_profile"),
                    "dispatch_payload": dispatch_payload,
                    "provider_execution": provider_execution,
                    "governance": governance_dict,
                    "result_post_check": post_check,
                    "violations": post_check["violations"],
                },
                "worker_report_payload": None,
                "continuation_required": True,
                "continuation_mode": "commander_internal",
                "next_actions": [
                    "Inspect the provider result governance violations before ingesting the worker report."
                ],
                "errors": list(post_check["violations"]),
            }
        inline_report_payload = provider_result.worker_report
        dispatch_status = "completed_inline"
    else:
        provider_execution = {
            "provider_id": provider.provider_id,
            "status": provider_result.status,
            "evidence": provider_result.evidence,
            "dispatch_metadata": provider_result.dispatch_metadata,
            "governance": governance_dict,
        }
        dispatch_status = str(provider_result.status or "waiting_worker")
    update: dict[str, Any] = {
        "task_id": task_id,
        "worker_dispatch": {
            "status": dispatch_status,
            "provider_id": provider_id,
            "task_id": task_id,
            "worker_id": selected.get("worker_id"),
            "worker_profile": task_packet.get("worker_profile"),
            "dispatch_payload": dispatch_payload,
            "provider_execution": provider_execution,
            "governance": governance_dict,
        },
        "worker_task_packet": None,
        "worker_report_payload": inline_report_payload,
    }
    if inline_report_payload is None and dispatch_status == "waiting_worker":
        update["continuation_required"] = True
        update["continuation_mode"] = "wait_external_result"
        update["next_actions"] = [
            "Wait for the external worker or inspect the host session."
        ]
    elif inline_report_payload is None and dispatch_status == "blocked":
        update["continuation_required"] = True
        update["continuation_mode"] = "commander_internal"
        update["next_actions"] = [
            "Inspect the host session launch result and fix the external worker launch failure before retrying."
        ]
    return update


def ingest_worker_node(state: CommanderGraphState) -> CommanderGraphState:
    report_payload = state.get("worker_report_payload")
    if not isinstance(report_payload, dict):
        return {
            "worker_ingest": {
                "status": "skipped",
                "reason": "missing_worker_report_payload",
            }
        }

    task_id = report_payload.get("task_id")
    ingest_payload = ingest_worker_report(
        state.get("runtime_root"),
        report_payload,
        idempotency_key=f"graph-ingest:{state.get('thread_id')}:{task_id}",
    )
    report_path = str(
        resolve_task_paths(
            normalize_runtime_root(state.get("runtime_root")),
            task_id,
        ).report_path
    )
    host_session_updates = close_task_host_sessions(
        state.get("runtime_root"),
        task_id,
        reason="worker_report_ingested",
        attached_report_path=report_path,
    )
    return {
        "task_id": task_id,
        "worker_ingest": {
            **ingest_payload,
            "host_session_updates": host_session_updates,
        },
        "worker_report_payload": None,
    }


def close_task_node(state: CommanderGraphState) -> CommanderGraphState:
    worker_ingest = state.get("worker_ingest")
    if not isinstance(worker_ingest, dict):
        return {
            "task_closure": {
                "status": "skipped",
                "reason": "missing_worker_ingest_payload",
            }
        }

    status = (
        worker_ingest.get("status")
        if isinstance(worker_ingest.get("status"), dict)
        else {}
    )
    if status.get("current_phase") != "ready_to_close":
        return {
            "task_closure": {
                "status": "skipped",
                "reason": "task_not_ready_to_close",
            }
        }

    task_id = worker_ingest.get("task_id")
    closure_payload = close_task(
        state.get("runtime_root"),
        task_id,
        idempotency_key=f"graph-close:{state.get('thread_id')}:{task_id}",
    )
    return {
        "task_id": task_id,
        "task_closure": closure_payload,
    }


def archive_task_node(state: CommanderGraphState) -> CommanderGraphState:
    task_id = _task_id_from_payload(
        state.get("task_closure"),
        state.get("worker_ingest"),
    )
    if task_id is None:
        return {
            "task_archive": {
                "status": "skipped",
                "reason": "missing_task_id",
            }
        }

    archive_payload = archive_task(
        state.get("runtime_root"),
        task_id,
        idempotency_key=f"graph-archive:{state.get('thread_id')}:{task_id}",
    )
    return {
        "task_id": task_id,
        "task_archive": archive_payload,
    }


def user_handoff_node(state: CommanderGraphState) -> CommanderGraphState:
    source_payload = (
        state.get("task_closure")
        if isinstance(state.get("task_closure"), dict)
        else state.get("worker_ingest")
    )
    status = _status_from_payload(source_payload)
    current_phase = str(status.get("current_phase") or "").strip()
    if current_phase not in USER_HANDOFF_PHASES:
        return {
            "user_delivery": None,
            "continuation_required": True,
            "continuation_mode": "commander_internal",
        }

    if current_phase == "pending_user":
        outcome = "request_user_decision"
        reason = "explicit_user_decision_required"
    else:
        outcome = "return_final_result"
        reason = "deliverable_ready_for_user"

    next_action = status.get("next_minimal_action") or status.get("recommended_action")
    next_actions = [next_action] if isinstance(next_action, str) and next_action.strip() else []
    return {
        "task_id": _task_id_from_payload(source_payload),
        "user_delivery": {
            "task_id": _task_id_from_payload(source_payload),
            "outcome": outcome,
            "reason": reason,
            "current_phase": current_phase,
            "next_actions": next_actions,
            "status_path": status.get("status_path"),
            "report_path": status.get("report_path"),
            "summary": status.get("summary"),
            "recommended_next_step": status.get("recommended_next_step"),
        },
        "continuation_required": False,
        "continuation_mode": "user_handoff",
    }


def route_after_ingest(state: CommanderGraphState) -> str:
    status = _status_from_payload(state.get("worker_ingest"))
    current_phase = str(status.get("current_phase") or "").strip()
    lifecycle_status = str(status.get("lifecycle_status") or "").strip()

    if current_phase in USER_HANDOFF_PHASES:
        return "user_handoff"
    if current_phase == "ready_to_close":
        return "close_task"
    if current_phase == "closed" or lifecycle_status == "closed":
        return "archive_task"
    return "continue_internal"


def route_after_close(state: CommanderGraphState) -> str:
    status = _status_from_payload(state.get("task_closure"))
    current_phase = str(status.get("current_phase") or "").strip()
    lifecycle_status = str(status.get("lifecycle_status") or "").strip()

    if current_phase in USER_HANDOFF_PHASES:
        return "user_handoff"
    if current_phase == "closed" or lifecycle_status == "closed":
        return "archive_task"
    return "continue_internal"


def route_after_dispatch(state: CommanderGraphState) -> str:
    if isinstance(state.get("worker_report_payload"), dict):
        return "ingest_worker"
    return "end"
