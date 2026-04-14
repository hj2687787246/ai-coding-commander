from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from commander.transport.scripts.commander_harness import (
    PROJECT_ROOT,
    load_schema,
    normalize_runtime_root,
    validate_instance,
)


COMMANDER_ROOT = PROJECT_ROOT / "commander"
SCHEMA_DIR = COMMANDER_ROOT / "transport" / "schemas"
MEMORY_INDEX_SCHEMA_PATH = SCHEMA_DIR / "commander_memory_index.schema.json"

LAYER_SESSION_RUNTIME = "session_runtime"
LAYER_PERSISTENT_DOCS = "persistent_commander_docs"
LAYER_PROCEDURAL_MEMORY = "procedural_memory"
LAYER_ORDER = (
    LAYER_SESSION_RUNTIME,
    LAYER_PERSISTENT_DOCS,
    LAYER_PROCEDURAL_MEMORY,
)
LAYER_PRIORITY = {
    LAYER_SESSION_RUNTIME: 3,
    LAYER_PERSISTENT_DOCS: 2,
    LAYER_PROCEDURAL_MEMORY: 1,
}

SESSION_RUNTIME_FILE_SOURCES: dict[str, tuple[str, ...]] = {
    "checkpoint": ("checkpoint.json",),
    "packet": ("packet.json",),
    "context_bundle": ("context_bundle.json",),
    "resume_anchor": ("resume_anchor.json",),
    "worker_brief": ("worker_brief.md",),
    "worker_report": ("worker_report.json",),
    "report": ("report.json",),
    "status": ("status.json",),
    "lifecycle": ("lifecycle.json",),
    "catalog_refresh": ("catalog_refresh.json",),
    "improvement_candidate": ("improvement_candidate.json",),
    "events": ("events.jsonl",),
}

SESSION_RUNTIME_HOST_SOURCES: dict[str, tuple[str, ...]] = {
    "host_runtime": ("host_runtime/registry.json",),
    "host_runtime_session": ("host_runtime/sessions/*.json",),
    "host_daemon_state": ("host_daemon/daemon_state.json",),
    "host_daemon_log": ("host_daemon/daemon.log.jsonl",),
}

PERSISTENT_DOC_SOURCES: dict[str, Path] = {
    "commander_appointment": COMMANDER_ROOT / "core" / "任命.md",
    "commander_doc": COMMANDER_ROOT / "core" / "主文档.md",
    "task_card": COMMANDER_ROOT / "state" / "当前任务卡.md",
    "timeline": COMMANDER_ROOT / "state" / "时间线.md",
    "issue_index": COMMANDER_ROOT / "state" / "问题索引.md",
    "memory_guide": COMMANDER_ROOT / "outer" / "指挥官记忆检索说明.md",
    "handoff_template": COMMANDER_ROOT / "outer" / "新窗口启动指令模板.md",
    "execution_workbench": COMMANDER_ROOT / "outer" / "agent_workbench.md",
    "dispatch_policy": COMMANDER_ROOT / "outer" / "指挥官调度原则.md",
    "dispatch_harness_v1": COMMANDER_ROOT / "outer" / "指挥官调度与结果回收harness-v1.md",
    "langgraph_runtime": COMMANDER_ROOT / "outer" / "指挥官LangGraph运行时项目化方案.md",
    "hermes_lite": COMMANDER_ROOT / "outer" / "指挥官Hermes-lite受控进化方案.md",
    "harness_priority": COMMANDER_ROOT / "outer" / "指挥官harness-v1实施优先级.md",
    "skill_load_policy": COMMANDER_ROOT / "outer" / "指挥官SkillRegistry与加载策略.md",
    "reuse_protocol": PROJECT_ROOT / "docs" / "复用问题沉淀与Skill升级协议.md",
}

REPO_SCRIPT_ROOTS: dict[str, Path] = {
    "repo_scripts": PROJECT_ROOT / "scripts",
    "commander_scripts": COMMANDER_ROOT / "transport" / "scripts",
}

