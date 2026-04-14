from __future__ import annotations

from pathlib import Path
from typing import Any

from commander.transport.scripts.commander_harness import (
    build_task_worker_binding_summary,
    normalize_runtime_root,
)


class WorkerOwnershipError(RuntimeError):
    """Raised when assigning another worker would violate single-writer ownership."""


def ensure_task_has_no_active_writer(
    runtime_root: str | Path | None,
    task_id: str,
    *,
    binding_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_runtime_root = normalize_runtime_root(runtime_root)
    summary = binding_summary or build_task_worker_binding_summary(
        resolved_runtime_root, task_id
    )
    if summary.get("has_active_lease"):
        leased_worker_ids = summary.get("leased_worker_ids") or []
        raise WorkerOwnershipError(
            f"Task {task_id!r} already has active leased worker(s): {leased_worker_ids!r}"
        )
    return summary
