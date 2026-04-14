from __future__ import annotations

from pathlib import Path
from typing import Any

from commander.transport.scripts.commander_harness import (
    describe_token_artifact_from_path,
    load_schema,
    resolve_context_budget_tokens,
    utc_now,
    validate_instance,
)
from commander.transport.scripts.commander_spec_kit import (
    collect_spec_artifact_paths,
)


COMMANDER_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = COMMANDER_ROOT.parent
CONTEXT_BUNDLE_SCHEMA_PATH = (
    COMMANDER_ROOT / "transport" / "schemas" / "commander_context_bundle.schema.json"
)

CONTEXT_REGISTRY: tuple[dict[str, Any], ...] = (
    {
        "context_id": "commander_rules",
        "title": "Commander role and lazy-loading rules",
        "category": "rules",
        "always": True,
        "tags": [],
        "paths": [PROJECT_ROOT / "commander" / "core" / "任命.md"],
        "deferred_paths": [],
        "disclosure_mode": "always_open",
        "summary_lines": [
            "Establishes commander identity, hard rules, and lazy-loading map.",
            "Use this as the first truth source before expanding phase-specific docs.",
        ],
        "when_to_open": [
            "Open at the start of every commander recovery or fresh handoff.",
        ],
    },
    {
        "context_id": "current_task_card",
        "title": "Current active objective and progress truth source",
        "category": "state",
        "always": True,
        "tags": [],
        "paths": [PROJECT_ROOT / "commander" / "state" / "当前任务卡.md"],
        "deferred_paths": [],
        "disclosure_mode": "always_open",
        "summary_lines": [
            "Contains the active phase, current slice, recovery anchors, and blockers.",
            "Prefer this over replaying full timeline history.",
        ],
        "when_to_open": [
            "Open during every recovery and before changing the current phase slice.",
        ],
    },
    {
        "context_id": "langgraph_runtime",
        "title": "LangGraph runtime design and orchestration contracts",
        "category": "project",
        "always": False,
        "tags": [
            "langgraph-runtime",
            "worker-orchestration",
            "host-runtime",
        ],
        "paths": [PROJECT_ROOT / "commander" / "graph" / "README.md"],
        "deferred_paths": [
            PROJECT_ROOT / "commander" / "outer" / "指挥官LangGraph运行时项目化方案.md",
        ],
        "disclosure_mode": "metadata_first",
        "summary_lines": [
            "Graph README gives the runtime topology and active node contracts.",
            "Projectization plan is deeper background; defer it unless the task touches phase/runtime design.",
        ],
        "when_to_open": [
            "Open deferred paths only when the task changes graph topology, phase planning, or host-runtime architecture.",
        ],
    },
    {
        "context_id": "execution_workbench",
        "title": "Execution workbench and external worker conventions",
        "category": "project",
        "always": False,
        "tags": [
            "external-window",
            "worker-orchestration",
            "host-runtime",
        ],
        "paths": [PROJECT_ROOT / "commander" / "outer" / "agent_workbench.md"],
        "deferred_paths": [
            PROJECT_ROOT
            / "commander"
            / "transport"
            / "prompts"
            / "execution_window_task_template.md",
        ],
        "disclosure_mode": "metadata_first",
        "summary_lines": [
            "Workbench doc explains external worker boundaries and operating norms.",
            "Task template is only needed when changing the worker-facing prompt contract.",
        ],
        "when_to_open": [
            "Open deferred paths only when editing external worker prompts or handoff protocol.",
        ],
    },
    {
        "context_id": "repo_runbook",
        "title": "Repo runbook and validation commands",
        "category": "project",
        "always": False,
        "tags": [
            "validation",
            "testing",
            "build",
        ],
        "paths": [PROJECT_ROOT / "docs" / "runbook.md"],
        "deferred_paths": [],
        "disclosure_mode": "metadata_first",
        "summary_lines": [
            "Runbook centralizes standard validation and failure-handling commands.",
        ],
        "when_to_open": [
            "Open when the current slice changes validation steps or runbook-facing behavior.",
        ],
    },
    {
        "context_id": "memory_index",
        "title": "Commander memory retrieval and recurrence boundaries",
        "category": "project",
        "always": False,
        "tags": [
            "memory",
            "validation",
        ],
        "paths": [PROJECT_ROOT / "commander" / "outer" / "指挥官记忆检索说明.md"],
        "deferred_paths": [
            PROJECT_ROOT / "commander" / "state" / "问题索引.md",
            PROJECT_ROOT / "docs" / "复用问题沉淀与Skill升级协议.md",
        ],
        "disclosure_mode": "metadata_first",
        "summary_lines": [
            "Explains when to retrieve from commander memory versus reading repo truth sources.",
            "Problem index and reuse-upgrade protocol are deeper references for repeated issues.",
        ],
        "when_to_open": [
            "Open deferred paths only when the task is a recurring confusion, memory retrieval issue, or reuse-upgrade decision.",
        ],
    },
    {
        "context_id": "procedural_memory",
        "title": "Reusable scripts and skill shells",
        "category": "project",
        "always": False,
        "tags": [
            "memory",
            "skill-candidate",
        ],
        "paths": [PROJECT_ROOT / "commander" / "skill-source" / "README.md"],
        "deferred_paths": [
            PROJECT_ROOT / "commander" / "transport" / "scripts" / "commander_memory_search.py",
            PROJECT_ROOT / "commander" / "transport" / "scripts" / "commander_memory_index.py",
            PROJECT_ROOT / "commander" / "skill-source" / "commander-mode" / "SKILL.md",
            PROJECT_ROOT / "commander" / "skill-source" / "commander-reuse-upgrader" / "SKILL.md",
        ],
        "disclosure_mode": "metadata_first",
        "summary_lines": [
            "Skill-source README is the index; actual skill files and memory scripts are heavy procedural references.",
            "Expand only when the slice changes memory tooling or skill behavior.",
        ],
        "when_to_open": [
            "Open deferred paths only when editing skill contracts, memory indexing, or retrieval scripts.",
        ],
    },
    {
        "context_id": "intent_binding",
        "title": "Chat entry alignment and recurring intent-binding issues",
        "category": "state",
        "always": False,
        "tags": [
            "intent-binding",
            "chat-entry",
        ],
        "paths": [PROJECT_ROOT / "commander" / "state" / "问题索引.md"],
        "deferred_paths": [],
        "disclosure_mode": "metadata_first",
        "summary_lines": [
            "Problem index records recurring chat-entry and intent-binding failures.",
        ],
        "when_to_open": [
            "Open when the slice touches reply binding, user confirmation, or chat-entry routing.",
        ],
    },
)