REPO_SKILL_SOURCE_ROOT = COMMANDER_ROOT / "skill-source"
MEMORY_SOURCE_IDS = (
    *SESSION_RUNTIME_FILE_SOURCES.keys(),
    *SESSION_RUNTIME_HOST_SOURCES.keys(),
    *PERSISTENT_DOC_SOURCES.keys(),
    *REPO_SCRIPT_ROOTS.keys(),
    "repo_skill_source",
    "local_skills",
    "candidate_skills",
)
SKILL_SOURCE_PRECEDENCE = {
    "repo_skill_source": 30,
    "local_skills": 20,
    "candidate_skills": 10,
}
SKILL_SOURCE_LOAD_POLICY = {
    "default_mode": "metadata_first",
    "body_load_trigger": "read_SKILL_md_only_after_skill_match",
    "candidate_isolation": "candidate_skills_never_override_live_skills",
}


@dataclass(frozen=True)
class MemoryDocument:
    source: str
    source_kind: str
    path: Path
    title: str
    text: str
    layer: str = LAYER_PERSISTENT_DOCS
    registry_metadata: dict[str, object] | None = None


def resolve_layers(raw_layers: list[str] | None) -> list[str]:
    if not raw_layers or "all" in raw_layers:
        return list(LAYER_ORDER)

    ordered: list[str] = []
    seen: set[str] = set()
    for layer in raw_layers:
        normalized = layer.strip()
        if not normalized or normalized in seen:
            continue
        if normalized not in LAYER_ORDER:
            raise ValueError(f"Unknown memory layer: {normalized}")
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def resolve_sources(raw_sources: list[str]) -> list[str]:
    all_sources = list(MEMORY_SOURCE_IDS)
    if not raw_sources or "all" in raw_sources:
        return all_sources

    ordered: list[str] = []
    seen: set[str] = set()
    for source in raw_sources:
        normalized = source.strip()
        if not normalized or normalized in seen:
            continue
        if normalized not in all_sources:
            raise ValueError(f"Unknown memory source: {normalized}")
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def all_memory_source_ids() -> Iterable[str]:
    return MEMORY_SOURCE_IDS


def build_memory_index(
    runtime_root: Path,
    query: str,
    *,
    sources: list[str] | None = None,
    layers: list[str] | None = None,
    limit: int = 8,
    repo_root: Path = PROJECT_ROOT,
    local_skill_root: Path | None = None,
) -> dict[str, object]:
    requested_layers = resolve_layers(layers)
    requested_sources = resolve_sources(sources or [])
    documents = collect_memory_documents(
        runtime_root,
        requested_sources,
        layers=requested_layers,
        repo_root=repo_root,
        local_skill_root=local_skill_root,
    )
    skill_source_registry = build_skill_source_registry(documents)
    results = search_documents(documents, query, limit=limit)
    layer_summaries = build_layer_summaries(documents, results)
    payload = {
        "schema_version": "commander-memory-index-v1",
        "query": query,
        "runtime_root": str(runtime_root),
        "searched_layers": requested_layers,
        "searched_sources": requested_sources,
        "index": {
            "layer_count": len(layer_summaries),
            "entry_count": len(documents),
            "layers": layer_summaries,
        },
        "skill_source_registry": skill_source_registry,
        "result_count": len(results),
        "results": results,
    }
    validate_instance(payload, load_schema(MEMORY_INDEX_SCHEMA_PATH))
    return payload


def collect_memory_documents(
    runtime_root: Path,
    sources: list[str],
    *,
    layers: list[str] | None = None,
    repo_root: Path = PROJECT_ROOT,
    local_skill_root: Path | None = None,
) -> list[MemoryDocument]:
    requested_layers = resolve_layers(layers)
    requested_sources = set(resolve_sources(sources))
    documents: list[MemoryDocument] = []

    if LAYER_SESSION_RUNTIME in requested_layers:
        documents.extend(
            _collect_session_runtime_documents(runtime_root, requested_sources)
        )
    if LAYER_PERSISTENT_DOCS in requested_layers:
        documents.extend(
            _collect_persistent_documents(requested_sources)
        )
    if LAYER_PROCEDURAL_MEMORY in requested_layers:
        documents.extend(
            _collect_procedural_documents(
                repo_root,
                runtime_root,
                requested_sources,
                local_skill_root=local_skill_root,
            )
        )
    return documents


