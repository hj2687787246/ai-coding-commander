from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from commander.transport.scripts.commander_harness import load_json, normalize_runtime_root, utc_now, write_json


ARCHIVE_CATALOG_SCHEMA_VERSION = "commander-archive-catalog-v1"
ARCHIVE_SECONDARY_SNAPSHOT_SCHEMA_VERSION = "commander-archive-secondary-snapshot-v1"


def _archive_root(runtime_root: Path) -> Path:
    return runtime_root / "archive"


def get_archive_root(runtime_root: Path) -> Path:
    return _archive_root(runtime_root)


def _archive_catalog_path(runtime_root: Path) -> Path:
    return _archive_root(runtime_root) / "catalog.json"


def get_archive_catalog_path(runtime_root: Path) -> Path:
    return _archive_catalog_path(runtime_root)


def _archive_snapshots_root(runtime_root: Path) -> Path:
    return _archive_root(runtime_root) / "snapshots"


def get_archive_snapshots_root(runtime_root: Path) -> Path:
    return _archive_snapshots_root(runtime_root)


def _archive_secondary_snapshot_path(runtime_root: Path, task_id: str) -> Path:
    return _archive_snapshots_root(runtime_root) / f"{task_id}.summary.json"


def get_archive_secondary_snapshot_path(runtime_root: Path, task_id: str) -> Path:
    return _archive_secondary_snapshot_path(runtime_root, task_id)


def _archive_tasks_root(runtime_root: Path) -> Path:
    return _archive_root(runtime_root) / "tasks"


