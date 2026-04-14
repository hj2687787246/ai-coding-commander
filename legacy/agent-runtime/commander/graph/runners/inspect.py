from __future__ import annotations

import argparse
import json

from commander.graph.runners.run_once import run_once


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect the commander graph's current routing decision."
    )
    parser.add_argument("--thread-id", default=None, help="Stable LangGraph thread id")
    parser.add_argument("--runtime-root", default=None, help="Override runtime root")
    parser.add_argument(
        "--task-card-path", default=None, help="Override current task card path"
    )
    parser.add_argument("--task-id", default=None, help="Optional runtime task id")
    parser.add_argument(
        "--checkpoint-db", default=None, help="Override graph checkpoint SQLite path"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    state = run_once(
        thread_id=args.thread_id,
        runtime_root=args.runtime_root,
        task_card_path=args.task_card_path,
        task_id=args.task_id,
        checkpoint_db=args.checkpoint_db,
    )
    stop_gate = (
        state.get("stop_gate_report")
        if isinstance(state.get("stop_gate_report"), dict)
        else {}
    )
    audit = (
        state.get("audit_report") if isinstance(state.get("audit_report"), dict) else {}
    )
    payload = {
        "thread_id": state.get("thread_id"),
        "route": state.get("route"),
        "stop_allowed": state.get("stop_allowed"),
        "continuation_required": state.get("continuation_required"),
        "continuation_mode": state.get("continuation_mode"),
        "stop_gate_outcome": stop_gate.get("outcome"),
        "warning_count": audit.get("warning_count"),
        "next_actions": state.get("next_actions", []),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