def search_documents(
    documents: Iterable[MemoryDocument],
    query: str,
    *,
    limit: int,
) -> list[dict[str, object]]:
    normalized_query, tokens = tokenize_query(query)
    hits: list[dict[str, object]] = []

    for document in documents:
        body_score, excerpt, matched_lines = build_excerpt(
            document.text,
            normalized_query=normalized_query,
            tokens=tokens,
        )

        path_bonus = score_text_line(
            str(document.path), normalized_query=normalized_query, tokens=tokens
        )
        title_bonus = score_text_line(
            document.title, normalized_query=normalized_query, tokens=tokens
        )
        layer_bonus = LAYER_PRIORITY.get(document.layer, 0)
        registry_bonus = (
            int(document.registry_metadata.get("source_precedence") or 0)
            if isinstance(document.registry_metadata, dict)
            else 0
        )
        score = body_score + path_bonus + title_bonus + layer_bonus + registry_bonus
        if score <= 0:
            continue

        hits.append(
            {
                "layer": document.layer,
                "source": document.source,
                "source_kind": document.source_kind,
                "path": str(document.path),
                "title": document.title,
                "score": score,
                "matched_lines": matched_lines,
                "excerpt": excerpt,
            }
        )
        if document.registry_metadata is not None:
            hits[-1]["registry_metadata"] = document.registry_metadata

    hits.sort(
        key=lambda item: (
            -int(item["score"]),
            -LAYER_PRIORITY.get(str(item["layer"]), 0),
            -int(
                item.get("registry_metadata", {}).get("source_precedence", 0)
                if isinstance(item.get("registry_metadata"), dict)
                else 0
            ),
            str(item["path"]),
        )
    )
    for rank, hit in enumerate(hits[:limit], start=1):
        hit["rank"] = rank
    return hits[:limit]


def build_layer_summaries(
    documents: Iterable[MemoryDocument],
    results: Iterable[dict[str, object]],
) -> list[dict[str, object]]:
    documents_by_layer: dict[str, list[MemoryDocument]] = {
        layer: [] for layer in LAYER_ORDER
    }
    for document in documents:
        documents_by_layer.setdefault(document.layer, []).append(document)

    results_by_layer: dict[str, int] = {layer: 0 for layer in LAYER_ORDER}
    for result in results:
        layer = str(result.get("layer") or "")
        if layer:
            results_by_layer[layer] = results_by_layer.get(layer, 0) + 1

    summaries: list[dict[str, object]] = []
    for layer in LAYER_ORDER:
        layer_documents = documents_by_layer.get(layer, [])
        summaries.append(
            {
                "layer": layer,
                "entry_count": len(layer_documents),
                "result_count": results_by_layer.get(layer, 0),
                "source_count": len({document.source for document in layer_documents}),
                "sources": sorted({document.source for document in layer_documents}),
                "source_kinds": sorted(
                    {document.source_kind for document in layer_documents}
                ),
            }
        )
    return summaries


def build_skill_source_registry(
    documents: Iterable[MemoryDocument],
) -> dict[str, object]:
    skill_documents = [
        document
        for document in documents
        if isinstance(document.registry_metadata, dict)
        and document.registry_metadata.get("registry_kind") == "skill"
    ]
    entries = [
        dict(document.registry_metadata or {})
        for document in skill_documents
    ]
    by_skill_name: dict[str, list[dict[str, object]]] = {}
    for entry in entries:
        skill_name = str(entry.get("skill_name") or "").strip()
        if not skill_name:
            continue
        by_skill_name.setdefault(skill_name, []).append(entry)

    effective_sources: dict[str, dict[str, object]] = {}
    for skill_name, skill_entries in by_skill_name.items():
        sorted_entries = sorted(
            skill_entries,
            key=lambda item: -int(item.get("source_precedence") or 0),
        )
        effective_sources[skill_name] = {
            "skill_name": skill_name,
            "source": sorted_entries[0].get("source"),
            "source_kind": sorted_entries[0].get("source_kind"),
            "path": sorted_entries[0].get("path"),
            "source_precedence": sorted_entries[0].get("source_precedence"),
            "candidate_can_override_live": False,
        }
        for index, entry in enumerate(sorted_entries):
            entry["is_effective_source"] = index == 0
            entry["shadowed_by"] = None if index == 0 else sorted_entries[0].get("source")

    return {
        "schema_version": "commander-skill-source-registry-v1",
        "entry_count": len(entries),
        "source_precedence": SKILL_SOURCE_PRECEDENCE,
        "load_policy": SKILL_SOURCE_LOAD_POLICY,
        "effective_sources": sorted(
            effective_sources.values(),
            key=lambda item: str(item.get("skill_name") or ""),
        ),
        "entries": sorted(
            entries,
            key=lambda item: (
                str(item.get("skill_name") or ""),
                -int(item.get("source_precedence") or 0),
                str(item.get("path") or ""),
            ),
        ),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search commander memory across session/runtime state, docs, and procedural sources."
    )
    parser.add_argument("--query", required=True, help="Query string to search for")
    parser.add_argument(
        "--runtime-root",
        default=None,
        help="Override runtime root. Defaults to .runtime/commander",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Override repo root for persistent docs and procedural sources.",
    )
    parser.add_argument(
        "--local-skill-root",
        default=None,
        help="Override local skill root. Defaults to $CODEX_HOME/skills or ~/.codex/skills.",
    )
    parser.add_argument("--layer", action="append", choices=[*LAYER_ORDER, "all"], default=[])
    parser.add_argument("--source", action="append", choices=[*all_memory_source_ids(), "all"], default=[])
    parser.add_argument("--limit", type=int, default=8, help="Maximum number of ranked hits to return")
    return parser.parse_args(argv)


