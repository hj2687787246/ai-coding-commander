from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from commander.transport.scripts.commander_harness import (
    PROJECT_ROOT,
    normalize_runtime_root,
)
from commander.transport.scripts.commander_memory_index import (
    build_skill_source_registry,
    collect_memory_documents,
    resolve_local_skill_root,
)


SKILL_REGISTRY_SOURCES = [
    "repo_skill_source",
    "local_skills",
    "candidate_skills",
]


def build_skill_load_plan(
    runtime_root: str | Path | None,
    skill_name: str,
    *,
    source: str | None = None,
    include_body: bool = False,
    repo_root: Path = PROJECT_ROOT,
    local_skill_root: Path | None = None,
) -> dict[str, Any]:
    normalized_skill_name = skill_name.strip()
    if not normalized_skill_name:
        raise ValueError("skill_name must not be empty")

    resolved_runtime_root = normalize_runtime_root(runtime_root)
    documents = collect_memory_documents(
        resolved_runtime_root,
        SKILL_REGISTRY_SOURCES,
        layers=["procedural_memory"],
        repo_root=repo_root,
        local_skill_root=local_skill_root,
    )
    registry = build_skill_source_registry(documents)
    entries = [
        entry
        for entry in registry["entries"]
        if entry.get("skill_name") == normalized_skill_name
        and (source is None or entry.get("source") == source)
    ]
    if not entries:
        return {
            "schema_version": "commander-skill-load-v1",
            "skill_name": normalized_skill_name,
            "status": "not_found",
            "requested_source": source,
            "body_loaded": False,
            "body": None,
            "load_policy": registry["load_policy"],
            "registry_entry": None,
            "available_sources": [
                entry.get("source")
                for entry in registry["entries"]
                if entry.get("skill_name") == normalized_skill_name
            ],
        }

    selected = entries[0]
    load_target = Path(str(selected["load_target"]))
    body = load_target.read_text(encoding="utf-8-sig") if include_body else None
    selected_source = str(selected.get("source") or "")
    return {
        "schema_version": "commander-skill-load-v1",
        "skill_name": normalized_skill_name,
        "status": "loaded" if include_body else "planned",
        "requested_source": source,
        "selected_source": selected_source,
        "source_kind": selected.get("source_kind"),
        "source_precedence": selected.get("source_precedence"),
        "is_effective_source": bool(selected.get("is_effective_source")),
        "candidate_review_only": selected_source == "candidate_skills",
        "candidate_can_override_live": bool(selected.get("candidate_can_override_live")),
        "body_loaded": include_body,
        "body": body,
        "load_policy": registry["load_policy"],
        "registry_entry": selected,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan or perform an explicit metadata-first skill body load."
    )
    parser.add_argument("--skill-name", required=True)
    parser.add_argument(
        "--source",
        choices=SKILL_REGISTRY_SOURCES,
        default=None,
        help="Optional source override. Defaults to the registry effective source.",
    )
    parser.add_argument(
        "--include-body",
        action="store_true",
        help="Actually read the selected SKILL.md body. Omit for metadata-only plan.",
    )
    parser.add_argument("--runtime-root", default=None)
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--local-skill-root", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = (
        Path(args.repo_root).expanduser().resolve()
        if args.repo_root
        else PROJECT_ROOT
    )
    local_skill_root = (
        Path(args.local_skill_root).expanduser().resolve()
        if args.local_skill_root
        else resolve_local_skill_root()
    )
    payload = build_skill_load_plan(
        args.runtime_root,
        args.skill_name,
        source=args.source,
        include_body=args.include_body,
        repo_root=repo_root,
        local_skill_root=local_skill_root,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
