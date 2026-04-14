from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver

from commander.transport.scripts.commander_harness import normalize_runtime_root


def default_checkpoint_db_path(runtime_root: str | Path | None = None) -> Path:
    return normalize_runtime_root(runtime_root) / "graph" / "checkpoints.sqlite"


@contextmanager
def open_commander_checkpointer(
    *,
    runtime_root: str | Path | None = None,
    checkpoint_db: str | Path | None = None,
    allow_memory_fallback: bool = True,
) -> Iterator[Any]:
    """Open the graph checkpointer.

    SQLite is the normal path because the commander graph must survive context
    compression and process restarts. InMemorySaver remains as a local fallback
    for unit tests or partially installed environments.
    """

    resolved_db = (
        Path(checkpoint_db)
        if checkpoint_db is not None
        else default_checkpoint_db_path(runtime_root)
    )
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver
    except ModuleNotFoundError:
        if not allow_memory_fallback:
            raise
        yield InMemorySaver()
        return

    resolved_db.parent.mkdir(parents=True, exist_ok=True)
    with SqliteSaver.from_conn_string(str(resolved_db)) as saver:
        saver.setup()
        yield saver