def resolve_local_skill_root(raw_local_skill_root: str | None = None) -> Path:
    if raw_local_skill_root:
        return Path(raw_local_skill_root).expanduser().resolve()
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        return (Path(codex_home).expanduser().resolve() / "skills").resolve()
    return (Path.home() / ".codex" / "skills").resolve()


def _collect_session_runtime_documents(
    runtime_root: Path,
    requested_sources: set[str],
) -> list[MemoryDocument]:
    documents: list[MemoryDocument] = []

    tasks_root = runtime_root / "tasks"
    if tasks_root.exists():
        for task_dir in sorted(path for path in tasks_root.iterdir() if path.is_dir()):
            for source, filenames in SESSION_RUNTIME_FILE_SOURCES.items():
                if source not in requested_sources:
                    continue
                for filename in filenames:
                    payload_path = task_dir / filename
                    if not payload_path.exists():
                        continue
                    text = payload_path.read_text(encoding="utf-8-sig")
                    documents.append(
                        MemoryDocument(
                            layer=LAYER_SESSION_RUNTIME,
                            source=source,
                            source_kind="runtime_artifact",
                            path=payload_path,
                            title=_extract_structured_title(
                                text=text,
                                fallback=f"{task_dir.name}:{payload_path.stem}",
                            ),
                            text=text,
                        )
                    )

    host_runtime_root = runtime_root / "host_runtime"
    if host_runtime_root.exists():
        if "host_runtime" in requested_sources:
            registry_path = host_runtime_root / "registry.json"
            if registry_path.exists():
                documents.append(
                    MemoryDocument(
                        layer=LAYER_SESSION_RUNTIME,
                        source="host_runtime",
                        source_kind="runtime_artifact",
                        path=registry_path,
                        title=_extract_structured_title(
                            text=registry_path.read_text(encoding="utf-8-sig"),
                            fallback="host_runtime:registry",
                        ),
                        text=registry_path.read_text(encoding="utf-8-sig"),
                    )
                )
        if "host_runtime_session" in requested_sources:
            sessions_root = host_runtime_root / "sessions"
            if sessions_root.exists():
                for session_path in sorted(sessions_root.glob("*.json")):
                    text = session_path.read_text(encoding="utf-8-sig")
                    documents.append(
                        MemoryDocument(
                            layer=LAYER_SESSION_RUNTIME,
                            source="host_runtime_session",
                            source_kind="runtime_artifact",
                            path=session_path,
                            title=_extract_structured_title(
                                text=text,
                                fallback=session_path.stem,
                            ),
                            text=text,
                        )
                    )

    host_daemon_root = runtime_root / "host_daemon"
    if host_daemon_root.exists():
        daemon_state_path = host_daemon_root / "daemon_state.json"
        if "host_daemon_state" in requested_sources and daemon_state_path.exists():
            text = daemon_state_path.read_text(encoding="utf-8-sig")
            documents.append(
                MemoryDocument(
                    layer=LAYER_SESSION_RUNTIME,
                    source="host_daemon_state",
                    source_kind="runtime_artifact",
                    path=daemon_state_path,
                    title=_extract_structured_title(
                        text=text,
                        fallback="host_daemon_state",
                    ),
                    text=text,
                )
            )
        daemon_log_path = host_daemon_root / "daemon.log.jsonl"
        if "host_daemon_log" in requested_sources and daemon_log_path.exists():
            text = daemon_log_path.read_text(encoding="utf-8-sig")
            documents.append(
                MemoryDocument(
                    layer=LAYER_SESSION_RUNTIME,
                    source="host_daemon_log",
                    source_kind="runtime_artifact",
                    path=daemon_log_path,
                    title="daemon.log",
                    text=text,
                )
            )

    return documents


