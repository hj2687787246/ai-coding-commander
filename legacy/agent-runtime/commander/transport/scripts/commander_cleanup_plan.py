from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from commander.transport.scripts.commander_archive_catalog import (
    get_archive_catalog_path,
    get_archive_root,
    get_archive_snapshots_root,
    load_archive_catalog,
    sync_archive_catalog_snapshot,
)
from commander.transport.scripts.commander_archive_cleanup import perform_archive_cleanup
from commander.transport.scripts.commander_harness import (
    is_cleanup_eligible,
    load_json,
    normalize_runtime_root,
    resolve_task_paths,
    utc_now,
)
from commander.transport.scripts.commander_task_catalog import load_task_catalog


PROTECTED_NAMESPACE_RULES: tuple[dict[str, object], ...] = (
    {
        "relative_path": "tasks",
        "reason": "Live commander task snapshots remain the source of truth until task-scoped archive cleanup runs.",
        "allowed_entrypoints": ["commander_close.py", "commander_archive.py", "commander_archive_cleanup.py"],
    },
    {
        "relative_path": "improvements",
        "reason": "Live improvement candidates should only move together with their archived task lifecycle.",
        "allowed_entrypoints": ["commander_archive_cleanup.py", "commander_archive_improvement.py"],
    },
    {
        "relative_path": "improvement_actions",
        "reason": "Improvement apply artifacts are part of the audit trail and must move with the owning task.",
        "allowed_entrypoints": ["commander_archive_cleanup.py", "commander_apply_improvement.py"],
    },
    {
        "relative_path": "workers",
        "reason": "Worker leases and runtime ownership are active control-plane state, not generic cleanup residue.",
        "allowed_entrypoints": ["commander_worker_pool.py"],
    },
    {
        "relative_path": "archive/tasks",
        "reason": "Archived task evidence is retained history and should not be bulk-deleted by generic runtime cleanup.",
        "allowed_entrypoints": ["commander_archive_catalog.py", "future_compaction_entrypoint"],
    },
    {
        "relative_path": "archive/improvements",
        "reason": "Archived improvement candidates stay with archived task evidence for later review.",
        "allowed_entrypoints": ["commander_archive_catalog.py", "future_compaction_entrypoint"],
    },
    {
        "relative_path": "archive/improvement_actions",
        "reason": "Archived improvement action outputs remain part of the archived task evidence set.",
        "allowed_entrypoints": ["commander_archive_catalog.py", "future_compaction_entrypoint"],
    },
    {
        "relative_path": "archive/catalog.json",
        "reason": "Archive catalog snapshot is controlled by explicit sync, not generic cleanup.",
        "allowed_entrypoints": ["commander_archive_catalog.py --sync"],
    },
    {
        "relative_path": "archive/snapshots",
        "reason": "Compact secondary summaries are the secondary storage layer for archived task metadata.",
        "allowed_entrypoints": ["commander_archive_catalog.py --sync"],
    },
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan commander runtime cleanup work, protected namespaces, and optional archive maintenance actions."
    )
    parser.add_argument("--runtime-root", default=None, help="Override runtime root. Defaults to .runtime/commander")
    parser.add_argument("--task-id", default=None, help="Focus the plan on a single live task")
    parser.add_argument("--apply", action="store_true", help="Apply cleanup-eligible archive moves before returning the plan")
    parser.add_argument(
        "--sync-archive-catalog",
        action="store_true",
        help="Sync archive catalog.json and secondary snapshots before returning the plan",
    )
    return parser.parse_args(argv)


