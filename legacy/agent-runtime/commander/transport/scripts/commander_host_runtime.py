from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from commander.transport.scripts.commander_harness import (
    _file_lock,
    is_dispatch_draft_report,
    load_json,
    normalize_runtime_root,
    parse_utc_timestamp,
    resolve_task_paths,
    utc_now,
    write_json,
)


HOST_SESSION_SCHEMA_VERSION = "commander-host-runtime-v1"
HOST_SESSION_PENDING_LAUNCH = "pending_launch"
HOST_SESSION_WAITING_WORKER = "waiting_worker"
HOST_SESSION_REPORT_READY = "report_ready"
HOST_SESSION_RESUME_REQUESTED = "resume_requested"
HOST_SESSION_RELEASED_REUSABLE = "released_reusable"
HOST_SESSION_STOPPED = "stopped"
HOST_SESSION_CLOSED = "closed"
HOST_SESSION_FAILED = "failed"
HOST_SESSION_ACTIVE_STATES = (
    HOST_SESSION_PENDING_LAUNCH,
    HOST_SESSION_WAITING_WORKER,
    HOST_SESSION_REPORT_READY,
    HOST_SESSION_RESUME_REQUESTED,
    HOST_SESSION_RELEASED_REUSABLE,
)
HOST_SESSION_MAILBOX_COMMAND_EVENTS = frozenset(
    {"assign_task", "inspect_session", "resume_session", "stop_session"}
)


@dataclass(frozen=True)
class HostRuntimePaths:
    runtime_root: Path
    host_runtime_dir: Path
    sessions_dir: Path
    mailboxes_dir: Path
    locks_dir: Path
    registry_path: Path
    registry_lock_path: Path


@dataclass(frozen=True)
class HostSessionPaths:
    session_id: str
    session_path: Path
    mailbox_path: Path
    lock_path: Path


def resolve_host_runtime_paths(runtime_root: Path) -> HostRuntimePaths:
    host_runtime_dir = runtime_root / "host_runtime"
    locks_dir = host_runtime_dir / "locks"
    return HostRuntimePaths(
        runtime_root=runtime_root,
        host_runtime_dir=host_runtime_dir,
        sessions_dir=host_runtime_dir / "sessions",
        mailboxes_dir=host_runtime_dir / "mailboxes",
        locks_dir=locks_dir,
        registry_path=host_runtime_dir / "registry.json",
        registry_lock_path=locks_dir / "registry.lock",
    )


def resolve_host_session_paths(runtime_root: Path, session_id: str) -> HostSessionPaths:
    runtime_paths = resolve_host_runtime_paths(runtime_root)
    return HostSessionPaths(
        session_id=session_id,
        session_path=runtime_paths.sessions_dir / f"{session_id}.json",
        mailbox_path=runtime_paths.mailboxes_dir / f"{session_id}.jsonl",
        lock_path=runtime_paths.locks_dir / f"{session_id}.lock",
    )


def _iter_host_session_paths(runtime_root: Path) -> list[Path]:
    runtime_paths = resolve_host_runtime_paths(runtime_root)
    if not runtime_paths.sessions_dir.exists():
        return []
    return sorted(
        path for path in runtime_paths.sessions_dir.iterdir() if path.is_file() and path.suffix == ".json"
    )


