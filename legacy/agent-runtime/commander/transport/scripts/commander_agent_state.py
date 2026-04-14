from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from commander.transport.scripts.commander_harness import (
    ACTIVE_SUBAGENT_CLOSED,
    ACTIVE_SUBAGENT_COMPLETED_WAITING_CLOSE,
    ACTIVE_SUBAGENT_BLOCKED,
    ACTIVE_SUBAGENT_RUNNING,
    normalize_active_subagent_update,
    load_json,
    normalize_runtime_root,
    refresh_status,
    resolve_task_paths,
    set_active_subagent_state,
)


def _load_json_payload(value: str) -> object:
    candidate_path = Path(value)
    if candidate_path.exists():
        return load_json(candidate_path)
    return json.loads(value)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update a commander sub-agent state.")
    parser.add_argument("--runtime-root", default=None, help="Override runtime root. Defaults to .runtime/commander")
    parser.add_argument("--task-id", required=True, help="Stable task identifier")
    parser.add_argument("--agent-id", default=None, help="Stable sub-agent identifier")
    parser.add_argument("--nickname", default=None, help="Human-friendly sub-agent nickname")
    parser.add_argument(
        "--state",
        default=None,
        choices=[
            ACTIVE_SUBAGENT_RUNNING,
            ACTIVE_SUBAGENT_COMPLETED_WAITING_CLOSE,
            ACTIVE_SUBAGENT_BLOCKED,
            ACTIVE_SUBAGENT_CLOSED,
        ],
        help="Sub-agent lifecycle state",
    )
    parser.add_argument(
        "--notification-json",
        default=None,
        help="Raw notification, wait_agent status, or spawn payload JSON, or a path to a JSON file",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    runtime_root = normalize_runtime_root(args.runtime_root)
    paths = resolve_task_paths(runtime_root, args.task_id)

    resolved_agent_id = args.agent_id
    resolved_nickname = args.nickname
    resolved_state = args.state
    payload = None
    if args.notification_json is not None:
        payload = _load_json_payload(args.notification_json)
    if payload is not None:
        normalized = normalize_active_subagent_update(
            payload,
            fallback_task_id=args.task_id,
            fallback_agent_id=args.agent_id,
            fallback_nickname=args.nickname,
            default_state=args.state,
        )
        if normalized is not None:
            resolved_agent_id = normalized["agent_id"]
            resolved_nickname = normalized["nickname"]
            resolved_state = args.state or normalized["state"]
        if resolved_agent_id is None or resolved_state is None:
            raise SystemExit("--notification-json must resolve an agent_id and state")
        set_active_subagent_state(
            paths,
            agent_id=resolved_agent_id,
            nickname=resolved_nickname,
            state=resolved_state,
        )
    else:
        if resolved_agent_id is None or resolved_state is None:
            raise SystemExit("--agent-id and --state are required without --notification-json")
        set_active_subagent_state(
            paths,
            agent_id=resolved_agent_id,
            nickname=resolved_nickname,
            state=resolved_state,
        )
    refresh_status(paths)
    checkpoint = load_json(paths.checkpoint_path)
    print(
        json.dumps(
            {
                "task_id": args.task_id,
                "agent_id": resolved_agent_id,
                "state": resolved_state,
                "checkpoint_path": str(paths.checkpoint_path),
                "status_path": str(paths.status_path),
                "active_subagents": checkpoint.get("active_subagents", []) if isinstance(checkpoint, dict) else [],
                "active_subagents_summary": (
                    checkpoint.get("active_subagents_summary", {}) if isinstance(checkpoint, dict) else {}
                ),
                "status": load_json(paths.status_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
