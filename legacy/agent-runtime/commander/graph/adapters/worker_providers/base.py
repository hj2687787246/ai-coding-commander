from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class WorkerProviderCapabilities:
    read_files: bool
    edit_files: bool
    run_shell: bool
    run_tests: bool
    commit_git: bool
    review_only: bool


@dataclass(frozen=True)
class WorkerToolProfile:
    profile_id: str
    label: str
    allowed_tools: tuple[str, ...]
    notes: tuple[str, ...] = ()
    read_only: bool = False


@dataclass(frozen=True)
class WorkerProviderLifecycle:
    dispatch_kinds: tuple[str, ...]
    continuation_modes: tuple[str, ...]
    supports_inline_dispatch: bool
    supports_external_handoff: bool


@dataclass(frozen=True)
class WorkerLauncherPreset:
    preset_id: str
    label: str
    command: tuple[str, ...]
    detached: bool = True
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkerProviderMetadata:
    provider_id: str
    label: str
    capabilities: WorkerProviderCapabilities
    lifecycle: WorkerProviderLifecycle
    default_tool_profile: str
    supported_tool_profiles: tuple[str, ...]
    supported_launcher_presets: tuple[str, ...] = ()
    governance_notes: tuple[str, ...] = ()
    host_adapter_id: str | None = None
    tags: tuple[str, ...] = ()


class WorkerDispatchGovernanceError(ValueError):
    """Raised when a provider/tool-profile/task-packet combination is unsafe."""

    def __init__(
        self,
        message: str,
        *,
        provider_id: str | None = None,
        tool_profile: str | None = None,
        violations: list[str] | None = None,
        governance: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.provider_id = provider_id
        self.tool_profile = tool_profile
        self.violations = violations or []
        self.governance = governance or {}


@dataclass(frozen=True)
class WorkerDispatchGovernance:
    provider: WorkerProviderMetadata
    tool_profile: WorkerToolProfile
    allowed_tools: tuple[str, ...]
    forbidden_paths: tuple[str, ...]
    owned_paths: tuple[str, ...]
    tool_policy: dict[str, Any] | None = None
    path_policy: dict[str, Any] | None = None
    violations: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    contract_notes: tuple[str, ...] = ()
    dispatch_kind: str | None = None
    closure_policy: str | None = None
    packet_task_id: str | None = None

    @property
    def ok(self) -> bool:
        return not self.violations

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider.provider_id,
            "provider_label": self.provider.label,
            "provider_capabilities": {
                "read_files": self.provider.capabilities.read_files,
                "edit_files": self.provider.capabilities.edit_files,
                "run_shell": self.provider.capabilities.run_shell,
                "run_tests": self.provider.capabilities.run_tests,
                "commit_git": self.provider.capabilities.commit_git,
                "review_only": self.provider.capabilities.review_only,
            },
            "dispatch_kind": self.dispatch_kind,
            "closure_policy": self.closure_policy,
            "packet_task_id": self.packet_task_id,
            "tool_profile": {
                "profile_id": self.tool_profile.profile_id,
                "label": self.tool_profile.label,
                "allowed_tools": list(self.tool_profile.allowed_tools),
                "read_only": self.tool_profile.read_only,
            },
            "allowed_tools": list(self.allowed_tools),
            "forbidden_paths": list(self.forbidden_paths),
            "owned_paths": list(self.owned_paths),
            "tool_policy": self.tool_policy,
            "path_policy": self.path_policy,
            "supported_dispatch_kinds": list(self.provider.lifecycle.dispatch_kinds),
            "supported_continuation_modes": list(
                self.provider.lifecycle.continuation_modes
            ),
            "supports_inline_dispatch": self.provider.lifecycle.supports_inline_dispatch,
            "supports_external_handoff": self.provider.lifecycle.supports_external_handoff,
            "default_tool_profile": self.provider.default_tool_profile,
            "supported_tool_profiles": list(self.provider.supported_tool_profiles),
            "supported_launcher_presets": list(
                self.provider.supported_launcher_presets
            ),
            "violations": list(self.violations),
            "warnings": list(self.warnings),
            "contract_notes": list(self.contract_notes),
            "host_adapter_id": self.provider.host_adapter_id,
            "tags": list(self.provider.tags),
        }


@dataclass(frozen=True)
class WorkerProviderDispatchContext:
    thread_id: str
    task_id: str
    runtime_root: str
    packet_path: str
    context_bundle_path: str
    worker_brief_path: str
    worker_report_path: str
    resume_anchor_path: str
    checkpoint_path: str
    status_path: str
    dispatch_idempotency_key: str | None = None
    worker_id: str | None = None
    worker_profile: str | None = None
    preferred_worker_profile: str | None = None
    tool_profile: str | None = None
    allowed_tools: tuple[str, ...] = ()
    forbidden_paths: tuple[str, ...] = ()
    owned_paths: tuple[str, ...] = ()
    reuse_allowed: bool = False
    dispatch_kind: str | None = None
    closure_policy: str | None = None
    governance: dict[str, Any] | None = None


@dataclass(frozen=True)
class WorkerProviderResult:
    status: str
    worker_report: dict[str, Any] | None
    evidence: list[str]
    dispatch_metadata: dict[str, Any] | None = None
    governance: dict[str, Any] | None = None


class WorkerProvider(Protocol):
    provider_id: str
    capabilities: WorkerProviderCapabilities
    metadata: WorkerProviderMetadata

    def dispatch(
        self,
        task_packet: dict[str, Any],
        *,
        dispatch_context: WorkerProviderDispatchContext | None = None,
    ) -> WorkerProviderResult:
        """Dispatch a unified task packet and return a unified worker report."""
