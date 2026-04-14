from __future__ import annotations

from commander.graph.adapters.worker_providers.base import WorkerProviderCapabilities
from commander.graph.adapters.worker_providers.external_window import (
    ExternalWindowWorkerProvider,
)


class DoubaoWorkerProvider(ExternalWindowWorkerProvider):
    provider_id = "doubao"
    provider_label = "Doubao Worker Window"
    capabilities = WorkerProviderCapabilities(
        read_files=True,
        edit_files=False,
        run_shell=False,
        run_tests=False,
        commit_git=False,
        review_only=True,
    )
