from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from commander.transport.scripts.commander_harness import (
    CLOSURE_POLICIES,
    CLOSURE_POLICY_CLOSE_WHEN_VALIDATED,
    DISPATCH_KINDS,
    DISPATCH_KIND_FRESH,
    PACKET_SCHEMA_PATH,
    REPORT_SCHEMA_PATH,
    REPORT_STATUSES,
    build_worker_brief,
    build_worker_report_draft,
    load_schema,
    normalize_runtime_root,
    refresh_commander_task_catalog,
    refresh_status,
    resolve_task_paths,
    utc_now,
    validate_instance,
    write_json,
    append_event,
    load_events,
)
from commander.transport.scripts.commander_context_router import build_context_bundle
from commander.transport.scripts.commander_spec_kit import build_spec_ref
from commander.graph.adapters.worker_providers import validate_worker_dispatch_governance
from commander.graph.policies.lane_contract import (
    resolve_default_allowed_tools,
    resolve_worker_tool_profile_id,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a structured commander task packet."
    )
    parser.add_argument(
        "--runtime-root",
        default=None,
        help="Override runtime root. Defaults to .runtime/commander",
    )
    parser.add_argument("--task-id", required=True, help="Stable task identifier")
    parser.add_argument("--title", required=True, help="Task title")
    parser.add_argument("--goal", required=True, help="Task goal")
    parser.add_argument(
        "--must-read",
        action="append",
        default=[],
        help="Required file or context entry",
    )
    parser.add_argument("--bound", action="append", default=[], help="Task boundary")
    parser.add_argument(
        "--validation",
        action="append",
        default=[],
        help="Required validation command or check",
    )
    parser.add_argument(
        "--forbidden-path",
        action="append",
        default=[],
        help="Path that must not be touched",
    )
    parser.add_argument(
        "--owned-path",
        action="append",
        default=[],
        help="Write-set path owned by this task for safe parallel dispatch",
    )
    parser.add_argument(
        "--worker-profile",
        default="code-worker",
        help="Named warm worker profile for this task",
    )
    parser.add_argument(
        "--preferred-worker-profile",
        default=None,
        help="Preferred warm worker profile to reuse before falling back to worker-profile",
    )
    parser.add_argument(
        "--tool-profile",
        default="default",
        help="Named tool boundary profile for the worker",
    )
    parser.add_argument(
        "--allowed-tool",
        action="append",
        default=[],
        help="Explicitly allowed tool within the chosen profile",
    )
    parser.add_argument(
        "--no-reuse",
        action="store_true",
        help="Disable warm worker reuse for this dispatch",
    )
    parser.add_argument(
        "--dispatch-kind",
        choices=list(DISPATCH_KINDS),
        default=DISPATCH_KIND_FRESH,
        help="Why this task is being dispatched",
    )
    parser.add_argument(
        "--source-task-id",
        default=None,
        help="Task that directly triggered this dispatch",
    )
    parser.add_argument(
        "--parent-task-id",
        default=None,
        help="Parent task when this dispatch is a split child",
    )
    parser.add_argument(
        "--task-owner",
        default="commander",
        help="Logical owner for governance and follow-up routing",
    )
    parser.add_argument(
        "--closure-policy",
        choices=list(CLOSURE_POLICIES),
        default=CLOSURE_POLICY_CLOSE_WHEN_VALIDATED,
        help="Expected closure behavior once the worker report lands",
    )
    parser.add_argument(
        "--note", action="append", default=[], help="Optional note for the worker brief"
    )
    parser.add_argument(
        "--context-tag",
        action="append",
        default=[],
        help="Optional explicit context-routing tag",
    )
    parser.add_argument(
        "--spec-ref",
        action="append",
        default=[],
        help="Optional spec artifact path to attach to the packet",
    )
    parser.add_argument(
        "--provider-id",
        default=None,
        help="Optional worker provider id used to route a context bundle",
    )
    parser.add_argument(
        "--idempotency-key", default=None, help="Optional graph node idempotency key"
    )
    return parser.parse_args(argv)


