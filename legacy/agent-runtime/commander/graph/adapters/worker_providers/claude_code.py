from __future__ import annotations

from commander.graph.adapters.worker_providers.external_window import (
    ExternalWindowWorkerProvider,
)


class ClaudeCodeWorkerProvider(ExternalWindowWorkerProvider):
    provider_id = "claude-code"
    provider_label = "Claude Code Worker Window"