TAG_KEYWORDS: dict[str, tuple[str, ...]] = {
    "langgraph-runtime": (
        "langgraph",
        "graph",
        "runtime",
        "objective",
        "phase",
        "resume",
        "poll",
        "checkpoint",
    ),
    "worker-orchestration": (
        "worker",
        "dispatch",
        "ingest",
        "lease",
        "provider",
        "ownership",
        "派发",
        "回收",
    ),
    "host-runtime": (
        "host",
        "adapter",
        "external",
        "window",
        "codex",
        "claude",
        "qwen",
        "doubao",
        "窗口",
        "宿主",
    ),
    "validation": (
        "validation",
        "verify",
        "pytest",
        "ruff",
        "build",
        "test",
        "lint",
        "self_check",
    ),
    "intent-binding": (
        "intent",
        "binding",
        "chat",
        "reply",
        "handoff",
        "confirm",
        "聊天",
        "短确认",
    ),
}

PRIORITY_WEIGHTS: dict[str, int] = {
    "critical": 400,
    "high": 300,
    "normal": 200,
    "low": 100,
}


def build_context_bundle(
    task_packet: dict[str, Any],
    *,
    provider_id: str | None = None,
    runtime_artifact_paths: dict[str, str] | None = None,
) -> dict[str, Any]:
    task_id = str(task_packet.get("task_id") or "").strip()
    selected_tags = infer_context_tags(task_packet, provider_id=provider_id)
    entries = _select_registry_entries(selected_tags)
    packet_paths = _collect_packet_must_read_paths(task_packet)
    if packet_paths:
        entries.append(
            {
                "context_id": "packet_must_read",
                "title": "Task packet explicit must-read files",
                "category": "task",
                "reason": "These files were explicitly requested by the task packet.",
                "disclosure_mode": "always_open",
                "summary_lines": [
                    "These files are explicitly required by packet.must_read for the current slice.",
                ],
                "when_to_open": [
                    "Open these paths in the current task before implementation or validation.",
                ],
                "paths": packet_paths,
                "deferred_paths": [],
            }
        )
    spec_artifact_paths = _collect_spec_artifact_paths(task_packet)
    if spec_artifact_paths:
        entries.append(
            {
                "context_id": "spec_artifacts",
                "title": "Task packet spec artifacts",
                "category": "spec",
                "reason": "These spec artifacts were explicitly attached to the task packet.",
                "disclosure_mode": "always_open",
                "summary_lines": [
                    "These spec artifacts are attached to the packet and are part of the current task contract.",
                ],
                "when_to_open": [
                    "Open when the implementation or validation depends on the attached spec.",
                ],
                "paths": spec_artifact_paths,
                "deferred_paths": [],
            }
        )
    runtime_immediate_paths = _collect_runtime_artifact_paths(
        runtime_artifact_paths,
        keys=("packet", "resume_anchor"),
    )
    runtime_deferred_paths = _collect_runtime_artifact_paths(
        runtime_artifact_paths,
        keys=("checkpoint", "worker_report"),
    )
    if runtime_immediate_paths or runtime_deferred_paths:
        entries.append(
            {
                "context_id": "runtime_artifacts",
                "title": "Task-local runtime artifacts",
                "category": "runtime",
                "reason": "These are the task-local truth sources for this dispatch.",
                "disclosure_mode": "metadata_first",
                "summary_lines": [
                    "Use the compact resume anchor before opening deeper runtime artifacts.",
                    "checkpoint.json is a deep-state fallback; worker_report.json is for result handoff, not initial reading.",
                ],
                "when_to_open": [
                    "Open deferred runtime artifacts only when recovering from interruption or validating task-local state transitions.",
                ],
                "paths": runtime_immediate_paths,
                "deferred_paths": runtime_deferred_paths,
            }
        )
    entries, budget_summary = _apply_budget_aware_routing(entries)
    payload = {
        "schema_version": "commander-context-bundle-v1",
        "task_id": task_id,
        "provider_id": provider_id,
        "selected_tags": selected_tags,
        "read_policy": build_context_read_policy(budget_summary=budget_summary),
        "entries": entries,
        "generated_at": utc_now(),
    }
    validate_instance(payload, load_schema(CONTEXT_BUNDLE_SCHEMA_PATH))
    return payload


