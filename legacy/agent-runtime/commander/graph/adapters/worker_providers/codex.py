from __future__ import annotations

from commander.graph.adapters.worker_providers.external_window import (
    ExternalWindowWorkerProvider,
)


class CodexWorkerProvider(ExternalWindowWorkerProvider):
    provider_id = "codex"
    provider_label = "Codex Worker Window"
