from __future__ import annotations

from pathlib import Path
from typing import Any

from commander.graph.adapters.worker_providers import get_tool_profile
from commander.graph.policies.ownership import ensure_task_has_no_active_writer
from commander.transport.scripts.commander_harness import (
    acquire_worker_slot,
    build_task_worker_binding_summary,
    normalize_runtime_root,
)


def assign_worker_owner(
    runtime_root: str | Path | None,
    *,
    task_packet: dict[str, Any],
    lease_seconds: int | None = None,
) -> dict[str, Any]:
    resolved_runtime_root = normalize_runtime_root(runtime_root)
    task_id = _required_string(task_packet, "task_id")
    tool_profile = get_tool_profile(_required_string(task_packet, "tool_profile"))
    binding_before = build_task_worker_binding_summary(resolved_runtime_root, task_id)
    ensure_task_has_no_active_writer(
        resolved_runtime_root, task_id, binding_summary=binding_before
    )
    assignment = acquire_worker_slot(
        resolved_runtime_root,
        task_id=task_id,
        worker_profile=_required_string(task_packet, "worker_profile"),
        preferred_worker_profile=_optional_string(
            task_packet, "preferred_worker_profile"
        ),
        tool_profile=tool_profile.profile_id,
        allowed_tools=_string_list(task_packet.get("allowed_tools")),
        reuse_allowed=bool(task_packet.get("reuse_allowed")),
        **({"lease_seconds": lease_seconds} if lease_seconds is not None else {}),
    )
    return {
        "task_id": task_id,
        "binding_before": binding_before,
        "assignment": assignment,
        "tool_profile": {
            "profile_id": tool_profile.profile_id,
            "allowed_tools": list(tool_profile.allowed_tools),
            "read_only": tool_profile.read_only,
        },
        "binding_after": build_task_worker_binding_summary(
            resolved_runtime_root, task_id
        ),
    }


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"task_packet.{key} must be a non-empty string")
    return value


def _optional_string(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"task_packet.{key} must be null or a non-empty string")
    return value


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]