def _load_json_if_dict(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = load_json(path)
    return payload if isinstance(payload, dict) else {}


def discover_archived_task_ids(runtime_root: Path) -> list[str]:
    tasks_root = _archive_tasks_root(runtime_root)
    if not tasks_root.exists():
        return []
    return sorted(path.name for path in tasks_root.iterdir() if path.is_dir())


def build_archive_catalog_entry(runtime_root: Path, task_id: str) -> dict[str, Any]:
    archive_root = _archive_root(runtime_root)
    task_dir = archive_root / "tasks" / task_id
    secondary_snapshot_path = _archive_secondary_snapshot_path(runtime_root, task_id)
    manifest = _load_json_if_dict(task_dir / "archive_manifest.json")
    status = _load_json_if_dict(task_dir / "status.json")
    lifecycle = _load_json_if_dict(task_dir / "lifecycle.json")
    report = _load_json_if_dict(task_dir / "report.json")
    action_dirs = manifest.get("improvement_action_dirs") if isinstance(manifest.get("improvement_action_dirs"), list) else []

    return {
        "task_id": task_id,
        "title": status.get("title"),
        "lifecycle_status": status.get("lifecycle_status") or lifecycle.get("lifecycle_status"),
        "current_phase": status.get("current_phase"),
        "worker_status": status.get("worker_status") or report.get("status"),
        "archived_at": status.get("archived_at") or lifecycle.get("archived_at"),
        "cleanup_eligible": status.get("cleanup_eligible"),
        "moved_at": manifest.get("moved_at"),
        "archive_task_dir": str(task_dir),
        "archive_manifest_path": str(task_dir / "archive_manifest.json"),
        "archive_candidate_path": manifest.get("destination_candidate_path"),
        "improvement_action_dir_count": len(action_dirs),
        "improvement_action_dirs": action_dirs,
        "retention_policy": manifest.get("retention_policy"),
        "source_task_dir": manifest.get("source_task_dir"),
        "secondary_snapshot_path": str(secondary_snapshot_path),
        "secondary_snapshot_exists": secondary_snapshot_path.exists(),
    }


def build_archive_secondary_snapshot(runtime_root: Path, task_id: str) -> dict[str, Any]:
    entry = build_archive_catalog_entry(runtime_root, task_id)
    return {
        "schema_version": ARCHIVE_SECONDARY_SNAPSHOT_SCHEMA_VERSION,
        "snapshot_generated_at": utc_now(),
        "task_id": entry["task_id"],
        "title": entry["title"],
        "lifecycle_status": entry["lifecycle_status"],
        "current_phase": entry["current_phase"],
        "worker_status": entry["worker_status"],
        "archived_at": entry["archived_at"],
        "cleanup_eligible": entry["cleanup_eligible"],
        "moved_at": entry["moved_at"],
        "archive_task_dir": entry["archive_task_dir"],
        "archive_manifest_path": entry["archive_manifest_path"],
        "archive_candidate_path": entry["archive_candidate_path"],
        "improvement_action_dir_count": entry["improvement_action_dir_count"],
        "improvement_action_dirs": entry["improvement_action_dirs"],
        "retention_policy": entry["retention_policy"],
        "source_task_dir": entry["source_task_dir"],
    }


def load_archive_catalog(runtime_root: str | Path | None = None, *, task_id: str | None = None) -> dict[str, Any]:
    resolved_runtime_root = normalize_runtime_root(runtime_root)
    task_ids = [task_id] if task_id else discover_archived_task_ids(resolved_runtime_root)
    tasks = [build_archive_catalog_entry(resolved_runtime_root, item) for item in task_ids]
    tasks.sort(key=lambda item: (str(item.get("moved_at", "")), str(item.get("task_id", ""))), reverse=True)
    return {
        "schema_version": ARCHIVE_CATALOG_SCHEMA_VERSION,
        "generated_at": utc_now(),
        "runtime_root": str(resolved_runtime_root),
        "archive_root": str(_archive_root(resolved_runtime_root)),
        "archive_catalog_path": str(_archive_catalog_path(resolved_runtime_root)),
        "secondary_snapshots_root": str(_archive_snapshots_root(resolved_runtime_root)),
        "secondary_snapshot_count": sum(1 for item in tasks if item.get("secondary_snapshot_exists")),
        "task_count": len(tasks),
        "tasks": tasks,
    }


def sync_archive_catalog_snapshot(runtime_root: str | Path | None = None) -> dict[str, Any]:
    resolved_runtime_root = normalize_runtime_root(runtime_root)
    catalog = load_archive_catalog(resolved_runtime_root)
    archive_catalog_path = _archive_catalog_path(resolved_runtime_root)
    snapshots_root = _archive_snapshots_root(resolved_runtime_root)
    write_json(archive_catalog_path, catalog)
    snapshots_root.mkdir(parents=True, exist_ok=True)

    active_snapshot_names: set[str] = set()
    for task in catalog["tasks"]:
        task_id = str(task.get("task_id") or "").strip()
        if not task_id:
            continue
        snapshot_path = _archive_secondary_snapshot_path(resolved_runtime_root, task_id)
        write_json(snapshot_path, build_archive_secondary_snapshot(resolved_runtime_root, task_id))
        active_snapshot_names.add(snapshot_path.name)

    removed_stale_snapshot_paths: list[str] = []
    for snapshot_path in sorted(snapshots_root.glob("*.summary.json")):
        if snapshot_path.name in active_snapshot_names:
            continue
        snapshot_path.unlink()
        removed_stale_snapshot_paths.append(str(snapshot_path))

    return {
        "schema_version": ARCHIVE_CATALOG_SCHEMA_VERSION,
        "synced_at": utc_now(),
        "runtime_root": str(resolved_runtime_root),
        "archive_root": str(_archive_root(resolved_runtime_root)),
        "archive_catalog_path": str(archive_catalog_path),
        "secondary_snapshots_root": str(snapshots_root),
        "task_count": catalog["task_count"],
        "snapshot_count": len(active_snapshot_names),
        "removed_stale_snapshot_count": len(removed_stale_snapshot_paths),
        "removed_stale_snapshot_paths": removed_stale_snapshot_paths,
        "task_ids": [task["task_id"] for task in catalog["tasks"]],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="List archived commander runtime tasks and their archive manifests.")
    parser.add_argument("--runtime-root", default=None, help="Override runtime root. Defaults to .runtime/commander")
    parser.add_argument("--task-id", default=None, help="Return a single archived task")
    parser.add_argument("--sync", action="store_true", help="Persist archive catalog.json and compact secondary snapshots before returning")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    sync_summary = sync_archive_catalog_snapshot(args.runtime_root) if args.sync else None
    catalog = load_archive_catalog(args.runtime_root, task_id=args.task_id)
    if sync_summary is not None:
        catalog["archive_catalog_sync"] = sync_summary
    print(json.dumps(catalog, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
