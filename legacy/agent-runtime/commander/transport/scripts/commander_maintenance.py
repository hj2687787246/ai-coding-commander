from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from commander.transport.scripts.commander_archive_catalog import sync_archive_catalog_snapshot
from commander.transport.scripts.commander_archive_cleanup import perform_archive_cleanup
from commander.transport.scripts.commander_audit import build_audit_report
from commander.transport.scripts.commander_cleanup_plan import build_cleanup_plan
from commander.transport.scripts.commander_harness import normalize_runtime_root, utc_now


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a single commander runtime maintenance cycle: archive sync, cleanup planning, optional cleanup apply, and audit."
    )
    parser.add_argument("--runtime-root", default=None, help="Override runtime root. Defaults to .runtime/commander")
    parser.add_argument("--task-card-path", default=None, help="Override current task card path for audit")
    parser.add_argument("--task-id", default=None, help="Limit cleanup planning/apply to a single task")
    parser.add_argument(
        "--skip-archive-sync",
        action="store_true",
        help="Skip archive catalog.json and secondary snapshot sync during this maintenance cycle",
    )
    parser.add_argument(
        "--apply-cleanup",
        action="store_true",
        help="Apply cleanup-eligible archive moves during this maintenance cycle",
    )
    return parser.parse_args(argv)


def _build_cycle_health(*, plan: dict[str, Any], audit: dict[str, Any]) -> str:
    if int(audit.get("warning_count") or 0) > 0:
        return "needs_attention"
    if int(plan.get("cleanup_candidate_count") or 0) > 0:
        return "cleanup_pending"
    return "healthy"


def _build_recommended_actions(*, plan: dict[str, Any], audit: dict[str, Any], applied_cleanup: bool) -> list[str]:
    actions: list[str] = []
    if int(audit.get("warning_count") or 0) > 0:
        actions.append("Inspect commander_audit warnings before trusting the runtime as fully healthy.")
    if int(plan.get("cleanup_candidate_count") or 0) > 0 and not applied_cleanup:
        actions.append("Run this maintenance cycle with --apply-cleanup after reviewing cleanup candidates.")
    if audit.get("warning_count") == 0 and plan.get("cleanup_candidate_count") == 0:
        actions.append("No immediate commander maintenance action is required.")
    return actions


def run_maintenance_cycle(
    runtime_root: str | Path | None = None,
    *,
    task_card_path: str | Path | None = None,
    task_id: str | None = None,
    sync_archive_catalog: bool,
    apply_cleanup: bool,
) -> dict[str, Any]:
    resolved_runtime_root = normalize_runtime_root(runtime_root)
    before_plan = build_cleanup_plan(resolved_runtime_root, task_id=task_id)
    before_audit = build_audit_report(resolved_runtime_root, task_card_path=task_card_path)

    archive_catalog_sync = None if not sync_archive_catalog else sync_archive_catalog_snapshot(resolved_runtime_root)
    cleanup_result = None
    if apply_cleanup:
        cleanup_result = perform_archive_cleanup(resolved_runtime_root, task_id=task_id, dry_run=False)

    after_plan = build_cleanup_plan(resolved_runtime_root, task_id=task_id)
    after_audit = build_audit_report(resolved_runtime_root, task_card_path=task_card_path)
    cycle_health = _build_cycle_health(plan=after_plan, audit=after_audit)

    return {
        "schema_version": "commander-maintenance-cycle-v1",
        "generated_at": utc_now(),
        "runtime_root": str(resolved_runtime_root),
        "task_id": task_id,
        "sync_archive_catalog": sync_archive_catalog,
        "apply_cleanup": apply_cleanup,
        "before": {
            "cleanup_plan": before_plan,
            "audit": before_audit,
        },
        "actions": {
            "archive_catalog_sync": archive_catalog_sync,
            "cleanup_apply_result": cleanup_result,
        },
        "after": {
            "cleanup_plan": after_plan,
            "audit": after_audit,
        },
        "cycle_health": cycle_health,
        "recommended_actions": _build_recommended_actions(
            plan=after_plan,
            audit=after_audit,
            applied_cleanup=apply_cleanup,
        ),
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = run_maintenance_cycle(
        args.runtime_root,
        task_card_path=args.task_card_path,
        task_id=args.task_id,
        sync_archive_catalog=not args.skip_archive_sync,
        apply_cleanup=args.apply_cleanup,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