def build_context_read_policy(
    *,
    budget_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    policy: dict[str, Any] = {
        "mode": "progressive_disclosure",
        "default_behavior": (
            "Review summary_lines and paths first; open deferred_paths only when "
            "packet.must_read, validation, blocker analysis, or the current phase "
            "slice requires deeper detail."
        ),
        "compact_resume_first": True,
        "open_checkpoint_only_when_needed": True,
        "recommended_sequence": [
            "worker_brief",
            "packet",
            "context_bundle",
            "resume_anchor",
            "checkpoint",
        ],
    }
    if isinstance(budget_summary, dict):
        policy.update(
            {
                "round_budget_tokens": budget_summary["round_budget_tokens"],
                "router_open_now_estimated_tokens": budget_summary[
                    "router_open_now_estimated_tokens"
                ],
                "router_deferred_estimated_tokens": budget_summary[
                    "router_deferred_estimated_tokens"
                ],
                "router_full_expand_estimated_tokens": budget_summary[
                    "router_full_expand_estimated_tokens"
                ],
                "router_budget_enforced": True,
                "router_budget_overflow": budget_summary["router_budget_overflow"],
                "deferred_by_budget_context_ids": budget_summary[
                    "deferred_by_budget_context_ids"
                ],
            }
        )
    return policy


def infer_context_tags(
    task_packet: dict[str, Any],
    *,
    provider_id: str | None = None,
) -> list[str]:
    tags: set[str] = set()
    explicit_tags = task_packet.get("context_tags")
    if isinstance(explicit_tags, list):
        tags.update(
            item.strip().lower()
            for item in explicit_tags
            if isinstance(item, str) and item.strip()
        )
    text = _collect_packet_text(task_packet)
    for tag, keywords in TAG_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            tags.add(tag)
    normalized_provider_id = (provider_id or "").strip().lower()
    if normalized_provider_id and normalized_provider_id != "local-script":
        tags.add("external-window")
    return sorted(tags)


def _collect_packet_text(task_packet: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("task_id", "title", "goal"):
        value = task_packet.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip().lower())
    for key in ("must_read", "bounds", "validation", "forbidden_paths", "notes"):
        value = task_packet.get(key)
        if isinstance(value, list):
            parts.extend(
                item.strip().lower()
                for item in value
                if isinstance(item, str) and item.strip()
            )
    provider_input = task_packet.get("provider_input")
    if isinstance(provider_input, dict):
        for value in provider_input.values():
            if isinstance(value, str) and value.strip():
                parts.append(value.strip().lower())
            elif isinstance(value, list):
                parts.extend(
                    item.strip().lower()
                    for item in value
                    if isinstance(item, str) and item.strip()
                )
    return " ".join(parts)


def _select_registry_entries(selected_tags: list[str]) -> list[dict[str, Any]]:
    tag_set = set(selected_tags)
    entries: list[dict[str, Any]] = []
    for entry in CONTEXT_REGISTRY:
        always = bool(entry.get("always"))
        entry_tags = set(entry.get("tags", []))
        if not always and not (entry_tags & tag_set):
            continue
        reason = (
            "Always include this truth source for every routed worker task."
            if always
            else f"Matched context tags: {', '.join(sorted(entry_tags & tag_set))}"
        )
        entries.append(
            {
                "context_id": str(entry["context_id"]),
                "title": str(entry["title"]),
                "category": str(entry["category"]),
                "reason": reason,
                "disclosure_mode": str(entry.get("disclosure_mode") or "metadata_first"),
                "summary_lines": [
                    str(item)
                    for item in entry.get("summary_lines", [])
                    if isinstance(item, str) and item.strip()
                ],
                "when_to_open": [
                    str(item)
                    for item in entry.get("when_to_open", [])
                    if isinstance(item, str) and item.strip()
                ],
                "paths": [str(Path(path)) for path in entry["paths"]],
                "deferred_paths": [
                    str(Path(path))
                    for path in entry.get("deferred_paths", [])
                ],
                "priority": _entry_priority(
                    context_id=str(entry["context_id"]),
                    category=str(entry["category"]),
                    disclosure_mode=str(
                        entry.get("disclosure_mode") or "metadata_first"
                    ),
                    always=always,
                ),
                "budget_behavior": _entry_budget_behavior(
                    context_id=str(entry["context_id"]),
                    disclosure_mode=str(
                        entry.get("disclosure_mode") or "metadata_first"
                    ),
                    always=always,
                ),
            }
        )
    return entries


def _entry_priority(
    *,
    context_id: str,
    category: str,
    disclosure_mode: str,
    always: bool,
) -> str:
    if always or disclosure_mode == "always_open":
        return "critical"
    if category in {"runtime", "task", "spec"}:
        return "critical"
    if context_id in {"langgraph_runtime", "execution_workbench", "repo_runbook"}:
        return "high"
    if category == "state":
        return "normal"
    return "low"


def _entry_budget_behavior(
    *,
    context_id: str,
    disclosure_mode: str,
    always: bool,
) -> str:
    if always or disclosure_mode == "always_open":
        return "pinned_open"
    if context_id in {"packet_must_read", "spec_artifacts", "runtime_artifacts"}:
        return "pinned_open"
    return "defer_if_needed"


def _estimate_paths_tokens(paths: list[str]) -> int:
    return sum(
        int(
            describe_token_artifact_from_path(
                path,
                kind="context_bundle_path",
            ).get("estimated_tokens")
            or 0
        )
        for path in paths
    )


def _apply_budget_aware_routing(
    entries: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    round_budget_tokens, _ = resolve_context_budget_tokens()
    normalized_entries: list[dict[str, Any]] = []
    for entry in entries:
        normalized = dict(entry)
        context_id = str(normalized.get("context_id") or "")
        category = str(normalized.get("category") or "")
        disclosure_mode = str(normalized.get("disclosure_mode") or "metadata_first")
        open_paths = [
            str(path).strip()
            for path in normalized.get("paths", [])
            if isinstance(path, str) and str(path).strip()
        ]
        deferred_paths = [
            str(path).strip()
            for path in normalized.get("deferred_paths", [])
            if isinstance(path, str) and str(path).strip()
        ]
        priority = str(
            normalized.get("priority")
            or _entry_priority(
                context_id=context_id,
                category=category,
                disclosure_mode=disclosure_mode,
                always=False,
            )
        )
        if priority not in PRIORITY_WEIGHTS:
            priority = "normal"
        budget_behavior = str(
            normalized.get("budget_behavior")
            or _entry_budget_behavior(
                context_id=context_id,
                disclosure_mode=disclosure_mode,
                always=False,
            )
        )
        if budget_behavior not in {"pinned_open", "defer_if_needed"}:
            budget_behavior = "defer_if_needed"
        normalized["paths"] = open_paths
        normalized["deferred_paths"] = deferred_paths
        normalized["priority"] = priority
        normalized["budget_behavior"] = budget_behavior
        normalized["estimated_open_tokens"] = _estimate_paths_tokens(open_paths)
        normalized["estimated_deferred_tokens"] = _estimate_paths_tokens(deferred_paths)
        normalized["budget_action"] = (
            "pinned_open" if budget_behavior == "pinned_open" else "kept_open"
        )
        normalized["budget_reason"] = (
            "Always-open entry kept in the first read pass."
            if budget_behavior == "pinned_open"
            else "Kept open for the first read pass within the current router budget."
        )
        normalized_entries.append(normalized)

    router_open_now_estimated_tokens = sum(
        int(entry.get("estimated_open_tokens") or 0) for entry in normalized_entries
    )
    deferred_by_budget: list[dict[str, Any]] = []
    candidates = sorted(
        (
            entry
            for entry in normalized_entries
            if entry.get("budget_behavior") == "defer_if_needed" and entry.get("paths")
        ),
        key=lambda entry: (
            PRIORITY_WEIGHTS.get(str(entry.get("priority") or "normal"), 200),
            -int(entry.get("estimated_open_tokens") or 0),
            str(entry.get("context_id") or ""),
        ),
    )
    for entry in candidates:
        if router_open_now_estimated_tokens <= round_budget_tokens:
            break
        moved_paths = list(entry["paths"])
        if not moved_paths:
            continue
        moved_tokens = int(entry.get("estimated_open_tokens") or 0)
        entry["paths"] = []
        entry["deferred_paths"] = [*moved_paths, *entry["deferred_paths"]]
        entry["estimated_open_tokens"] = 0
        entry["estimated_deferred_tokens"] = int(
            entry.get("estimated_deferred_tokens") or 0
        ) + moved_tokens
        entry["budget_action"] = "deferred_by_budget"
        entry["budget_reason"] = (
            f"Moved {len(moved_paths)} open path(s) into deferred_paths because the "
            f"router open-now estimate exceeded the round budget of {round_budget_tokens} tokens."
        )
        router_open_now_estimated_tokens = max(
            router_open_now_estimated_tokens - moved_tokens, 0
        )
        deferred_by_budget.append(
            {
                "context_id": entry["context_id"],
                "title": entry["title"],
                "priority": entry["priority"],
                "moved_path_count": len(moved_paths),
                "estimated_tokens": moved_tokens,
            }
        )

    router_deferred_estimated_tokens = sum(
        int(entry.get("estimated_deferred_tokens") or 0) for entry in normalized_entries
    )
    return normalized_entries, {
        "round_budget_tokens": round_budget_tokens,
        "router_open_now_estimated_tokens": router_open_now_estimated_tokens,
        "router_deferred_estimated_tokens": router_deferred_estimated_tokens,
        "router_full_expand_estimated_tokens": (
            router_open_now_estimated_tokens + router_deferred_estimated_tokens
        ),
        "router_budget_overflow": router_open_now_estimated_tokens
        > round_budget_tokens,
        "deferred_by_budget_context_ids": [
            str(entry["context_id"]) for entry in deferred_by_budget
        ],
        "entries_deferred_by_budget": deferred_by_budget,
    }


def _collect_packet_must_read_paths(task_packet: dict[str, Any]) -> list[str]:
    must_read = task_packet.get("must_read")
    if not isinstance(must_read, list):
        return []
    paths: list[str] = []
    for item in must_read:
        if not isinstance(item, str) or not item.strip():
            continue
        path = _resolve_repo_path(item.strip())
        if path is not None:
            paths.append(str(path))
    return sorted(dict.fromkeys(paths))


def _collect_spec_artifact_paths(task_packet: dict[str, Any]) -> list[str]:
    spec_refs = task_packet.get("spec_refs")
    if not isinstance(spec_refs, list) or not spec_refs:
        return []
    return collect_spec_artifact_paths(spec_refs)


def _collect_runtime_artifact_paths(
    runtime_artifact_paths: dict[str, str] | None,
    *,
    keys: tuple[str, ...] | None = None,
) -> list[str]:
    if not isinstance(runtime_artifact_paths, dict):
        return []
    if keys is None:
        selected_values = runtime_artifact_paths.values()
    else:
        selected_values = (
            runtime_artifact_paths.get(key)
            for key in keys
        )
    paths = [
        value.strip()
        for value in selected_values
        if isinstance(value, str) and value.strip()
    ]
    return sorted(dict.fromkeys(paths))


def _resolve_repo_path(value: str) -> Path | None:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    if candidate.suffix.lower() not in {".md", ".py", ".json", ".ps1", ".yml", ".yaml"}:
        return None
    return (PROJECT_ROOT / candidate).resolve()
