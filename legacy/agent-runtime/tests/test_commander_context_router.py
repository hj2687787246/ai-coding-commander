from __future__ import annotations

from pathlib import Path

from commander.transport.scripts.commander_context_router import (
    CONTEXT_BUNDLE_SCHEMA_PATH,
    build_context_bundle,
)
from commander.transport.scripts.commander_harness import load_schema, validate_instance


def test_context_router_builds_bundle_from_explicit_tags() -> None:
    packet = {
        "task_id": "host-runtime-context-task",
        "title": "Host runtime integration",
        "goal": "Integrate external worker host wait and intent binding routing.",
        "must_read": [
            "commander/graph/README.md",
            "commander/outer/agent_workbench.md",
        ],
        "bounds": ["commander runtime only"],
        "validation": ["python -m pytest -q tests/test_commander_context_router.py"],
        "forbidden_paths": ["config/rag.yml"],
        "context_tags": ["host-runtime", "intent-binding"],
    }

    payload = build_context_bundle(
        packet,
        provider_id="codex",
        runtime_artifact_paths={
            "packet": str(Path("D:/runtime/tasks/host-runtime-context-task/packet.json")),
            "resume_anchor": str(Path("D:/runtime/tasks/host-runtime-context-task/resume_anchor.json")),
        },
    )

    validate_instance(payload, load_schema(CONTEXT_BUNDLE_SCHEMA_PATH))
    context_ids = {entry["context_id"] for entry in payload["entries"]}

    assert "commander_rules" in context_ids
    assert "current_task_card" in context_ids
    assert "langgraph_runtime" in context_ids
    assert "execution_workbench" in context_ids
    assert "intent_binding" in context_ids
    assert "runtime_artifacts" in context_ids
    assert "packet_must_read" in context_ids
    assert "external-window" in payload["selected_tags"]
    assert "host-runtime" in payload["selected_tags"]
    assert "intent-binding" in payload["selected_tags"]


def test_context_router_includes_memory_and_procedural_entries() -> None:
    packet = {
        "task_id": "memory-index-task",
        "title": "Memory index",
        "goal": "Build a three-layer memory index for commander tasks.",
        "must_read": [
            "commander/outer/指挥官记忆检索说明.md",
            "commander/state/问题索引.md",
        ],
        "bounds": ["commander runtime only"],
        "validation": ["python -m pytest -q tests/test_commander_memory_search.py"],
        "forbidden_paths": ["config/rag.yml"],
        "context_tags": ["memory", "skill-candidate"],
    }

    payload = build_context_bundle(packet, provider_id="codex")
    validate_instance(payload, load_schema(CONTEXT_BUNDLE_SCHEMA_PATH))
    context_ids = {entry["context_id"] for entry in payload["entries"]}

    assert "memory_index" in context_ids
    assert "procedural_memory" in context_ids
    assert "memory" in payload["selected_tags"]
    assert "skill-candidate" in payload["selected_tags"]
