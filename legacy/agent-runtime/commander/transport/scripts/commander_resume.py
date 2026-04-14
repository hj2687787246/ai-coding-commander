from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from commander.transport.scripts.commander_harness import (
    build_resume_anchor as build_resume_anchor_from_paths,
    load_json,
    normalize_runtime_root,
    refresh_status,
    resolve_task_paths,
)


def _compact_path_map(paths: dict[str, Any]) -> dict[str, str]:
    if not isinstance(paths, dict):
        return {}
    keep = ("packet", "report", "checkpoint", "status", "events", "worker_report", "worker_brief")
    compact: dict[str, str] = {}
    for key in keep:
        value = paths.get(key)
        if isinstance(value, str) and value.strip():
            compact[key] = value
    return compact


def build_resume_anchor(checkpoint: dict[str, Any]) -> dict[str, Any]:
    recent_completion = checkpoint.get("recent_trusted_completion")
    if not isinstance(recent_completion, dict):
        recent_completion = None

    improvement_candidate = checkpoint.get("improvement_candidate")
    if not isinstance(improvement_candidate, dict):
        improvement_candidate = None

    worker_binding = checkpoint.get("worker_binding")
    if not isinstance(worker_binding, dict):
        worker_binding = None

    active_subagents_summary = checkpoint.get("active_subagents_summary")
    if not isinstance(active_subagents_summary, dict):
        active_subagents_summary = None

    catalog_refresh = checkpoint.get("catalog_refresh")
    if not isinstance(catalog_refresh, dict):
        catalog_refresh = None

    intent_binding = checkpoint.get("intent_binding")
    if not isinstance(intent_binding, dict):
        intent_binding = None

    context_budget = checkpoint.get("context_budget")
    if isinstance(context_budget, dict):
        context_budget = {
            "estimation_mode": context_budget.get("estimation_mode"),
            "round_budget_tokens": context_budget.get("round_budget_tokens"),
            "account_window_budget_tokens": context_budget.get(
                "account_window_budget_tokens"
            ),
            "open_now_estimated_tokens": context_budget.get(
                "open_now_estimated_tokens"
            ),
            "deferred_estimated_tokens": context_budget.get(
                "deferred_estimated_tokens"
            ),
            "full_expand_estimated_tokens": context_budget.get(
                "full_expand_estimated_tokens"
            ),
            "open_now_percent_of_round_budget": context_budget.get(
                "open_now_percent_of_round_budget"
            ),
            "full_expand_percent_of_round_budget": context_budget.get(
                "full_expand_percent_of_round_budget"
            ),
            "open_now_percent_of_account_window_budget": context_budget.get(
                "open_now_percent_of_account_window_budget"
            ),
            "full_expand_percent_of_account_window_budget": context_budget.get(
                "full_expand_percent_of_account_window_budget"
            ),
        }
    else:
        context_budget = None

    return {
        "schema_version": checkpoint.get("schema_version", "commander-harness-v1"),
        "task_id": checkpoint.get("task_id"),
        "title": checkpoint.get("title"),
        "current_phase": checkpoint.get("current_phase"),
        "lifecycle_status": checkpoint.get("lifecycle_status"),
        "worker_status": checkpoint.get("worker_status"),
        "controller_handoff": checkpoint.get("controller_handoff"),
        "conversation_stop_required": checkpoint.get("conversation_stop_required"),
        "conversation_stop_reason": checkpoint.get("conversation_stop_reason"),
        "recommended_action": checkpoint.get("recommended_action"),
        "next_minimal_action": checkpoint.get("next_minimal_action"),
        "result_grade": checkpoint.get("result_grade"),
        "next_action_owner": checkpoint.get("next_action_owner"),
        "continuation_mode": checkpoint.get("continuation_mode"),
        "decision_reason": checkpoint.get("decision_reason"),
        "last_open_offer": intent_binding.get("last_open_offer") if intent_binding else None,
        "pending_user_reply_target": (
            intent_binding.get("pending_user_reply_target") if intent_binding else None
        ),
        "offer_confirmed": bool(intent_binding.get("offer_confirmed")) if intent_binding else False,
        "latest_user_reply_text": (
            intent_binding.get("latest_user_reply_text") if intent_binding else None
        ),
        "intent_binding": intent_binding,
        "pending_decisions": checkpoint.get("pending_decisions") or [],
        "blockers": checkpoint.get("blockers") or [],
        "recent_trusted_completion": {
            "status": recent_completion.get("status"),
            "summary": recent_completion.get("summary"),
            "report_path": recent_completion.get("report_path"),
        }
        if recent_completion
        else None,
        "improvement_candidate": {
            "candidate_id": improvement_candidate.get("candidate_id"),
            "recommended_layer": improvement_candidate.get("recommended_layer"),
            "recommended_target": improvement_candidate.get("recommended_target"),
            "status": improvement_candidate.get("status"),
        }
        if improvement_candidate
        else None,
        "worker_binding": {
            "binding_health": worker_binding.get("binding_health"),
            "leased_worker_ids": worker_binding.get("leased_worker_ids") or [],
            "expired_leased_worker_ids": worker_binding.get("expired_leased_worker_ids") or [],
            "state_counts": worker_binding.get("state_counts") or {},
        }
        if worker_binding
        else None,
        "active_subagents_summary": active_subagents_summary,
        "catalog_refresh": {
            "status": catalog_refresh.get("status"),
            "reason": catalog_refresh.get("reason"),
            "failure_count": catalog_refresh.get("failure_count"),
        }
        if catalog_refresh
        else None,
        "context_budget": context_budget,
        "key_paths": _compact_path_map(checkpoint.get("key_paths")),
        "updated_at": checkpoint.get("updated_at"),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load a commander harness checkpoint for resume.")
    parser.add_argument("--runtime-root", default=None, help="Override runtime root. Defaults to .runtime/commander")
    parser.add_argument("--task-id", required=True, help="Stable task identifier")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--compact",
        action="store_true",
        help="Print the compact resume anchor (default).",
    )
    mode.add_argument(
        "--full-checkpoint",
        action="store_true",
        help="Return the full checkpoint payload instead of the compact resume anchor.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    runtime_root = normalize_runtime_root(args.runtime_root)
    paths = resolve_task_paths(runtime_root, args.task_id)

    refresh_status(paths)
    if args.full_checkpoint:
        payload = load_json(paths.checkpoint_path)
    else:
        payload = (
            load_json(paths.compaction_event_path)
            if paths.compaction_event_path.exists()
            else None
        )
        if not isinstance(payload, dict):
            payload = load_json(paths.resume_anchor_path) if paths.resume_anchor_path.exists() else None
        if not isinstance(payload, dict):
            checkpoint = load_json(paths.checkpoint_path)
            payload = build_resume_anchor_from_paths(paths, checkpoint)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