def build_packet(args: argparse.Namespace) -> dict[str, object]:
    timestamp = utc_now()
    spec_refs = [build_spec_ref(spec_ref) for spec_ref in args.spec_ref]
    resolved_tool_profile = resolve_worker_tool_profile_id(
        worker_profile=args.worker_profile,
        requested_tool_profile=args.tool_profile,
        provider_default_tool_profile="default",
    )
    resolved_allowed_tools = resolve_default_allowed_tools(
        worker_profile=args.worker_profile,
        requested_allowed_tools=tuple(args.allowed_tool),
    )
    return {
        "schema_version": "commander-harness-v1",
        "task_id": args.task_id,
        "title": args.title,
        "goal": args.goal,
        "must_read": args.must_read,
        "bounds": args.bound,
        "validation": args.validation,
        "forbidden_paths": args.forbidden_path,
        "owned_paths": args.owned_path,
        "worker_profile": args.worker_profile,
        "preferred_worker_profile": args.preferred_worker_profile,
        "tool_profile": resolved_tool_profile,
        "allowed_tools": list(resolved_allowed_tools),
        "reuse_allowed": not args.no_reuse,
        "dispatch_kind": args.dispatch_kind,
        "source_task_id": args.source_task_id,
        "parent_task_id": args.parent_task_id,
        "task_owner": args.task_owner,
        "closure_policy": args.closure_policy,
        "context_tags": args.context_tag,
        "spec_refs": spec_refs,
        "report_contract": {
            "allowed_statuses": list(REPORT_STATUSES),
            "required_fields": [
                "task_id",
                "status",
                "summary",
                "changed_files",
                "verification",
                "commit",
                "risks",
                "recommended_next_step",
                "needs_commander_decision",
                "result_grade",
                "next_action_owner",
                "continuation_mode",
            ],
        },
        "status": "dispatched",
        "notes": args.note,
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def _has_idempotent_event(paths, event_type: str, idempotency_key: str | None) -> bool:
    if not idempotency_key:
        return False
    for event in load_events(paths.events_path):
        detail = event.get("detail") if isinstance(event.get("detail"), dict) else {}
        if (
            event.get("event_type") == event_type
            and detail.get("idempotency_key") == idempotency_key
        ):
            return True
    return False


def dispatch_task(
    runtime_root: str | Path | None,
    packet: dict[str, object],
    *,
    provider_id: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, object]:
    resolved_runtime_root = normalize_runtime_root(runtime_root)
    validate_instance(packet, load_schema(PACKET_SCHEMA_PATH))
    resolved_provider_id = _normalize_provider_id(provider_id)
    provider_governance: dict[str, object] | None = None
    if resolved_provider_id is not None:
        governance = validate_worker_dispatch_governance(
            packet,
            provider_id=resolved_provider_id,
        )
        provider_governance = governance.as_dict()

    task_id = str(packet["task_id"])
    paths = resolve_task_paths(resolved_runtime_root, task_id)
    write_json(paths.packet_path, packet)
    context_bundle = build_context_bundle(
        packet,
        provider_id=resolved_provider_id,
        runtime_artifact_paths={
            "packet": str(paths.packet_path),
            "resume_anchor": str(paths.resume_anchor_path),
            "checkpoint": str(paths.checkpoint_path),
            "worker_report": str(paths.worker_report_path),
        },
    )
    write_json(paths.context_bundle_path, context_bundle)
    paths.worker_brief_path.write_text(
        build_worker_brief(
            packet,
            context_bundle_path=paths.context_bundle_path,
            context_bundle=context_bundle,
            resume_anchor_path=paths.resume_anchor_path,
            checkpoint_path=paths.checkpoint_path,
        ),
        encoding="utf-8",
    )
    worker_report_created = False
    if not paths.worker_report_path.exists():
        worker_report_draft = build_worker_report_draft(task_id)
        validate_instance(worker_report_draft, load_schema(REPORT_SCHEMA_PATH))
        write_json(paths.worker_report_path, worker_report_draft)
        worker_report_created = True

    event_appended = False
    if not _has_idempotent_event(paths, "task_dispatched", idempotency_key):
        append_event(
            paths,
            "task_dispatched",
            {
                "title": packet["title"],
                "goal": packet["goal"],
                "worker_report_path": str(paths.worker_report_path),
                "worker_report_created": worker_report_created,
                "idempotency_key": idempotency_key,
            },
        )
        event_appended = True

    status = refresh_status(paths)
    refresh_commander_task_catalog(paths, event_type="task_dispatched")
    return {
        "task_id": task_id,
        "packet_path": str(paths.packet_path),
        "context_bundle_path": str(paths.context_bundle_path),
        "worker_brief_path": str(paths.worker_brief_path),
        "resume_anchor_path": str(paths.resume_anchor_path),
        "worker_report_path": str(paths.worker_report_path),
        "checkpoint_path": str(paths.checkpoint_path),
        "worker_report_created": worker_report_created,
        "event_appended": event_appended,
        "idempotency_key": idempotency_key,
        "status_path": str(paths.status_path),
        "runtime_root": str(resolved_runtime_root),
        "status": status,
        "provider_governance": provider_governance,
    }


def _normalize_provider_id(provider_id: str | None) -> str | None:
    if not isinstance(provider_id, str):
        return None
    normalized = provider_id.strip()
    return normalized or None


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    packet = build_packet(args)
    payload = dispatch_task(
        args.runtime_root,
        packet,
        provider_id=args.provider_id,
        idempotency_key=args.idempotency_key,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
