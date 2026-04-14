from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from commander.transport.scripts.commander_harness import (
    DEFAULT_ARCHIVE_RETENTION_DAYS,
    is_cleanup_eligible,
    load_json,
    normalize_runtime_root,
    refresh_commander_task_catalog,
    refresh_status,
    resolve_task_paths,
    utc_now,
    write_json,
)
from commander.transport.scripts.commander_archive_catalog import sync_archive_catalog_snapshot
from commander.transport.scripts.commander_task_catalog import discover_task_ids


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Move cleanup-eligible archived commander tasks out of the live runtime.")
    parser.add_argument("--runtime-root", default=None, help="Override runtime root. Defaults to .runtime/commander")
    parser.add_argument("--task-id", default=None, help="Clean up a single archived task instead of all tasks")
    parser.add_argument("--dry-run", action="store_true", help="Report what would move without changing files")
    return parser.parse_args(argv)


def _archive_root(runtime_root: Path) -> Path:
    return runtime_root / "archive"


def _collect_improvement_action_dirs(runtime_root: Path, task_id: str) -> list[dict[str, str]]:
    actions_root = runtime_root / "improvement_actions"
    if not actions_root.exists():
        return []

    matches: list[dict[str, str]] = []
    for action_dir in sorted(path for path in actions_root.iterdir() if path.is_dir()):
        metadata_path = action_dir / "candidate_metadata.json"
        if not metadata_path.exists():
            continue
        try:
            metadata = load_json(metadata_path)
        except Exception:
            continue
        if not isinstance(metadata, dict) or metadata.get("task_id") != task_id:
            continue
        matches.append(
            {
                "candidate_id": str(metadata.get("candidate_id") or action_dir.name),
                "source_dir": str(action_dir),
                "destination_dir": str(_archive_root(runtime_root) / "improvement_actions" / action_dir.name),
            }
        )
    return matches


def _move_task(runtime_root: Path, task_id: str, *, dry_run: bool) -> dict[str, object]:
    paths = resolve_task_paths(runtime_root, task_id)
    status = refresh_status(paths)
    lifecycle = load_json(paths.lifecycle_path)
    cleanup_eligible = bool(status.get("cleanup_eligible")) or is_cleanup_eligible(lifecycle)
    archived_root = _archive_root(runtime_root)
    destination_task_dir = archived_root / "tasks" / task_id
    destination_candidate_path = archived_root / "improvements" / f"{task_id}.candidate.json"
    action_dirs = _collect_improvement_action_dirs(runtime_root, task_id)
    destination_action_dirs = [Path(item["destination_dir"]) for item in action_dirs]

    if status.get("lifecycle_status") != "archived":
        return {
            "task_id": task_id,
            "moved": False,
            "reason": "not_archived",
            "status": status,
        }
    if not cleanup_eligible:
        return {
            "task_id": task_id,
            "moved": False,
            "reason": "not_cleanup_eligible",
            "status": status,
        }
    if destination_task_dir.exists():
        return {
            "task_id": task_id,
            "moved": False,
            "reason": "archive_destination_exists",
            "destination_task_dir": str(destination_task_dir),
            "status": status,
        }
    if any(path.exists() for path in destination_action_dirs):
        return {
            "task_id": task_id,
            "moved": False,
            "reason": "archive_action_destination_exists",
            "destination_action_dirs": [str(path) for path in destination_action_dirs if path.exists()],
            "status": status,
        }

    refresh_commander_task_catalog(paths)
    manifest = {
        "task_id": task_id,
        "moved_at": utc_now(),
        "source_task_dir": str(paths.task_dir),
        "destination_task_dir": str(destination_task_dir),
        "source_candidate_path": str(paths.improvement_candidate_path) if paths.improvement_candidate_path.exists() else None,
        "destination_candidate_path": str(destination_candidate_path) if paths.improvement_candidate_path.exists() else None,
        "improvement_action_dirs": action_dirs,
        "lifecycle_status": status.get("lifecycle_status"),
        "archived_at": status.get("archived_at"),
        "cleanup_eligible": cleanup_eligible,
        "retention_policy": {
            "archive_retention_days": DEFAULT_ARCHIVE_RETENTION_DAYS,
            "cleanup_eligible": cleanup_eligible,
        },
    }
    if not dry_run:
        destination_task_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(paths.task_dir), str(destination_task_dir))
        if paths.improvement_candidate_path.exists():
            destination_candidate_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(paths.improvement_candidate_path), str(destination_candidate_path))
        for action_dir in action_dirs:
            source_dir = Path(action_dir["source_dir"])
            destination_dir = Path(action_dir["destination_dir"])
            destination_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source_dir), str(destination_dir))
        write_json(destination_task_dir / "archive_manifest.json", manifest)

    return {
        "task_id": task_id,
        "moved": True,
        "dry_run": dry_run,
        "destination_task_dir": str(destination_task_dir),
        "destination_candidate_path": str(destination_candidate_path) if paths.improvement_candidate_path.exists() else None,
        "destination_action_dirs": [item["destination_dir"] for item in action_dirs],
        "manifest": manifest,
    }


def perform_archive_cleanup(
    runtime_root: str | Path | None = None,
    *,
    task_id: str | None = None,
    dry_run: bool,
) -> dict[str, object]:
    resolved_runtime_root = normalize_runtime_root(runtime_root)
    task_ids = [task_id] if task_id else discover_task_ids(resolved_runtime_root)
    results = []
    for current_task_id in task_ids:
        try:
            results.append(_move_task(resolved_runtime_root, current_task_id, dry_run=dry_run))
        except Exception as exc:
            results.append(
                {
                    "task_id": current_task_id,
                    "moved": False,
                    "reason": "cleanup_error",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    archive_catalog_sync: dict[str, object] | None
    if dry_run:
        archive_catalog_sync = {
            "status": "skipped",
            "reason": "dry_run",
        }
    else:
        archive_catalog_sync = sync_archive_catalog_snapshot(resolved_runtime_root)

    return {
        "runtime_root": str(resolved_runtime_root),
        "archive_root": str(_archive_root(resolved_runtime_root)),
        "task_count": len(results),
        "moved_count": sum(1 for item in results if item.get("moved")),
        "dry_run": dry_run,
        "archive_catalog_sync": archive_catalog_sync,
        "tasks": results,
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    summary = perform_archive_cleanup(args.runtime_root, task_id=args.task_id, dry_run=args.dry_run)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
