from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from api.db import upsert_commander_task_catalog_entries
from commander.transport.scripts.commander_task_catalog import load_task_catalog


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync file-backed commander task catalog entries into the primary database.")
    parser.add_argument("--runtime-root", default=None, help="Override runtime root. Defaults to .runtime/commander")
    parser.add_argument("--task-id", default=None, help="Sync a single task catalog entry")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    catalog = load_task_catalog(args.runtime_root, task_id=args.task_id)
    synced_count = upsert_commander_task_catalog_entries(catalog["tasks"])
    print(
        json.dumps(
            {
                "schema_version": catalog["schema_version"],
                "runtime_root": catalog["runtime_root"],
                "task_count": catalog["task_count"],
                "synced_count": synced_count,
                "task_ids": [item["task_id"] for item in catalog["tasks"]],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