def _normalize_optional_string(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def build_protected_paths(runtime_root: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for rule in PROTECTED_NAMESPACE_RULES:
        relative_path = str(rule["relative_path"])
        path = runtime_root / Path(relative_path)
        entries.append(
            {
                "path": str(path),
                "relative_path": relative_path.replace("\\", "/"),
                "exists": path.exists(),
                "reason": str(rule["reason"]),
                "allowed_entrypoints": list(rule["allowed_entrypoints"]),
            }
        )
    return entries


def build_cleanup_candidates(runtime_root: Path, *, task_id: str | None = None) -> list[dict[str, Any]]:
    catalog = load_task_catalog(runtime_root)
    entries = catalog["tasks"]
    if task_id:
        entries = [entry for entry in entries if entry.get("task_id") == task_id]

    candidates: list[dict[str, Any]] = []
    for entry in entries:
        if entry.get("lifecycle_status") != "archived":
            continue
        cleanup_eligible = bool(entry.get("cleanup_eligible"))
        if not cleanup_eligible:
            paths = resolve_task_paths(runtime_root, str(entry.get("task_id") or ""))
            if paths.lifecycle_path.exists():
                lifecycle = load_json(paths.lifecycle_path)
                if isinstance(lifecycle, dict):
                    cleanup_eligible = is_cleanup_eligible(lifecycle)
        if not cleanup_eligible:
            continue
        candidates.append(
            {
                "task_id": entry["task_id"],
                "title": entry.get("title"),
                "archived_at": entry.get("archived_at"),
                "current_phase": entry.get("current_phase"),
                "recommended_action": entry.get("recommended_action"),
                "next_minimal_action": entry.get("next_minimal_action"),
            }
        )
    candidates.sort(key=lambda item: (str(item.get("archived_at", "")), str(item.get("task_id", ""))), reverse=True)
    return candidates


def build_archive_sync_status(runtime_root: Path) -> dict[str, Any]:
    archive_catalog = load_archive_catalog(runtime_root)
    archive_catalog_path = get_archive_catalog_path(runtime_root)
    snapshots_root = get_archive_snapshots_root(runtime_root)
    snapshot_paths = sorted(snapshots_root.glob("*.summary.json")) if snapshots_root.exists() else []
    expected_snapshot_names = {
        Path(str(task.get("secondary_snapshot_path") or "")).name
        for task in archive_catalog["tasks"]
        if str(task.get("secondary_snapshot_path") or "").strip()
    }
    missing_secondary_snapshot_task_ids = [
        str(task["task_id"])
        for task in archive_catalog["tasks"]
        if not bool(task.get("secondary_snapshot_exists"))
    ]
    stale_secondary_snapshot_paths = [
        str(path) for path in snapshot_paths if path.name not in expected_snapshot_names
    ]

    warnings: list[str] = []
    if archive_catalog["task_count"] > 0 and not archive_catalog_path.exists():
        warnings.append("archive_catalog_snapshot_missing")
    if missing_secondary_snapshot_task_ids:
        warnings.append("missing_secondary_snapshots")
    if stale_secondary_snapshot_paths:
        warnings.append("stale_secondary_snapshots")

    return {
        "archive_root": str(get_archive_root(runtime_root)),
        "archive_catalog_path": str(archive_catalog_path),
        "archive_catalog_exists": archive_catalog_path.exists(),
        "archive_task_count": archive_catalog["task_count"],
        "secondary_snapshots_root": str(snapshots_root),
        "secondary_snapshot_count": len(snapshot_paths),
        "missing_secondary_snapshot_task_ids": missing_secondary_snapshot_task_ids,
        "stale_secondary_snapshot_paths": stale_secondary_snapshot_paths,
        "needs_sync": bool(warnings),
        "warnings": warnings,
    }


def build_cleanup_plan(runtime_root: str | Path | None = None, *, task_id: str | None = None) -> dict[str, Any]:
    resolved_runtime_root = normalize_runtime_root(runtime_root)
    cleanup_candidates = build_cleanup_candidates(resolved_runtime_root, task_id=task_id)
    archive_sync_status = build_archive_sync_status(resolved_runtime_root)

    recommended_actions: list[str] = []
    if cleanup_candidates:
        recommended_actions.append("Run commander_archive_cleanup.py for cleanup-eligible archived tasks.")
    if archive_sync_status["needs_sync"]:
        recommended_actions.append("Run commander_archive_catalog.py --sync to refresh archive catalog.json and secondary snapshots.")
    if not recommended_actions:
        recommended_actions.append("No immediate commander runtime cleanup action is required.")

    return {
        "schema_version": "commander-cleanup-plan-v1",
        "generated_at": utc_now(),
        "runtime_root": str(resolved_runtime_root),
        "archive_root": str(get_archive_root(resolved_runtime_root)),
        "protected_paths": build_protected_paths(resolved_runtime_root),
        "cleanup_candidate_count": len(cleanup_candidates),
        "cleanup_candidate_ids": [candidate["task_id"] for candidate in cleanup_candidates],
        "cleanup_candidates": cleanup_candidates,
        "archive_sync_status": archive_sync_status,
        "recommended_actions": recommended_actions,
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    resolved_runtime_root = normalize_runtime_root(args.runtime_root)

    cleanup_apply_result: dict[str, Any] | None = None
    archive_sync_result: dict[str, Any] | None = None
    if args.apply:
        cleanup_apply_result = perform_archive_cleanup(resolved_runtime_root, task_id=args.task_id, dry_run=False)
    elif args.sync_archive_catalog:
        archive_sync_result = sync_archive_catalog_snapshot(resolved_runtime_root)

    plan = build_cleanup_plan(resolved_runtime_root, task_id=args.task_id)
    plan["maintenance_actions"] = {
        "cleanup_apply_result": cleanup_apply_result,
        "archive_catalog_sync_result": archive_sync_result
        or (cleanup_apply_result or {}).get("archive_catalog_sync"),
    }
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
