from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from commander.transport.scripts.commander_harness import normalize_runtime_root, refresh_status, resolve_task_paths
from commander.transport.scripts.commander_host_runtime import build_host_runtime_summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Show commander harness task status.")
    parser.add_argument("--runtime-root", default=None, help="Override runtime root. Defaults to .runtime/commander")
    parser.add_argument("--task-id", help="Return a single task snapshot")
    return parser.parse_args(argv)


def build_context_route_summary(snapshot: dict[str, object]) -> dict[str, object] | None:
    context_budget = snapshot.get("context_budget")
    if not isinstance(context_budget, dict):
        return None
    entries_deferred_by_budget = context_budget.get("entries_deferred_by_budget")
    if isinstance(entries_deferred_by_budget, list):
        normalized_entries = [
            str(item)
            for item in entries_deferred_by_budget
            if isinstance(item, str) and item.strip()
        ]
    else:
        normalized_entries = []
    return {
        "router_budget_overflow": bool(context_budget.get("router_budget_overflow")),
        "entries_deferred_by_budget": normalized_entries,
        "deferred_by_budget_count": len(normalized_entries),
        "router_open_now_estimated_tokens": context_budget.get(
            "router_open_now_estimated_tokens"
        ),
        "router_deferred_estimated_tokens": context_budget.get(
            "router_deferred_estimated_tokens"
        ),
        "open_now_percent_of_round_budget": context_budget.get(
            "open_now_percent_of_round_budget"
        ),
        "full_expand_percent_of_round_budget": context_budget.get(
            "full_expand_percent_of_round_budget"
        ),
    }


def enrich_status_snapshot(snapshot: dict[str, object]) -> dict[str, object]:
    context_route_summary = build_context_route_summary(snapshot)
    if context_route_summary is None:
        return snapshot
    return {
        **snapshot,
        "context_route_summary": context_route_summary,
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    runtime_root = normalize_runtime_root(args.runtime_root)

    if args.task_id:
        snapshot = enrich_status_snapshot(
            refresh_status(resolve_task_paths(runtime_root, args.task_id))
        )
        print(
            json.dumps(
                {
                    **snapshot,
                    "host_runtime": build_host_runtime_summary(
                        runtime_root, task_id=args.task_id
                    ),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    tasks_root = runtime_root / "tasks"
    if not tasks_root.exists():
        print(
            json.dumps(
                {
                    "host_runtime": build_host_runtime_summary(runtime_root),
                    "tasks": [],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    tasks = []
    for task_dir in sorted(path for path in tasks_root.iterdir() if path.is_dir()):
        tasks.append(
            enrich_status_snapshot(
                refresh_status(resolve_task_paths(runtime_root, task_dir.name))
            )
        )
    print(
        json.dumps(
            {
                "host_runtime": build_host_runtime_summary(runtime_root),
                "tasks": tasks,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