def _collect_persistent_documents(requested_sources: set[str]) -> list[MemoryDocument]:
    documents: list[MemoryDocument] = []
    for source, path in PERSISTENT_DOC_SOURCES.items():
        if source not in requested_sources or not path.exists():
            continue
        text = path.read_text(encoding="utf-8-sig")
        documents.append(
            MemoryDocument(
                layer=LAYER_PERSISTENT_DOCS,
                source=source,
                source_kind="commander_doc",
                path=path,
                title=_extract_markdown_title(text, fallback=path.stem),
                text=text,
            )
        )
    return documents


def _collect_procedural_documents(
    repo_root: Path,
    runtime_root: Path,
    requested_sources: set[str],
    *,
    local_skill_root: Path | None,
) -> list[MemoryDocument]:
    documents: list[MemoryDocument] = []

    if "repo_scripts" in requested_sources:
        scripts_root = repo_root / "scripts"
        if scripts_root.exists():
            for path in sorted(scripts_root.rglob("*.py")):
                documents.append(
                    _build_procedural_document(
                        layer=LAYER_PROCEDURAL_MEMORY,
                        source="repo_scripts",
                        source_kind="repo_script",
                        path=path,
                        title=str(path.relative_to(repo_root).as_posix()),
                    )
                )

    if "commander_scripts" in requested_sources:
        scripts_root = repo_root / "commander" / "transport" / "scripts"
        if scripts_root.exists():
            for path in sorted(scripts_root.rglob("*.py")):
                documents.append(
                    _build_procedural_document(
                        layer=LAYER_PROCEDURAL_MEMORY,
                        source="commander_scripts",
                        source_kind="repo_script",
                        path=path,
                        title=str(path.relative_to(repo_root).as_posix()),
                    )
                )

    if "repo_skill_source" in requested_sources:
        repo_skill_root = repo_root / "commander" / "skill-source"
        if repo_skill_root.exists():
            for path in sorted(repo_skill_root.rglob("SKILL.md")):
                documents.append(
                    _build_skill_registry_document(
                        layer=LAYER_PROCEDURAL_MEMORY,
                        source="repo_skill_source",
                        source_kind="repo_skill_source",
                        path=path,
                    )
                )

    if "local_skills" in requested_sources:
        skill_root = local_skill_root or resolve_local_skill_root()
        if skill_root.exists():
            for path in sorted(skill_root.rglob("SKILL.md")):
                documents.append(
                    _build_skill_registry_document(
                        layer=LAYER_PROCEDURAL_MEMORY,
                        source="local_skills",
                        source_kind="local_skill",
                        path=path,
                    )
                )

    if "candidate_skills" in requested_sources:
        candidate_root = runtime_root / "skill_candidates"
        if candidate_root.exists():
            for path in sorted(candidate_root.rglob("SKILL.candidate.md")):
                documents.append(
                    _build_skill_registry_document(
                        layer=LAYER_PROCEDURAL_MEMORY,
                        source="candidate_skills",
                        source_kind="candidate_skill",
                        path=path,
                    )
                )

    return documents


def _build_procedural_document(
    *,
    layer: str,
    source: str,
    source_kind: str,
    path: Path,
    title: str,
) -> MemoryDocument:
    text = path.read_text(encoding="utf-8-sig")
    return MemoryDocument(
        layer=layer,
        source=source,
        source_kind=source_kind,
        path=path,
        title=title,
        text=text,
    )