def _normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _normalize_path_scope(value: str) -> str:
    normalized = value.replace("\\", "/").strip().strip("/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _path_scopes_overlap(left: str, right: str) -> bool:
    normalized_left = _normalize_path_scope(left)
    normalized_right = _normalize_path_scope(right)
    if not normalized_left or not normalized_right:
        return False
    return (
        normalized_left == normalized_right
        or normalized_left.startswith(f"{normalized_right}/")
        or normalized_right.startswith(f"{normalized_left}/")
    )


def _owned_path_overlaps(
    session_owned_paths: list[str],
    requested_owned_paths: list[str],
) -> list[dict[str, str]]:
    overlaps: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for session_path in session_owned_paths:
        for requested_path in requested_owned_paths:
            if not _path_scopes_overlap(session_path, requested_path):
                continue
            key = (session_path, requested_path)
            if key in seen:
                continue
            seen.add(key)
            overlaps.append(
                {
                    "session_owned_path": session_path,
                    "requested_owned_path": requested_path,
                }
            )
    return overlaps


def _append_host_session_mailbox_entry(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _normalize_string_mapping(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            continue
        if not isinstance(item, str) or not item.strip():
            continue
        normalized[key.strip()] = item.strip()
    return normalized


def _digest_string_mapping(value: dict[str, str]) -> str:
    return hashlib.sha1(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:12]


def _build_context_paths_diff(
    previous_paths: Any,
    next_paths: Any,
) -> dict[str, Any]:
    previous = _normalize_string_mapping(previous_paths)
    current = _normalize_string_mapping(next_paths)
    added = {
        key: value
        for key, value in current.items()
        if key not in previous
    }
    changed = {
        key: {
            "previous": previous[key],
            "current": current[key],
        }
        for key in sorted(previous.keys() & current.keys())
        if previous[key] != current[key]
    }
    removed = {
        key: value
        for key, value in previous.items()
        if key not in current
    }
    unchanged = [
        key
        for key in sorted(previous.keys() & current.keys())
        if previous[key] == current[key]
    ]
    return {
        "schema_version": "commander-context-diff-v1",
        "previous_digest": _digest_string_mapping(previous),
        "current_digest": _digest_string_mapping(current),
        "added_paths": added,
        "changed_paths": changed,
        "removed_paths": removed,
        "unchanged_path_keys": unchanged,
        "has_changes": bool(added or changed or removed),
    }


def append_host_session_mailbox_command(
    runtime_root: str | Path | None,
    session_id: str,
    *,
    command_type: str,
    command_payload: dict[str, Any] | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    if command_type not in HOST_SESSION_MAILBOX_COMMAND_EVENTS:
        raise ValueError(f"Unsupported mailbox command type: {command_type}")
    resolved_runtime_root = normalize_runtime_root(runtime_root)
    session = load_host_session(resolved_runtime_root, session_id)
    if not isinstance(session, dict):
        raise ValueError(f"Host session not found: {session_id}")
    session_paths = resolve_host_session_paths(resolved_runtime_root, session_id)
    entry = {
        "timestamp": utc_now(),
        "event_type": command_type,
        "command_id": f"{command_type}-{uuid4().hex[:8]}",
        "command_status": "pending",
        "retry_count": 0,
        "session_id": session_id,
        "task_id": session.get("task_id"),
        "thread_id": session.get("thread_id"),
        "note": note,
        "command_payload": command_payload or {},
    }
    _append_host_session_mailbox_entry(session_paths.mailbox_path, entry)
    return entry


def read_host_session_mailbox_entries(
    runtime_root: str | Path | None,
    session_id: str,
    *,
    after_sequence: int = 0,
    commands_only: bool = False,
    unacked_only: bool = False,
) -> dict[str, Any]:
    resolved_runtime_root = normalize_runtime_root(runtime_root)
    session_paths = resolve_host_session_paths(resolved_runtime_root, session_id)
    session = load_host_session(resolved_runtime_root, session_id)
    if unacked_only and isinstance(session, dict):
        ack_sequence = session.get("mailbox_ack_sequence")
        if isinstance(ack_sequence, int):
            after_sequence = max(after_sequence, ack_sequence)
        retry_sequence = session.get("mailbox_retry_sequence")
        if isinstance(retry_sequence, int):
            after_sequence = max(after_sequence, retry_sequence)
    entries: list[dict[str, Any]] = []
    if session_paths.mailbox_path.exists():
        with session_paths.mailbox_path.open("r", encoding="utf-8") as handle:
            for sequence, line in enumerate(handle, start=1):
                if sequence <= after_sequence:
                    continue
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    entry = json.loads(stripped)
                except json.JSONDecodeError:
                    entry = {
                        "event_type": "mailbox_decode_error",
                        "raw": stripped,
                    }
                if not isinstance(entry, dict):
                    entry = {
                        "event_type": "mailbox_invalid_entry",
                        "raw": entry,
                    }
                event_type = str(entry.get("event_type") or "").strip()
                if commands_only and event_type not in HOST_SESSION_MAILBOX_COMMAND_EVENTS:
                    continue
                entry = {
                    "sequence": sequence,
                    "is_command": event_type in HOST_SESSION_MAILBOX_COMMAND_EVENTS,
                    **entry,
                }
                entries.append(entry)

    command_entries = [
        entry for entry in entries if bool(entry.get("is_command"))
    ]
    return {
        "runtime_root": str(resolved_runtime_root),
        "session_id": session_id,
        "mailbox_path": str(session_paths.mailbox_path),
        "after_sequence": after_sequence,
        "commands_only": bool(commands_only),
        "unacked_only": bool(unacked_only),
        "entry_count": len(entries),
        "command_count": len(command_entries),
        "last_sequence": entries[-1]["sequence"] if entries else after_sequence,
        "entries": entries,
    }


def ack_host_session_mailbox(
    runtime_root: str | Path | None,
    session_id: str,
    *,
    through_sequence: int,
    note: str | None = None,
) -> dict[str, Any]:
    if through_sequence < 0:
        raise ValueError("through_sequence must be >= 0")
    updated = _update_host_session(
        runtime_root,
        session_id,
        patch={
            "mailbox_ack_sequence": through_sequence,
            "mailbox_ack_at": utc_now(),
            "mailbox_ack_note": note,
        },
    )
    session_paths = resolve_host_session_paths(
        normalize_runtime_root(runtime_root),
        session_id,
    )
    _append_host_session_mailbox_entry(
        session_paths.mailbox_path,
        {
            "timestamp": updated["updated_at"],
            "event_type": "mailbox_ack",
            "session_id": session_id,
            "task_id": updated.get("task_id"),
            "through_sequence": through_sequence,
            "note": note,
        },
    )
    return updated


def retry_unacked_host_session_mailbox_commands(
    runtime_root: str | Path | None,
    session_id: str,
    *,
    max_retries: int = 3,
    note: str | None = None,
) -> dict[str, Any]:
    if max_retries < 1:
        raise ValueError("max_retries must be >= 1")
    resolved_runtime_root = normalize_runtime_root(runtime_root)
    mailbox = read_host_session_mailbox_entries(
        resolved_runtime_root,
        session_id,
        commands_only=True,
        unacked_only=True,
    )
    entries = mailbox["entries"]
    if not entries:
        return {
            "runtime_root": str(resolved_runtime_root),
            "session_id": session_id,
            "retried_count": 0,
            "skipped_count": 0,
            "max_retries": max_retries,
            "retried_commands": [],
            "skipped_commands": [],
        }

    retry_sequence = max(
        entry["sequence"]
        for entry in entries
        if isinstance(entry.get("sequence"), int)
    )
    updated = _update_host_session(
        resolved_runtime_root,
        session_id,
        patch={
            "mailbox_retry_sequence": retry_sequence,
            "mailbox_retry_at": utc_now(),
            "mailbox_retry_note": note,
        },
    )
    session_paths = resolve_host_session_paths(resolved_runtime_root, session_id)
    retried_commands: list[dict[str, Any]] = []
    skipped_commands: list[dict[str, Any]] = []
    for entry in entries:
        retry_count = entry.get("retry_count", 0)
        if not isinstance(retry_count, int):
            retry_count = 0
        if retry_count >= max_retries:
            skipped_commands.append(
                {
                    "sequence": entry.get("sequence"),
                    "event_type": entry.get("event_type"),
                    "command_id": entry.get("command_id"),
                    "retry_count": retry_count,
                    "reason": "max_retries_reached",
                }
            )
            continue
        retry_entry = {
            key: value
            for key, value in entry.items()
            if key not in {"sequence", "is_command", "timestamp", "command_status"}
        }
        retry_entry.update(
            {
                "timestamp": utc_now(),
                "command_status": "retry",
                "retry_count": retry_count + 1,
                "retry_of_sequence": entry.get("sequence"),
                "retry_note": note,
                "task_id": updated.get("task_id"),
                "thread_id": updated.get("thread_id"),
            }
        )
        _append_host_session_mailbox_entry(session_paths.mailbox_path, retry_entry)
        retried_commands.append(
            {
                "sequence": entry.get("sequence"),
                "event_type": entry.get("event_type"),
                "command_id": retry_entry.get("command_id"),
                "retry_count": retry_count + 1,
            }
        )

    return {
        "runtime_root": str(resolved_runtime_root),
        "session_id": session_id,
        "retried_count": len(retried_commands),
        "skipped_count": len(skipped_commands),
        "max_retries": max_retries,
        "retry_sequence": retry_sequence,
        "retried_commands": retried_commands,
        "skipped_commands": skipped_commands,
    }


def _compute_context_revision(payload: dict[str, Any]) -> str:
    source = {
        "provider_id": payload.get("provider_id"),
        "host_adapter_id": payload.get("host_adapter_id"),
        "worker_id": payload.get("worker_id"),
        "worker_profile": payload.get("worker_profile"),
        "preferred_worker_profile": payload.get("preferred_worker_profile"),
        "tool_profile": payload.get("tool_profile"),
        "allowed_tools": _normalize_string_list(payload.get("allowed_tools")),
        "forbidden_paths": _normalize_string_list(payload.get("forbidden_paths")),
        "owned_paths": _normalize_string_list(payload.get("owned_paths")),
        "provider_notes": _normalize_string_list(payload.get("provider_notes")),
        "launch_bundle_paths": payload.get("launch_bundle_paths") or {},
        "dispatch_kind": payload.get("dispatch_kind"),
        "closure_policy": payload.get("closure_policy"),
    }
    digest = hashlib.sha1(
        json.dumps(source, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return digest[:12]


def _build_reuse_eligibility(payload: dict[str, Any]) -> dict[str, Any]:
    reuse_allowed = bool(payload.get("reuse_allowed"))
    session_status = str(payload.get("session_status") or "").strip()
    attached_report_path = str(payload.get("attached_report_path") or "").strip()
    stop_reason = str(payload.get("stop_reason") or "").strip()
    reasons: list[str] = []
    if not reuse_allowed:
        decision = "disabled_by_packet"
        reasons.append("task packet disabled session reuse")
        eligible_now = False
        can_accept_new_task = False
        eligible_after_release = False
    elif session_status not in HOST_SESSION_ACTIVE_STATES:
        decision = "session_not_active"
        reasons.append("session is no longer in an active host-runtime state")
        eligible_now = False
        can_accept_new_task = False
        eligible_after_release = False
    elif attached_report_path:
        decision = "report_pending_ingest"
        reasons.append("worker report is attached and should be ingested before any reuse")
        eligible_now = False
        can_accept_new_task = False
        eligible_after_release = False
    elif stop_reason:
        decision = "terminal_stop_recorded"
        reasons.append("session already recorded a stop reason and should be reconciled first")
        eligible_now = False
        can_accept_new_task = False
        eligible_after_release = False
    elif session_status == HOST_SESSION_RELEASED_REUSABLE:
        decision = "reusable_now"
        reasons.append("session is released to the reusable host session pool")
        eligible_now = True
        can_accept_new_task = True
        eligible_after_release = True
    else:
        decision = "eligible_after_release"
        reasons.append("session reuse is allowed, but this session is still bound to its current task")
        eligible_now = False
        can_accept_new_task = False
        eligible_after_release = True

    allowed_tools = _normalize_string_list(payload.get("allowed_tools"))
    reuse_key = "|".join(
        [
            str(payload.get("provider_id") or "").strip() or "unknown-provider",
            str(payload.get("worker_profile") or "").strip() or "unknown-worker-profile",
            str(payload.get("tool_profile") or "").strip() or "unknown-tool-profile",
            ",".join(sorted(allowed_tools)) or "no-tools",
        ]
    )
    return {
        "eligible_now": eligible_now,
        "eligible_after_release": eligible_after_release,
        "can_accept_new_task": can_accept_new_task,
        "decision": decision,
        "reasons": reasons,
        "reuse_key": reuse_key,
    }


def _build_session_blocker(session: dict[str, Any]) -> tuple[str | None, str]:
    session_status = str(session.get("session_status") or "").strip()
    attached_report_path = str(session.get("attached_report_path") or "").strip()
    if attached_report_path:
        return None, "Ingest the attached worker report and then close or archive the task."
    if session_status == HOST_SESSION_RESUME_REQUESTED:
        return "resume_pending", "Resume or inspect the worker window before waiting again."
    if session_status == HOST_SESSION_RELEASED_REUSABLE:
        return None, "Session is released to the reusable pool and can accept a new task."
    if session_status == HOST_SESSION_REPORT_READY:
        return None, "Inspect the reported output and ingest it into the commander runtime."
    if session_status in {HOST_SESSION_WAITING_WORKER, HOST_SESSION_PENDING_LAUNCH}:
        return None, "Wait for the worker or send a heartbeat/resume if progress stalls."
    if session_status == HOST_SESSION_FAILED:
        return "worker_failed", "Inspect the failed worker session before retrying or splitting the task."
    if session_status == HOST_SESSION_STOPPED:
        return "worker_stopped", "Inspect why the worker session stopped before deciding the next step."
    if session_status == HOST_SESSION_CLOSED:
        return None, "No further worker action is expected; the session is already closed."
    return "state_unknown", "Inspect the host session and reconcile its runtime state."


def _build_host_session_card(session: dict[str, Any]) -> dict[str, Any]:
    reuse_eligibility = _build_reuse_eligibility(session)
    blocker, next_action = _build_session_blocker(session)
    launch_bundle = (
        session.get("launch_bundle")
        if isinstance(session.get("launch_bundle"), dict)
        else {}
    )
    launch_result = (
        launch_bundle.get("launch_result")
        if isinstance(launch_bundle.get("launch_result"), dict)
        else None
    )
    return {
        "session_id": session.get("session_id"),
        "session_path": session.get("session_path"),
        "task_id": session.get("task_id"),
        "thread_id": session.get("thread_id"),
        "provider_id": session.get("provider_id"),
        "provider_label": session.get("provider_label"),
        "host_adapter_id": session.get("host_adapter_id"),
        "session_kind": session.get("session_kind"),
        "session_status": session.get("session_status"),
        "worker_id": session.get("worker_id"),
        "worker_profile": session.get("worker_profile"),
        "preferred_worker_profile": session.get("preferred_worker_profile"),
        "tool_profile": session.get("tool_profile"),
        "allowed_tools": _normalize_string_list(session.get("allowed_tools")),
        "forbidden_paths": _normalize_string_list(session.get("forbidden_paths")),
        "owned_paths": _normalize_string_list(session.get("owned_paths")),
        "reuse_allowed": bool(session.get("reuse_allowed")),
        "reuse_eligibility": reuse_eligibility,
        "can_accept_new_task": bool(reuse_eligibility.get("can_accept_new_task")),
        "dispatch_kind": session.get("dispatch_kind"),
        "closure_policy": session.get("closure_policy"),
        "governance": session.get("governance"),
        "mailbox_path": session.get("mailbox_path"),
        "launch_mode": launch_bundle.get("launch_mode"),
        "auto_launch_supported": bool(launch_bundle.get("auto_launch_supported")),
        "launch_status": launch_bundle.get("launch_status"),
        "launch_result": launch_result,
        "context_revision": session.get("context_revision"),
        "context_delivery_mode": session.get("context_delivery_mode"),
        "context_delta_paths": session.get("context_delta_paths"),
        "context_paths_diff": session.get("context_paths_diff"),
        "last_report_path": session.get("last_report_path") or session.get("attached_report_path"),
        "blocker": blocker,
        "next_action": next_action,
        "updated_at": session.get("updated_at"),
        "last_heartbeat_at": session.get("last_heartbeat_at"),
        "resume_requested_at": session.get("resume_requested_at"),
        "host_controls": session.get("host_controls"),
    }


def _decorate_host_session_payload(
    runtime_root: Path,
    payload: dict[str, Any],
) -> dict[str, Any]:
    session_id = str(payload.get("session_id") or "").strip()
    if not session_id:
        return payload
    session_paths = resolve_host_session_paths(runtime_root, session_id)
    normalized = dict(payload)
    normalized.setdefault("session_path", str(session_paths.session_path))
    normalized.setdefault("session_kind", "external_window")
    normalized["provider_notes"] = _normalize_string_list(normalized.get("provider_notes"))
    normalized["allowed_tools"] = _normalize_string_list(normalized.get("allowed_tools"))
    normalized["forbidden_paths"] = _normalize_string_list(normalized.get("forbidden_paths"))
    normalized["owned_paths"] = _normalize_string_list(normalized.get("owned_paths"))
    normalized["reuse_allowed"] = bool(normalized.get("reuse_allowed"))
    normalized.setdefault("mailbox_path", str(session_paths.mailbox_path))
    normalized["context_revision"] = _compute_context_revision(normalized)
    normalized["session_card"] = _build_host_session_card(normalized)
    return normalized


def load_host_session(runtime_root: str | Path | None, session_id: str) -> dict[str, Any] | None:
    resolved_runtime_root = normalize_runtime_root(runtime_root)
    session_paths = resolve_host_session_paths(resolved_runtime_root, session_id)
    if not session_paths.session_path.exists():
        return None
    payload = load_json(session_paths.session_path)
    if not isinstance(payload, dict):
        return None
    return _decorate_host_session_payload(resolved_runtime_root, payload)


def list_host_sessions(
    runtime_root: str | Path | None,
    *,
    task_id: str | None = None,
    include_terminal: bool = True,
) -> list[dict[str, Any]]:
    resolved_runtime_root = normalize_runtime_root(runtime_root)
    sessions: list[dict[str, Any]] = []
    for session_path in _iter_host_session_paths(resolved_runtime_root):
        payload = load_json(session_path)
        if not isinstance(payload, dict):
            continue
        payload = _decorate_host_session_payload(resolved_runtime_root, payload)
        if isinstance(task_id, str) and task_id.strip():
            if payload.get("task_id") != task_id.strip():
                continue
        if not include_terminal and payload.get("session_status") not in HOST_SESSION_ACTIVE_STATES:
            continue
        sessions.append(payload)
    return sessions


def list_host_session_reuse_candidates(
    runtime_root: str | Path | None,
    *,
    provider_id: str | None = None,
    worker_profile: str | None = None,
    tool_profile: str | None = None,
    allowed_tools: list[str] | None = None,
    owned_paths: list[str] | None = None,
    include_terminal: bool = False,
    include_rejected: bool = False,
) -> dict[str, Any]:
    resolved_runtime_root = normalize_runtime_root(runtime_root)
    requested_allowed_tools = _normalize_string_list(allowed_tools or [])
    requested_owned_paths = _normalize_string_list(owned_paths or [])
    provider_filter = provider_id.strip() if isinstance(provider_id, str) and provider_id.strip() else None
    worker_profile_filter = (
        worker_profile.strip()
        if isinstance(worker_profile, str) and worker_profile.strip()
        else None
    )
    tool_profile_filter = (
        tool_profile.strip()
        if isinstance(tool_profile, str) and tool_profile.strip()
        else None
    )
    candidates: list[dict[str, Any]] = []
    rejected_sessions: list[dict[str, Any]] = []

    for session in list_host_sessions(
        resolved_runtime_root,
        include_terminal=include_terminal,
    ):
        card = session.get("session_card")
        if not isinstance(card, dict):
            continue

        reject_reasons: list[str] = []
        current_provider_id = str(card.get("provider_id") or "").strip()
        current_worker_profile = str(card.get("worker_profile") or "").strip()
        current_tool_profile = str(card.get("tool_profile") or "").strip()
        session_allowed_tools = _normalize_string_list(card.get("allowed_tools"))
        session_owned_paths = _normalize_string_list(card.get("owned_paths"))

        if provider_filter and current_provider_id != provider_filter:
            reject_reasons.append("provider_id_mismatch")
        if worker_profile_filter and current_worker_profile != worker_profile_filter:
            reject_reasons.append("worker_profile_mismatch")
        if tool_profile_filter and current_tool_profile != tool_profile_filter:
            reject_reasons.append("tool_profile_mismatch")

        missing_allowed_tools = [
            tool for tool in requested_allowed_tools if tool not in session_allowed_tools
        ]
        if missing_allowed_tools:
            reject_reasons.append("missing_allowed_tools")

        reuse_eligibility = card.get("reuse_eligibility")
        eligible_after_release = (
            isinstance(reuse_eligibility, dict)
            and bool(reuse_eligibility.get("eligible_after_release"))
        )
        can_accept_new_task = (
            isinstance(reuse_eligibility, dict)
            and bool(reuse_eligibility.get("can_accept_new_task"))
        )
        if not eligible_after_release:
            decision = (
                reuse_eligibility.get("decision")
                if isinstance(reuse_eligibility, dict)
                else "missing_reuse_eligibility"
            )
            reject_reasons.append(f"reuse_{decision}")

        owned_path_overlaps = _owned_path_overlaps(
            session_owned_paths,
            requested_owned_paths,
        )
        candidate_payload = {
            "session_id": card.get("session_id"),
            "task_id": card.get("task_id"),
            "provider_id": current_provider_id or None,
            "worker_profile": current_worker_profile or None,
            "tool_profile": current_tool_profile or None,
            "allowed_tools": session_allowed_tools,
            "owned_paths": session_owned_paths,
            "requested_allowed_tools": requested_allowed_tools,
            "requested_owned_paths": requested_owned_paths,
            "owned_path_overlaps": owned_path_overlaps,
            "reuse_eligibility": reuse_eligibility,
            "reuse_key": reuse_eligibility.get("reuse_key")
            if isinstance(reuse_eligibility, dict)
            else None,
            "can_accept_new_task": can_accept_new_task,
            "candidate_state": "reusable_now"
            if can_accept_new_task
            else "eligible_after_release",
            "reason": "session is already released to reusable pool"
            if can_accept_new_task
            else "candidate is still bound to its current task; reuse requires release first",
            "session_card": card,
        }
        if reject_reasons:
            if include_rejected:
                rejected_sessions.append(
                    {
                        **candidate_payload,
                        "candidate_state": "rejected",
                        "reject_reasons": reject_reasons,
                    }
                )
            continue
        candidates.append(candidate_payload)

    return {
        "runtime_root": str(resolved_runtime_root),
        "filters": {
            "provider_id": provider_filter,
            "worker_profile": worker_profile_filter,
            "tool_profile": tool_profile_filter,
            "allowed_tools": requested_allowed_tools,
            "owned_paths": requested_owned_paths,
            "include_terminal": bool(include_terminal),
            "include_rejected": bool(include_rejected),
        },
        "candidate_count": len(candidates),
        "rejected_count": len(rejected_sessions),
        "can_accept_new_task_count": sum(
            1 for candidate in candidates if bool(candidate.get("can_accept_new_task"))
        ),
        "candidates": candidates,
        "rejected_sessions": rejected_sessions,
    }


def _build_registry_payload(runtime_root: Path) -> dict[str, Any]:
    sessions = list_host_sessions(runtime_root)
    status_counts: dict[str, int] = {}
    provider_counts: dict[str, int] = {}
    worker_profile_counts: dict[str, int] = {}
    task_index: dict[str, str] = {}
    reusable_now_count = 0
    reusable_after_release_count = 0
    for session in sessions:
        session_status = str(session.get("session_status") or "unknown")
        provider_id = str(session.get("provider_id") or "unknown")
        worker_profile = str(session.get("worker_profile") or "unknown")
        status_counts[session_status] = status_counts.get(session_status, 0) + 1
        provider_counts[provider_id] = provider_counts.get(provider_id, 0) + 1
        worker_profile_counts[worker_profile] = worker_profile_counts.get(worker_profile, 0) + 1
        task_id = session.get("task_id")
        session_id = session.get("session_id")
        if isinstance(task_id, str) and task_id.strip() and isinstance(session_id, str) and session_id.strip():
            task_index[task_id.strip()] = session_id.strip()
        session_card = session.get("session_card")
        if isinstance(session_card, dict):
            reuse_eligibility = session_card.get("reuse_eligibility")
            if isinstance(reuse_eligibility, dict):
                if bool(reuse_eligibility.get("can_accept_new_task")):
                    reusable_now_count += 1
                if bool(reuse_eligibility.get("eligible_after_release")):
                    reusable_after_release_count += 1

    active_sessions = [
        {
            "session_id": session.get("session_id"),
            "task_id": session.get("task_id"),
            "provider_id": session.get("provider_id"),
            "session_status": session.get("session_status"),
            "worker_profile": session.get("worker_profile"),
            "tool_profile": session.get("tool_profile"),
            "owned_paths": session.get("owned_paths"),
            "updated_at": session.get("updated_at"),
            "last_heartbeat_at": session.get("last_heartbeat_at"),
            "can_accept_new_task": session.get("session_card", {}).get("can_accept_new_task")
            if isinstance(session.get("session_card"), dict)
            else False,
        }
        for session in sessions
        if session.get("session_status") in HOST_SESSION_ACTIVE_STATES
    ]
    return {
        "schema_version": HOST_SESSION_SCHEMA_VERSION,
        "generated_at": utc_now(),
        "session_count": len(sessions),
        "active_session_count": len(active_sessions),
        "status_counts": status_counts,
        "provider_counts": provider_counts,
        "worker_profile_counts": worker_profile_counts,
        "reusable_now_count": reusable_now_count,
        "reusable_after_release_count": reusable_after_release_count,
        "task_index": task_index,
        "active_sessions": active_sessions,
    }


def refresh_host_runtime_registry(runtime_root: str | Path | None) -> dict[str, Any]:
    resolved_runtime_root = normalize_runtime_root(runtime_root)
    runtime_paths = resolve_host_runtime_paths(resolved_runtime_root)
    with _file_lock(runtime_paths.registry_lock_path, scope="host_runtime_registry"):
        registry = _build_registry_payload(resolved_runtime_root)
        write_json(runtime_paths.registry_path, registry)
    return registry


def _build_host_session_control_commands(
    *,
    runtime_root: Path,
    session_id: str,
) -> dict[str, str]:
    runtime_root_str = str(runtime_root)
    session_id_escaped = session_id
    base = (
        ".\\.venv\\Scripts\\python.exe -m commander.transport.scripts.commander_host_runtime "
        f"--runtime-root \"{runtime_root_str}\""
    )
    return {
        "status": f"{base} status",
        "inspect": f"{base} inspect --session-id \"{session_id_escaped}\"",
        "resume": f"{base} resume --session-id \"{session_id_escaped}\"",
        "stop": f"{base} stop --session-id \"{session_id_escaped}\"",
        "heartbeat": f"{base} heartbeat --session-id \"{session_id_escaped}\"",
    }


def _find_host_session_by_dispatch_key(
    runtime_root: Path,
    dispatch_idempotency_key: str | None,
) -> dict[str, Any] | None:
    if not isinstance(dispatch_idempotency_key, str) or not dispatch_idempotency_key.strip():
        return None
    for session in list_host_sessions(runtime_root):
        if session.get("dispatch_idempotency_key") == dispatch_idempotency_key.strip():
            return session
    return None


def create_host_session(
    runtime_root: str | Path | None,
    *,
    thread_id: str,
    task_id: str,
    provider_id: str,
    provider_label: str,
    host_adapter_id: str,
    launch_prompt: str,
    provider_notes: list[str] | None = None,
    launch_bundle_paths: dict[str, str] | None = None,
    launch_bundle: dict[str, Any] | None = None,
    dispatch_idempotency_key: str | None = None,
    worker_id: str | None = None,
    worker_profile: str | None = None,
    preferred_worker_profile: str | None = None,
    tool_profile: str | None = None,
    allowed_tools: list[str] | None = None,
    forbidden_paths: list[str] | None = None,
    owned_paths: list[str] | None = None,
    reuse_allowed: bool = False,
    dispatch_kind: str | None = None,
    closure_policy: str | None = None,
    governance: dict[str, Any] | None = None,
    session_status: str = HOST_SESSION_WAITING_WORKER,
) -> dict[str, Any]:
    resolved_runtime_root = normalize_runtime_root(runtime_root)
    existing = _find_host_session_by_dispatch_key(
        resolved_runtime_root,
        dispatch_idempotency_key,
    )
    if isinstance(existing, dict):
        return existing

    created_at = utc_now()
    session_id = f"host-{task_id}-{uuid4().hex[:8]}"
    session_paths = resolve_host_session_paths(resolved_runtime_root, session_id)
    session_paths.session_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": HOST_SESSION_SCHEMA_VERSION,
        "session_id": session_id,
        "session_path": str(session_paths.session_path),
        "mailbox_path": str(session_paths.mailbox_path),
        "thread_id": thread_id,
        "task_id": task_id,
        "provider_id": provider_id,
        "provider_label": provider_label,
        "host_adapter_id": host_adapter_id,
        "session_kind": "external_window",
        "session_status": session_status,
        "created_at": created_at,
        "updated_at": created_at,
        "last_heartbeat_at": None,
        "resume_requested_at": None,
        "resume_request_count": 0,
        "stop_reason": None,
        "dispatch_idempotency_key": dispatch_idempotency_key,
        "launch_prompt": launch_prompt,
        "provider_notes": provider_notes or [],
        "launch_bundle_paths": launch_bundle_paths or {},
        "launch_bundle": launch_bundle,
        "worker_id": worker_id,
        "worker_profile": worker_profile,
        "preferred_worker_profile": preferred_worker_profile,
        "tool_profile": tool_profile,
        "allowed_tools": allowed_tools or [],
        "forbidden_paths": forbidden_paths or [],
        "owned_paths": owned_paths or [],
        "reuse_allowed": bool(reuse_allowed),
        "dispatch_kind": dispatch_kind,
        "closure_policy": closure_policy,
        "governance": governance,
        "attached_report_path": None,
        "host_controls": _build_host_session_control_commands(
            runtime_root=resolved_runtime_root,
            session_id=session_id,
        ),
    }
    payload = _decorate_host_session_payload(resolved_runtime_root, payload)
    with _file_lock(session_paths.lock_path, scope=f"host_session:{session_id}"):
        write_json(session_paths.session_path, payload)
        _append_host_session_mailbox_entry(
            session_paths.mailbox_path,
            {
                "timestamp": created_at,
                "event_type": "session_created",
                "session_id": session_id,
                "task_id": task_id,
                "session_status": payload.get("session_status"),
                "context_revision": payload.get("context_revision"),
                "next_action": payload.get("session_card", {}).get("next_action")
                if isinstance(payload.get("session_card"), dict)
                else None,
            },
        )
    refresh_host_runtime_registry(resolved_runtime_root)
    return payload


def record_host_session_launch_result(
    runtime_root: str | Path | None,
    session_id: str,
    *,
    launch_status: str,
    session_status: str,
    launch_result: dict[str, Any] | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    existing = load_host_session(runtime_root, session_id)
    if not isinstance(existing, dict):
        raise FileNotFoundError(f"Host session not found: {session_id}")
    launch_bundle = (
        dict(existing.get("launch_bundle"))
        if isinstance(existing.get("launch_bundle"), dict)
        else {}
    )
    launch_bundle["launch_status"] = launch_status
    if isinstance(launch_result, dict):
        launch_bundle["launch_result"] = launch_result
    patch: dict[str, Any] = {
        "launch_bundle": launch_bundle,
        "session_status": session_status,
    }
    if isinstance(note, str) and note.strip():
        patch["last_note"] = note.strip()
    return _update_host_session(runtime_root, session_id, patch=patch)


def _update_host_session(
    runtime_root: str | Path | None,
    session_id: str,
    *,
    patch: dict[str, Any],
) -> dict[str, Any]:
    resolved_runtime_root = normalize_runtime_root(runtime_root)
    session_paths = resolve_host_session_paths(resolved_runtime_root, session_id)
    existing = load_host_session(resolved_runtime_root, session_id)
    if not isinstance(existing, dict):
        raise FileNotFoundError(f"Host session not found: {session_id}")

    updated = dict(existing)
    updated.update(patch)
    updated["updated_at"] = utc_now()
    updated = _decorate_host_session_payload(resolved_runtime_root, updated)
    with _file_lock(session_paths.lock_path, scope=f"host_session:{session_id}"):
        write_json(session_paths.session_path, updated)
        changed_keys = sorted(
            key for key, value in patch.items() if existing.get(key) != value
        )
        _append_host_session_mailbox_entry(
            session_paths.mailbox_path,
            {
                "timestamp": updated["updated_at"],
                "event_type": "session_updated",
                "session_id": session_id,
                "task_id": updated.get("task_id"),
                "session_status": updated.get("session_status"),
                "changed_keys": changed_keys,
                "note": updated.get("last_note"),
                "attached_report_path": updated.get("attached_report_path"),
                "context_revision": updated.get("context_revision"),
                "next_action": updated.get("session_card", {}).get("next_action")
                if isinstance(updated.get("session_card"), dict)
                else None,
            },
        )
    refresh_host_runtime_registry(resolved_runtime_root)
    return updated


def heartbeat_host_session(
    runtime_root: str | Path | None,
    session_id: str,
    *,
    note: str | None = None,
) -> dict[str, Any]:
    heartbeat_at = utc_now()
    patch = {
        "last_heartbeat_at": heartbeat_at,
    }
    if note:
        patch["last_note"] = note
    return _update_host_session(runtime_root, session_id, patch=patch)


def resume_host_session(
    runtime_root: str | Path | None,
    session_id: str,
    *,
    note: str | None = None,
) -> dict[str, Any]:
    existing = load_host_session(runtime_root, session_id)
    if not isinstance(existing, dict):
        raise FileNotFoundError(f"Host session not found: {session_id}")
    patch: dict[str, Any] = {
        "session_status": HOST_SESSION_RESUME_REQUESTED,
        "resume_requested_at": utc_now(),
        "resume_request_count": int(existing.get("resume_request_count", 0)) + 1,
    }
    if isinstance(note, str) and note.strip():
        patch["last_note"] = note.strip()
    updated = _update_host_session(
        runtime_root,
        session_id,
        patch=patch,
    )
    append_host_session_mailbox_command(
        runtime_root,
        session_id,
        command_type="resume_session",
        command_payload={
            "resume_request_count": updated.get("resume_request_count"),
        },
        note=note,
    )
    return updated


def stop_host_session(
    runtime_root: str | Path | None,
    session_id: str,
    *,
    reason: str,
    final_status: str = HOST_SESSION_STOPPED,
    attached_report_path: str | None = None,
) -> dict[str, Any]:
    patch: dict[str, Any] = {
        "session_status": final_status,
        "stop_reason": reason,
    }
    if attached_report_path:
        patch["attached_report_path"] = attached_report_path
    updated = _update_host_session(runtime_root, session_id, patch=patch)
    if final_status == HOST_SESSION_STOPPED:
        append_host_session_mailbox_command(
            runtime_root,
            session_id,
            command_type="stop_session",
            command_payload={"reason": reason},
            note=reason,
        )
    return updated


def mark_task_host_session_report_ready(
    runtime_root: str | Path | None,
    task_id: str,
    report_path: str,
) -> dict[str, Any] | None:
    sessions = list_host_sessions(runtime_root, task_id=task_id, include_terminal=False)
    if not sessions:
        return None
    latest = sessions[-1]
    session_id = latest.get("session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        return None
    return _update_host_session(
        runtime_root,
        session_id.strip(),
        patch={
            "session_status": HOST_SESSION_REPORT_READY,
            "attached_report_path": report_path,
        },
    )


def close_task_host_sessions(
    runtime_root: str | Path | None,
    task_id: str,
    *,
    reason: str,
    attached_report_path: str | None = None,
) -> list[dict[str, Any]]:
    sessions = list_host_sessions(runtime_root, task_id=task_id, include_terminal=False)
    updated_sessions: list[dict[str, Any]] = []
    for session in sessions:
        session_id = session.get("session_id")
        if not isinstance(session_id, str) or not session_id.strip():
            continue
        updated_sessions.append(
            stop_host_session(
                runtime_root,
                session_id.strip(),
                reason=reason,
                final_status=HOST_SESSION_CLOSED,
                attached_report_path=attached_report_path,
            )
        )
    return updated_sessions


def release_host_session_for_reuse(
    runtime_root: str | Path | None,
    session_id: str,
    *,
    reason: str = "released_for_reuse",
    last_report_path: str | None = None,
) -> dict[str, Any]:
    current = load_host_session(runtime_root, session_id)
    if not isinstance(current, dict):
        raise ValueError(f"Host session not found: {session_id}")
    if not bool(current.get("reuse_allowed")):
        raise ValueError(f"Host session {session_id} does not allow reuse")

    current_report_path = str(current.get("attached_report_path") or "").strip()
    report_path = (
        last_report_path.strip()
        if isinstance(last_report_path, str) and last_report_path.strip()
        else current_report_path
    )
    patch: dict[str, Any] = {
        "session_status": HOST_SESSION_RELEASED_REUSABLE,
        "attached_report_path": None,
        "stop_reason": None,
        "release_reason": reason,
        "released_at": utc_now(),
        "released_from_task_id": current.get("task_id"),
    }
    if report_path:
        patch["last_report_path"] = report_path
    return _update_host_session(runtime_root, session_id, patch=patch)


def release_task_host_sessions_for_reuse(
    runtime_root: str | Path | None,
    task_id: str,
    *,
    reason: str = "released_for_reuse",
    last_report_path: str | None = None,
) -> list[dict[str, Any]]:
    sessions = list_host_sessions(runtime_root, task_id=task_id, include_terminal=False)
    released_sessions: list[dict[str, Any]] = []
    for session in sessions:
        session_id = session.get("session_id")
        if not isinstance(session_id, str) or not session_id.strip():
            continue
        if not bool(session.get("reuse_allowed")):
            continue
        released_sessions.append(
            release_host_session_for_reuse(
                runtime_root,
                session_id.strip(),
                reason=reason,
                last_report_path=last_report_path,
            )
        )
    return released_sessions


def assign_reusable_host_session_to_task(
    runtime_root: str | Path | None,
    *,
    task_id: str,
    thread_id: str,
    launch_prompt: str,
    session_id: str | None = None,
    provider_id: str | None = None,
    worker_profile: str | None = None,
    tool_profile: str | None = None,
    allowed_tools: list[str] | None = None,
    owned_paths: list[str] | None = None,
    launch_bundle_paths: dict[str, str] | None = None,
    launch_bundle: dict[str, Any] | None = None,
    dispatch_idempotency_key: str | None = None,
) -> dict[str, Any]:
    resolved_runtime_root = normalize_runtime_root(runtime_root)
    candidate_payload = list_host_session_reuse_candidates(
        resolved_runtime_root,
        provider_id=provider_id,
        worker_profile=worker_profile,
        tool_profile=tool_profile,
        allowed_tools=allowed_tools,
        owned_paths=owned_paths,
    )
    candidates = candidate_payload["candidates"]
    if isinstance(session_id, str) and session_id.strip():
        requested_session_id = session_id.strip()
        candidates = [
            candidate
            for candidate in candidates
            if candidate.get("session_id") == requested_session_id
        ]
    if not candidates:
        raise ValueError("No reusable host session matches the requested task")

    selected = candidates[0]
    selected_session_id = selected.get("session_id")
    if not isinstance(selected_session_id, str) or not selected_session_id.strip():
        raise ValueError("Selected reusable host session is missing session_id")
    current = load_host_session(resolved_runtime_root, selected_session_id.strip())
    if not isinstance(current, dict):
        raise ValueError(f"Host session not found: {selected_session_id}")
    reuse_eligibility = current.get("session_card", {}).get("reuse_eligibility")
    if not (
        isinstance(reuse_eligibility, dict)
        and bool(reuse_eligibility.get("can_accept_new_task"))
    ):
        raise ValueError(f"Host session {selected_session_id} is not reusable now")

    now = utc_now()
    previous_task_id = current.get("task_id")
    task_history = current.get("task_history")
    if not isinstance(task_history, list):
        task_history = []
    if isinstance(previous_task_id, str) and previous_task_id.strip():
        task_history = [
            *task_history,
            {
                "task_id": previous_task_id.strip(),
                "released_at": current.get("released_at"),
                "last_report_path": current.get("last_report_path"),
            },
        ]

    current_reuse_count = current.get("reuse_count", 0)
    if not isinstance(current_reuse_count, int):
        current_reuse_count = 0

    context_paths_diff = _build_context_paths_diff(
        current.get("launch_bundle_paths"),
        launch_bundle_paths or {},
    )

    patch: dict[str, Any] = {
        "thread_id": thread_id,
        "task_id": task_id,
        "session_status": HOST_SESSION_WAITING_WORKER,
        "launch_prompt": launch_prompt,
        "launch_bundle_paths": launch_bundle_paths or {},
        "launch_bundle": launch_bundle
        if launch_bundle is not None
        else current.get("launch_bundle"),
        "context_delivery_mode": "reuse_delta",
        "context_delta_paths": launch_bundle_paths or {},
        "context_paths_diff": context_paths_diff,
        "dispatch_idempotency_key": dispatch_idempotency_key,
        "allowed_tools": _normalize_string_list(allowed_tools or current.get("allowed_tools")),
        "owned_paths": _normalize_string_list(owned_paths or current.get("owned_paths")),
        "worker_profile": worker_profile or current.get("worker_profile"),
        "tool_profile": tool_profile or current.get("tool_profile"),
        "attached_report_path": None,
        "stop_reason": None,
        "release_reason": None,
        "released_at": None,
        "assigned_at": now,
        "reused_from_task_id": previous_task_id,
        "reuse_count": current_reuse_count + 1,
        "dispatch_kind": "reuse",
        "task_history": task_history,
    }
    updated = _update_host_session(
        resolved_runtime_root,
        selected_session_id.strip(),
        patch=patch,
    )
    session_paths = resolve_host_session_paths(
        resolved_runtime_root,
        selected_session_id.strip(),
    )
    _append_host_session_mailbox_entry(
        session_paths.mailbox_path,
        {
            "timestamp": updated["updated_at"],
            "event_type": "assign_task",
            "command_id": f"assign_task-{uuid4().hex[:8]}",
            "command_status": "pending",
            "retry_count": 0,
            "session_id": selected_session_id,
            "task_id": task_id,
            "thread_id": thread_id,
            "previous_task_id": previous_task_id,
            "dispatch_kind": "reuse",
            "launch_prompt": launch_prompt,
            "launch_bundle_paths": launch_bundle_paths or {},
            "launch_bundle": launch_bundle,
            "context_delivery_mode": "reuse_delta",
            "context_delta_paths": launch_bundle_paths or {},
            "context_paths_diff": context_paths_diff,
            "context_revision": updated.get("context_revision"),
            "next_action": updated.get("session_card", {}).get("next_action")
            if isinstance(updated.get("session_card"), dict)
            else None,
        },
    )
    return updated


def get_task_host_session_summary(
    runtime_root: str | Path | None,
    task_id: str | None,
) -> dict[str, Any] | None:
    if not isinstance(task_id, str) or not task_id.strip():
        return None
    sessions = list_host_sessions(runtime_root, task_id=task_id.strip(), include_terminal=True)
    if not sessions:
        return None
    latest = sessions[-1]
    return {
        "session_id": latest.get("session_id"),
        "provider_id": latest.get("provider_id"),
        "provider_label": latest.get("provider_label"),
        "session_status": latest.get("session_status"),
        "updated_at": latest.get("updated_at"),
        "last_heartbeat_at": latest.get("last_heartbeat_at"),
        "resume_requested_at": latest.get("resume_requested_at"),
        "attached_report_path": latest.get("attached_report_path"),
        "host_controls": latest.get("host_controls"),
        "launch_bundle": latest.get("launch_bundle"),
        "session_card": latest.get("session_card"),
    }


def _candidate_report_paths(
    runtime_root: Path,
    task_id: str,
    session: dict[str, Any] | None,
) -> list[tuple[str, Path]]:
    task_paths = resolve_task_paths(runtime_root, task_id)
    candidates: list[tuple[str, Path]] = []
    attached_report_path = (
        session.get("attached_report_path")
        if isinstance(session, dict)
        else None
    )
    if isinstance(attached_report_path, str) and attached_report_path.strip():
        candidates.append(("attached_report", Path(attached_report_path.strip())))
    candidates.append(("worker_report", task_paths.worker_report_path))
    candidates.append(("report", task_paths.report_path))

    unique_candidates: list[tuple[str, Path]] = []
    seen_paths: set[str] = set()
    for source, path in candidates:
        normalized = str(path.resolve(strict=False))
        if normalized in seen_paths:
            continue
        seen_paths.add(normalized)
        unique_candidates.append((source, path))
    return unique_candidates


def _safe_load_report_payload(path: Path) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        payload = load_json(path)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    if is_dispatch_draft_report(payload):
        return None
    return payload


def find_task_report_candidate(
    runtime_root: str | Path | None,
    task_id: str | None,
) -> dict[str, Any] | None:
    if not isinstance(task_id, str) or not task_id.strip():
        return None
    resolved_runtime_root = normalize_runtime_root(runtime_root)
    sessions = list_host_sessions(
        resolved_runtime_root,
        task_id=task_id.strip(),
        include_terminal=True,
    )
    latest_session = sessions[-1] if sessions else None
    for report_source, report_path in _candidate_report_paths(
        resolved_runtime_root,
        task_id.strip(),
        latest_session,
    ):
        payload = _safe_load_report_payload(report_path)
        if not isinstance(payload, dict):
            continue
        return {
            "task_id": task_id.strip(),
            "report_source": report_source,
            "report_path": str(report_path),
            "report_payload": payload,
            "session_id": latest_session.get("session_id")
            if isinstance(latest_session, dict)
            else None,
            "session_status": latest_session.get("session_status")
            if isinstance(latest_session, dict)
            else None,
        }
    return None


def build_task_host_wait_summary(
    runtime_root: str | Path | None,
    task_id: str | None,
    *,
    timed_out: bool = False,
    wait_timeout_seconds: float | None = None,
) -> dict[str, Any] | None:
    if not isinstance(task_id, str) or not task_id.strip():
        return None
    resolved_runtime_root = normalize_runtime_root(runtime_root)
    sessions = list_host_sessions(
        resolved_runtime_root,
        task_id=task_id.strip(),
        include_terminal=True,
    )
    latest_session = sessions[-1] if sessions else None
    report_candidate = find_task_report_candidate(
        resolved_runtime_root,
        task_id.strip(),
    )
    now = datetime.now(timezone.utc)

    session_status = (
        str(latest_session.get("session_status") or "").strip()
        if isinstance(latest_session, dict)
        else None
    )
    updated_at = (
        parse_utc_timestamp(latest_session.get("updated_at"))
        if isinstance(latest_session, dict)
        else None
    )
    last_heartbeat_at = (
        parse_utc_timestamp(latest_session.get("last_heartbeat_at"))
        if isinstance(latest_session, dict)
        else None
    )
    updated_age_seconds = (
        max(int((now - updated_at).total_seconds()), 0)
        if updated_at is not None
        else None
    )
    last_heartbeat_age_seconds = (
        max(int((now - last_heartbeat_at).total_seconds()), 0)
        if last_heartbeat_at is not None
        else None
    )

    if isinstance(report_candidate, dict):
        wait_reason = "worker_report_available"
        next_action = "Ingest the available worker report and continue the task closure flow."
    elif not isinstance(latest_session, dict):
        wait_reason = "no_host_session_attached"
        next_action = "Inspect dispatch state and recreate or attach a host session."
    elif session_status == HOST_SESSION_RESUME_REQUESTED:
        wait_reason = "host_session_resume_requested"
        next_action = "Resume or inspect the external worker session before waiting again."
    elif session_status == HOST_SESSION_REPORT_READY:
        wait_reason = "host_session_report_ready_missing_file"
        next_action = "Inspect the attached report path and ingest the worker result."
    elif session_status in {
        HOST_SESSION_WAITING_WORKER,
        HOST_SESSION_PENDING_LAUNCH,
    }:
        if timed_out:
            wait_reason = "host_session_wait_timed_out"
            next_action = "Resume or inspect the external worker session after the timeout."
        else:
            wait_reason = "external_worker_running"
            next_action = "Wait for the external worker or inspect the host session."
    elif session_status == HOST_SESSION_FAILED:
        wait_reason = "host_session_failed_without_report"
        next_action = "Inspect why the host session failed before a worker report arrived."
    elif session_status == HOST_SESSION_STOPPED:
        wait_reason = "host_session_stopped_without_report"
        next_action = "Inspect why the host session stopped before a worker report arrived."
    elif session_status == HOST_SESSION_CLOSED:
        wait_reason = "host_session_closed"
        next_action = "Inspect whether the worker report was already ingested or archived."
    else:
        wait_reason = "host_session_state_unknown"
        next_action = "Inspect the host session and reconcile its state."

    attached_report_path = (
        latest_session.get("attached_report_path")
        if isinstance(latest_session, dict)
        else None
    )
    launch_bundle = (
        latest_session.get("launch_bundle")
        if isinstance(latest_session, dict)
        and isinstance(latest_session.get("launch_bundle"), dict)
        else {}
    )
    launch_result = (
        launch_bundle.get("launch_result")
        if isinstance(launch_bundle.get("launch_result"), dict)
        else None
    )
    return {
        "task_id": task_id.strip(),
        "session_id": latest_session.get("session_id")
        if isinstance(latest_session, dict)
        else None,
        "provider_id": latest_session.get("provider_id")
        if isinstance(latest_session, dict)
        else None,
        "provider_label": latest_session.get("provider_label")
        if isinstance(latest_session, dict)
        else None,
        "session_status": session_status,
        "updated_at": latest_session.get("updated_at")
        if isinstance(latest_session, dict)
        else None,
        "updated_age_seconds": updated_age_seconds,
        "last_heartbeat_at": latest_session.get("last_heartbeat_at")
        if isinstance(latest_session, dict)
        else None,
        "last_heartbeat_age_seconds": last_heartbeat_age_seconds,
        "resume_requested_at": latest_session.get("resume_requested_at")
        if isinstance(latest_session, dict)
        else None,
        "resume_request_count": latest_session.get("resume_request_count")
        if isinstance(latest_session, dict)
        else 0,
        "attached_report_path": attached_report_path,
        "auto_launch_supported": bool(launch_bundle.get("auto_launch_supported")),
        "launch_status": launch_bundle.get("launch_status"),
        "launch_result": launch_result,
        "launch_error": launch_result.get("error")
        if isinstance(launch_result, dict)
        else None,
        "host_controls": latest_session.get("host_controls")
        if isinstance(latest_session, dict)
        else None,
        "session_card": latest_session.get("session_card")
        if isinstance(latest_session, dict)
        else None,
        "wait_reason": wait_reason,
        "next_action": next_action,
        "report_available": isinstance(report_candidate, dict),
        "report_source": report_candidate.get("report_source")
        if isinstance(report_candidate, dict)
        else None,
        "report_path": report_candidate.get("report_path")
        if isinstance(report_candidate, dict)
        else None,
        "timed_out": bool(timed_out),
        "wait_timeout_seconds": wait_timeout_seconds,
        "resume_recommended": bool(timed_out)
        and session_status
        in {HOST_SESSION_WAITING_WORKER, HOST_SESSION_PENDING_LAUNCH},
    }


def request_task_host_session_resume(
    runtime_root: str | Path | None,
    task_id: str | None,
    *,
    note: str | None = None,
) -> dict[str, Any] | None:
    if not isinstance(task_id, str) or not task_id.strip():
        return None
    sessions = list_host_sessions(
        runtime_root,
        task_id=task_id.strip(),
        include_terminal=False,
    )
    if not sessions:
        return None
    latest = sessions[-1]
    session_id = latest.get("session_id")
    session_status = str(latest.get("session_status") or "").strip()
    if not isinstance(session_id, str) or not session_id.strip():
        return None
    if session_status not in {
        HOST_SESSION_PENDING_LAUNCH,
        HOST_SESSION_WAITING_WORKER,
        HOST_SESSION_RESUME_REQUESTED,
    }:
        return latest
    return resume_host_session(runtime_root, session_id.strip(), note=note)


def resume_waiting_host_sessions(
    runtime_root: str | Path | None,
    *,
    provider_id: str | None = None,
    only_resume_requested: bool = False,
    note: str | None = None,
) -> dict[str, Any]:
    resolved_runtime_root = normalize_runtime_root(runtime_root)
    resumed_sessions: list[dict[str, Any]] = []
    skipped_sessions: list[dict[str, Any]] = []
    matched_session_count = 0
    provider_filter = (
        provider_id.strip()
        if isinstance(provider_id, str) and provider_id.strip()
        else None
    )
    for session in list_host_sessions(resolved_runtime_root, include_terminal=False):
        current_provider_id = str(session.get("provider_id") or "").strip()
        if provider_filter and current_provider_id != provider_filter:
            continue
        session_status = str(session.get("session_status") or "").strip()
        eligible_states = (
            {HOST_SESSION_RESUME_REQUESTED}
            if only_resume_requested
            else {
                HOST_SESSION_PENDING_LAUNCH,
                HOST_SESSION_WAITING_WORKER,
                HOST_SESSION_RESUME_REQUESTED,
            }
        )
        if session_status not in eligible_states:
            skipped_sessions.append(
                {
                    "session_id": session.get("session_id"),
                    "task_id": session.get("task_id"),
                    "provider_id": current_provider_id or None,
                    "session_status": session_status or None,
                    "reason": "session_not_resumable",
                }
            )
            continue
        matched_session_count += 1
        session_id = session.get("session_id")
        if not isinstance(session_id, str) or not session_id.strip():
            skipped_sessions.append(
                {
                    "session_id": session.get("session_id"),
                    "task_id": session.get("task_id"),
                    "provider_id": current_provider_id or None,
                    "session_status": session_status or None,
                    "reason": "missing_session_id",
                }
            )
            continue
        resumed = resume_host_session(
            resolved_runtime_root,
            session_id.strip(),
            note=note,
        )
        resumed_sessions.append(
            {
                "session_id": resumed.get("session_id"),
                "task_id": resumed.get("task_id"),
                "provider_id": resumed.get("provider_id"),
                "session_status": resumed.get("session_status"),
                "resume_request_count": resumed.get("resume_request_count"),
            }
        )

    return {
        "runtime_root": str(resolved_runtime_root),
        "provider_id": provider_filter,
        "only_resume_requested": bool(only_resume_requested),
        "matched_session_count": matched_session_count,
        "resumed_session_count": len(resumed_sessions),
        "resumed_sessions": resumed_sessions,
        "skipped_sessions": skipped_sessions,
    }


def build_host_runtime_summary(
    runtime_root: str | Path | None,
    *,
    task_id: str | None = None,
) -> dict[str, Any]:
    resolved_runtime_root = normalize_runtime_root(runtime_root)
    registry = refresh_host_runtime_registry(resolved_runtime_root)
    sessions = list_host_sessions(
        resolved_runtime_root,
        task_id=task_id,
        include_terminal=True,
    )
    session_cards = [
        session.get("session_card")
        for session in sessions
        if isinstance(session.get("session_card"), dict)
    ]
    worker_profile_counts: dict[str, int] = {}
    reuse_allowed_count = 0
    auto_launch_enabled_count = 0
    failed_launch_count = 0
    reusable_now_count = 0
    reusable_after_release_count = 0
    for card in session_cards:
        worker_profile = str(card.get("worker_profile") or "unknown")
        worker_profile_counts[worker_profile] = worker_profile_counts.get(worker_profile, 0) + 1
        if bool(card.get("reuse_allowed")):
            reuse_allowed_count += 1
        if bool(card.get("auto_launch_supported")):
            auto_launch_enabled_count += 1
        if str(card.get("launch_status") or "").strip() == "failed":
            failed_launch_count += 1
        reuse_eligibility = card.get("reuse_eligibility")
        if isinstance(reuse_eligibility, dict):
            if bool(reuse_eligibility.get("can_accept_new_task")):
                reusable_now_count += 1
            if bool(reuse_eligibility.get("eligible_after_release")):
                reusable_after_release_count += 1
    return {
        "runtime_root": str(resolved_runtime_root),
        "registry": registry,
        "session_count": len(sessions),
        "sessions": sessions,
        "session_cards": session_cards,
        "session_pool": {
            "session_count": len(session_cards),
            "reuse_allowed_count": reuse_allowed_count,
            "auto_launch_enabled_count": auto_launch_enabled_count,
            "failed_launch_count": failed_launch_count,
            "reusable_now_count": reusable_now_count,
            "reusable_after_release_count": reusable_after_release_count,
            "candidate_after_release_count": reusable_after_release_count,
            "worker_profile_counts": worker_profile_counts,
        },
        "task_wait": build_task_host_wait_summary(
            resolved_runtime_root,
            task_id,
        ),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect and manage commander host runtime sessions."
    )
    parser.add_argument("--runtime-root", default=None, help="Override runtime root")
    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("status", help="Show host runtime summary")
    status_parser.add_argument("--task-id", default=None, help="Optional task id filter")

    inspect_parser = subparsers.add_parser("inspect", help="Inspect a host session")
    inspect_parser.add_argument("--session-id", required=True)

    mailbox_parser = subparsers.add_parser("mailbox", help="Read a host session mailbox")
    mailbox_parser.add_argument("--session-id", required=True)
    mailbox_parser.add_argument("--after-sequence", type=int, default=0)
    mailbox_parser.add_argument("--commands-only", action="store_true")
    mailbox_parser.add_argument("--unacked-only", action="store_true")

    ack_mailbox_parser = subparsers.add_parser(
        "ack-mailbox",
        help="Acknowledge host session mailbox entries through a sequence",
    )
    ack_mailbox_parser.add_argument("--session-id", required=True)
    ack_mailbox_parser.add_argument("--through-sequence", type=int, required=True)
    ack_mailbox_parser.add_argument("--note", default=None)

    retry_mailbox_parser = subparsers.add_parser(
        "retry-mailbox",
        help="Re-enqueue unacked host session mailbox commands",
    )
    retry_mailbox_parser.add_argument("--session-id", required=True)
    retry_mailbox_parser.add_argument("--max-retries", type=int, default=3)
    retry_mailbox_parser.add_argument("--note", default=None)

    send_command_parser = subparsers.add_parser(
        "send-command",
        help="Append a command event to a host session mailbox",
    )
    send_command_parser.add_argument("--session-id", required=True)
    send_command_parser.add_argument(
        "--command-type",
        required=True,
        choices=sorted(HOST_SESSION_MAILBOX_COMMAND_EVENTS - {"assign_task"}),
    )
    send_command_parser.add_argument("--payload-json", default=None)
    send_command_parser.add_argument("--note", default=None)

    heartbeat_parser = subparsers.add_parser("heartbeat", help="Touch session heartbeat")
    heartbeat_parser.add_argument("--session-id", required=True)
    heartbeat_parser.add_argument("--note", default=None)

    resume_parser = subparsers.add_parser("resume", help="Mark a session for resume")
    resume_parser.add_argument("--session-id", required=True)
    resume_parser.add_argument("--note", default=None)

    resume_waits_parser = subparsers.add_parser(
        "resume-waits",
        help="Batch mark waiting host sessions for resume",
    )
    resume_waits_parser.add_argument("--provider-id", default=None)
    resume_waits_parser.add_argument("--only-resume-requested", action="store_true")
    resume_waits_parser.add_argument("--note", default=None)

    reuse_candidates_parser = subparsers.add_parser(
        "reuse-candidates",
        help="List host sessions that may be reused after release",
    )
    reuse_candidates_parser.add_argument("--provider-id", default=None)
    reuse_candidates_parser.add_argument("--worker-profile", default=None)
    reuse_candidates_parser.add_argument("--tool-profile", default=None)
    reuse_candidates_parser.add_argument("--allowed-tool", action="append", default=[])
    reuse_candidates_parser.add_argument("--owned-path", action="append", default=[])
    reuse_candidates_parser.add_argument("--include-terminal", action="store_true")
    reuse_candidates_parser.add_argument("--include-rejected", action="store_true")

    stop_parser = subparsers.add_parser("stop", help="Stop a host session")
    stop_parser.add_argument("--session-id", required=True)
    stop_parser.add_argument("--reason", default="manual_stop")

    release_reusable_parser = subparsers.add_parser(
        "release-reusable",
        help="Release a host session into the reusable pool",
    )
    release_reusable_parser.add_argument("--session-id", required=True)
    release_reusable_parser.add_argument("--reason", default="released_for_reuse")
    release_reusable_parser.add_argument("--last-report-path", default=None)

    release_task_reusable_parser = subparsers.add_parser(
        "release-task-reusable",
        help="Release reusable host sessions attached to a task",
    )
    release_task_reusable_parser.add_argument("--task-id", required=True)
    release_task_reusable_parser.add_argument("--reason", default="released_for_reuse")
    release_task_reusable_parser.add_argument("--last-report-path", default=None)

    assign_reusable_parser = subparsers.add_parser(
        "assign-reusable",
        help="Assign a released reusable host session to a new task",
    )
    assign_reusable_parser.add_argument("--task-id", required=True)
    assign_reusable_parser.add_argument("--thread-id", required=True)
    assign_reusable_parser.add_argument("--launch-prompt", required=True)
    assign_reusable_parser.add_argument("--session-id", default=None)
    assign_reusable_parser.add_argument("--provider-id", default=None)
    assign_reusable_parser.add_argument("--worker-profile", default=None)
    assign_reusable_parser.add_argument("--tool-profile", default=None)
    assign_reusable_parser.add_argument("--allowed-tool", action="append", default=[])
    assign_reusable_parser.add_argument("--owned-path", action="append", default=[])
    assign_reusable_parser.add_argument("--dispatch-idempotency-key", default=None)
    assign_reusable_parser.add_argument("--packet-path", default=None)
    assign_reusable_parser.add_argument("--context-bundle-path", default=None)
    assign_reusable_parser.add_argument("--worker-brief-path", default=None)
    assign_reusable_parser.add_argument("--worker-report-path", default=None)
    assign_reusable_parser.add_argument("--resume-anchor-path", default=None)
    assign_reusable_parser.add_argument("--checkpoint-path", default=None)
    assign_reusable_parser.add_argument("--status-path", default=None)

    start_parser = subparsers.add_parser("start", help="Manually create a host session")
    start_parser.add_argument("--thread-id", required=True)
    start_parser.add_argument("--task-id", required=True)
    start_parser.add_argument("--provider-id", required=True)
    start_parser.add_argument("--provider-label", required=True)
    start_parser.add_argument("--host-adapter-id", default="external-window")
    start_parser.add_argument("--launch-prompt", required=True)
    start_parser.add_argument("--dispatch-idempotency-key", default=None)
    start_parser.add_argument("--packet-path", default=None)
    start_parser.add_argument("--context-bundle-path", default=None)
    start_parser.add_argument("--worker-brief-path", default=None)
    start_parser.add_argument("--worker-report-path", default=None)
    start_parser.add_argument("--resume-anchor-path", default=None)
    start_parser.add_argument("--checkpoint-path", default=None)
    start_parser.add_argument("--status-path", default=None)
    start_parser.add_argument("--worker-id", default=None)
    start_parser.add_argument("--worker-profile", default=None)
    start_parser.add_argument("--preferred-worker-profile", default=None)
    start_parser.add_argument("--tool-profile", default=None)
    start_parser.add_argument("--allowed-tool", action="append", default=[])
    start_parser.add_argument("--forbidden-path", action="append", default=[])
    start_parser.add_argument("--owned-path", action="append", default=[])
    start_parser.add_argument("--reuse-allowed", action="store_true")
    start_parser.add_argument("--dispatch-kind", default=None)
    start_parser.add_argument("--closure-policy", default=None)
    start_parser.add_argument("--provider-note", action="append", default=[])
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "status":
        payload = build_host_runtime_summary(args.runtime_root, task_id=args.task_id)
    elif args.command == "inspect":
        payload = load_host_session(args.runtime_root, args.session_id)
        if payload is None:
            raise SystemExit(f"Host session not found: {args.session_id}")
    elif args.command == "mailbox":
        payload = read_host_session_mailbox_entries(
            args.runtime_root,
            args.session_id,
            after_sequence=args.after_sequence,
            commands_only=bool(args.commands_only),
            unacked_only=bool(args.unacked_only),
        )
    elif args.command == "ack-mailbox":
        payload = ack_host_session_mailbox(
            args.runtime_root,
            args.session_id,
            through_sequence=args.through_sequence,
            note=args.note,
        )
    elif args.command == "retry-mailbox":
        payload = retry_unacked_host_session_mailbox_commands(
            args.runtime_root,
            args.session_id,
            max_retries=args.max_retries,
            note=args.note,
        )
    elif args.command == "send-command":
        command_payload: dict[str, Any] | None = None
        if isinstance(args.payload_json, str) and args.payload_json.strip():
            try:
                parsed_payload = json.loads(args.payload_json)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"Invalid --payload-json: {exc}") from exc
            if not isinstance(parsed_payload, dict):
                raise SystemExit("--payload-json must decode to a JSON object")
            command_payload = parsed_payload
        payload = append_host_session_mailbox_command(
            args.runtime_root,
            args.session_id,
            command_type=args.command_type,
            command_payload=command_payload,
            note=args.note,
        )
    elif args.command == "heartbeat":
        payload = heartbeat_host_session(
            args.runtime_root,
            args.session_id,
            note=args.note,
        )
    elif args.command == "resume":
        payload = resume_host_session(
            args.runtime_root,
            args.session_id,
            note=args.note,
        )
    elif args.command == "resume-waits":
        payload = resume_waiting_host_sessions(
            args.runtime_root,
            provider_id=args.provider_id,
            only_resume_requested=bool(args.only_resume_requested),
            note=args.note,
        )
    elif args.command == "reuse-candidates":
        payload = list_host_session_reuse_candidates(
            args.runtime_root,
            provider_id=args.provider_id,
            worker_profile=args.worker_profile,
            tool_profile=args.tool_profile,
            allowed_tools=[item for item in args.allowed_tool if item],
            owned_paths=[item for item in args.owned_path if item],
            include_terminal=bool(args.include_terminal),
            include_rejected=bool(args.include_rejected),
        )
    elif args.command == "stop":
        payload = stop_host_session(
            args.runtime_root,
            args.session_id,
            reason=args.reason,
        )
    elif args.command == "release-reusable":
        payload = release_host_session_for_reuse(
            args.runtime_root,
            args.session_id,
            reason=args.reason,
            last_report_path=args.last_report_path,
        )
    elif args.command == "release-task-reusable":
        payload = release_task_host_sessions_for_reuse(
            args.runtime_root,
            args.task_id,
            reason=args.reason,
            last_report_path=args.last_report_path,
        )
    elif args.command == "assign-reusable":
        launch_bundle_paths = {
            key: value
            for key, value in {
                "packet_path": args.packet_path,
                "context_bundle_path": args.context_bundle_path,
                "worker_brief_path": args.worker_brief_path,
                "worker_report_path": args.worker_report_path,
                "resume_anchor_path": args.resume_anchor_path,
                "checkpoint_path": args.checkpoint_path,
                "status_path": args.status_path,
            }.items()
            if isinstance(value, str) and value.strip()
        }
        payload = assign_reusable_host_session_to_task(
            args.runtime_root,
            task_id=args.task_id,
            thread_id=args.thread_id,
            launch_prompt=args.launch_prompt,
            session_id=args.session_id,
            provider_id=args.provider_id,
            worker_profile=args.worker_profile,
            tool_profile=args.tool_profile,
            allowed_tools=[item for item in args.allowed_tool if item],
            owned_paths=[item for item in args.owned_path if item],
            launch_bundle_paths=launch_bundle_paths,
            dispatch_idempotency_key=args.dispatch_idempotency_key,
        )
    elif args.command == "start":
        launch_bundle_paths = {
            key: value
            for key, value in {
                "packet_path": args.packet_path,
                "context_bundle_path": args.context_bundle_path,
                "worker_brief_path": args.worker_brief_path,
                "worker_report_path": args.worker_report_path,
                "resume_anchor_path": args.resume_anchor_path,
                "checkpoint_path": args.checkpoint_path,
                "status_path": args.status_path,
            }.items()
            if isinstance(value, str) and value.strip()
        }
        payload = create_host_session(
            args.runtime_root,
            thread_id=args.thread_id,
            task_id=args.task_id,
            provider_id=args.provider_id,
            provider_label=args.provider_label,
            host_adapter_id=args.host_adapter_id,
            launch_prompt=args.launch_prompt,
            provider_notes=[item for item in args.provider_note if item],
            launch_bundle_paths=launch_bundle_paths,
            dispatch_idempotency_key=args.dispatch_idempotency_key,
            worker_id=args.worker_id,
            worker_profile=args.worker_profile,
            preferred_worker_profile=args.preferred_worker_profile,
            tool_profile=args.tool_profile,
            allowed_tools=[item for item in args.allowed_tool if item],
            forbidden_paths=[item for item in args.forbidden_path if item],
            owned_paths=[item for item in args.owned_path if item],
            reuse_allowed=bool(args.reuse_allowed),
            dispatch_kind=args.dispatch_kind,
            closure_policy=args.closure_policy,
        )
    else:
        raise SystemExit(f"Unsupported command: {args.command}")

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
