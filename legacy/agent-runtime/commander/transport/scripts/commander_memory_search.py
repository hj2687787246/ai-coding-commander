from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from commander.transport.scripts.commander_memory_index import (
    LAYER_ORDER,
    MEMORY_INDEX_SCHEMA_PATH,
    MemoryDocument,
    all_memory_source_ids,
    build_excerpt,
    build_layer_summaries,
    build_memory_index,
    collect_memory_documents,
    main,
    parse_args,
    resolve_layers,
    resolve_local_skill_root,
    resolve_sources,
    score_text_line,
    search_documents,
    tokenize_query,
)

__all__ = [
    "LAYER_ORDER",
    "MEMORY_INDEX_SCHEMA_PATH",
    "MemoryDocument",
    "all_memory_source_ids",
    "build_excerpt",
    "build_layer_summaries",
    "build_memory_index",
    "collect_memory_documents",
    "main",
    "parse_args",
    "resolve_layers",
    "resolve_local_skill_root",
    "resolve_sources",
    "score_text_line",
    "search_documents",
    "tokenize_query",
]


if __name__ == "__main__":
    raise SystemExit(main())