def _build_skill_registry_document(
    *,
    layer: str,
    source: str,
    source_kind: str,
    path: Path,
) -> MemoryDocument:
    text = path.read_text(encoding="utf-8-sig")
    metadata = _extract_skill_metadata(text, fallback=path.parent.name)
    skill_name = str(metadata["skill_name"])
    description = str(metadata["description"])
    registry_metadata: dict[str, object] = {
        "registry_kind": "skill",
        "skill_name": skill_name,
        "description": description,
        "source": source,
        "source_kind": source_kind,
        "path": str(path),
        "source_precedence": SKILL_SOURCE_PRECEDENCE[source],
        "load_policy": "metadata_first",
        "body_loaded": False,
        "load_target": str(path),
        "candidate_can_override_live": False,
    }
    summary_lines = [
        f"skill_name: {skill_name}",
        f"description: {description}",
        f"source: {source}",
        f"source_kind: {source_kind}",
        "load_policy: metadata_first",
        f"load_target: {path}",
    ]
    if source == "candidate_skills":
        summary_lines.append("candidate_isolation: review_only_never_overrides_live")
    return MemoryDocument(
        layer=layer,
        source=source,
        source_kind=source_kind,
        path=path,
        title=skill_name,
        text="\n".join(summary_lines),
        registry_metadata=registry_metadata,
    )


def _extract_markdown_title(text: str, *, fallback: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return fallback


def _extract_skill_title(text: str, *, fallback: str) -> str:
    for line in text.splitlines()[:25]:
        stripped = line.strip()
        if stripped.startswith("name:"):
            value = stripped.split(":", 1)[1].strip()
            if value:
                return _strip_metadata_scalar(value)
    return _extract_markdown_title(text, fallback=fallback)


def _extract_skill_metadata(text: str, *, fallback: str) -> dict[str, str]:
    metadata = {
        "skill_name": _extract_skill_title(text, fallback=fallback),
        "description": "",
    }
    for line in text.splitlines()[:40]:
        stripped = line.strip()
        if stripped.startswith("name:"):
            value = stripped.split(":", 1)[1].strip()
            if value:
                metadata["skill_name"] = _strip_metadata_scalar(value)
        if stripped.startswith("description:"):
            value = stripped.split(":", 1)[1].strip()
            if value:
                metadata["description"] = _strip_metadata_scalar(value)
    if not metadata["description"]:
        metadata["description"] = _extract_markdown_title(
            text,
            fallback=metadata["skill_name"],
        )
    return metadata


def _strip_metadata_scalar(value: str) -> str:
    return value.strip().strip("\"'")


def _extract_structured_title(*, text: str, fallback: str) -> str:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return fallback

    if isinstance(payload, dict):
        for key in ("title", "name", "task_id", "session_id", "worker_id"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return fallback


def tokenize_query(query: str) -> tuple[str, list[str]]:
    query_text = query.strip()
    if not query_text:
        raise ValueError("Search query must not be empty")
    normalized = query_text.casefold()
    tokens = [token for token in re.split(r"\s+", normalized) if token]
    if not tokens:
        tokens = [normalized]
    return normalized, tokens


def score_text_line(line: str, *, normalized_query: str, tokens: list[str]) -> int:
    normalized_line = line.casefold()
    score = 0
    if normalized_query in normalized_line:
        score += 12
    for token in tokens:
        if token != normalized_query and token in normalized_line:
            score += 4
    return score


def build_excerpt(text: str, *, normalized_query: str, tokens: list[str]) -> tuple[int, str, list[int]]:
    scored_lines: list[tuple[int, int, str]] = []
    for index, line in enumerate(text.splitlines(), start=1):
        score = score_text_line(line, normalized_query=normalized_query, tokens=tokens)
        if score > 0:
            scored_lines.append((score, index, line.strip()))

    if not scored_lines:
        return 0, "", []

    scored_lines.sort(key=lambda item: (-item[0], item[1]))
    top_lines = scored_lines[:3]
    excerpt = "\n".join(f"L{line_no}: {line_text}" for _, line_no, line_text in top_lines)
    total_score = sum(item[0] for item in top_lines)
    return total_score, excerpt, [line_no for _, line_no, _ in top_lines]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    runtime_root = normalize_runtime_root(args.runtime_root)
    repo_root = Path(args.repo_root).expanduser().resolve() if args.repo_root else PROJECT_ROOT
    local_skill_root = (
        Path(args.local_skill_root).expanduser().resolve()
        if args.local_skill_root
        else resolve_local_skill_root()
    )
    payload = build_memory_index(
        runtime_root,
        args.query,
        sources=args.source,
        layers=args.layer,
        limit=args.limit,
        repo_root=repo_root,
        local_skill_root=local_skill_root,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
