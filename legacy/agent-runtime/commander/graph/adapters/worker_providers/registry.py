from __future__ import annotations

from typing import Any, Callable

from commander.graph.adapters.worker_providers.base import (
    WorkerDispatchGovernance,
    WorkerDispatchGovernanceError,
    WorkerProvider,
    WorkerProviderCapabilities,
    WorkerProviderLifecycle,
    WorkerProviderMetadata,
    WorkerToolProfile,
)
from commander.graph.policies.lane_contract import (
    build_lane_contract_policy,
    resolve_worker_tool_profile_id,
)
from commander.graph.policies.tool_path_governance import (
    build_path_governance_policy,
    build_tool_governance_policy,
)
from commander.graph.adapters.worker_providers.claude_code import (
    ClaudeCodeWorkerProvider,
)
from commander.graph.adapters.worker_providers.codex import CodexWorkerProvider
from commander.graph.adapters.worker_providers.doubao import DoubaoWorkerProvider
from commander.graph.adapters.worker_providers.local_script import (
    LocalScriptWorkerProvider,
)
from commander.graph.adapters.worker_providers.qwen import QwenWorkerProvider


TOOL_PROFILES: dict[str, WorkerToolProfile] = {
    "default": WorkerToolProfile(
        profile_id="default",
        label="Default Worker Profile",
        allowed_tools=("shell_command",),
        notes=("Fallback profile for read/inspect style tasks.",),
        read_only=True,
    ),
    "control_plane_safe_write": WorkerToolProfile(
        profile_id="control_plane_safe_write",
        label="Control Plane Safe Write",
        allowed_tools=("shell_command", "apply_patch"),
        notes=(
            "Allows shell execution and patch-based file edits.",
            "Forbidden paths remain task-contract boundaries and are not overridden by provider capabilities.",
        ),
        read_only=False,
    ),
    "commander_docs_write": WorkerToolProfile(
        profile_id="commander_docs_write",
        label="Commander Docs Write",
        allowed_tools=("shell_command", "apply_patch"),
        notes=(
            "Narrow write profile for commander documentation surfaces only.",
            "Dispatch governance must still constrain owned_paths to commander docs surfaces.",
        ),
        read_only=False,
    ),
    "review_only": WorkerToolProfile(
        profile_id="review_only",
        label="Review Only",
        allowed_tools=("shell_command",),
        notes=("For providers restricted to reading, inspection, or lightweight analysis.",),
        read_only=True,
    ),
    "commander_readonly": WorkerToolProfile(
        profile_id="commander_readonly",
        label="Commander Read Only",
        allowed_tools=("shell_command",),
        notes=("Clear read-only contract for commander-style analysis, verifier, and explorer lanes.",),
        read_only=True,
    ),
    "local_script_readonly": WorkerToolProfile(
        profile_id="local_script_readonly",
        label="Local Script Read Only",
        allowed_tools=("shell_command",),
        notes=("Backward-compatible alias for read-only local-script and analysis lanes.",),
        read_only=True,
    ),
}


_PROVIDER_METADATA: dict[str, WorkerProviderMetadata] = {
    "codex": WorkerProviderMetadata(
        provider_id="codex",
        label="Codex Worker Window",
        capabilities=WorkerProviderCapabilities(
            read_files=True,
            edit_files=True,
            run_shell=True,
            run_tests=True,
            commit_git=True,
            review_only=False,
        ),
        lifecycle=WorkerProviderLifecycle(
            dispatch_kinds=("fresh", "followup", "split", "reopen", "reconcile"),
            continuation_modes=("close", "followup", "split", "wait_user"),
            supports_inline_dispatch=False,
            supports_external_handoff=True,
        ),
        default_tool_profile="control_plane_safe_write",
        supported_tool_profiles=(
            "default",
            "control_plane_safe_write",
            "commander_docs_write",
            "commander_readonly",
            "local_script_readonly",
        ),
        supported_launcher_presets=("codex-cli",),
        governance_notes=(
            "Provider is model-agnostic and should be treated as an interchangeable worker backend.",
            "Forbidden paths stay as dispatch contract boundaries; provider capability does not narrow them automatically.",
        ),
        host_adapter_id="external-window",
        tags=("external_window", "code_worker"),
    ),
    "claude-code": WorkerProviderMetadata(
        provider_id="claude-code",
        label="Claude Code Worker Window",
        capabilities=WorkerProviderCapabilities(
            read_files=True,
            edit_files=True,
            run_shell=True,
            run_tests=True,
            commit_git=True,
            review_only=False,
        ),
        lifecycle=WorkerProviderLifecycle(
            dispatch_kinds=("fresh", "followup", "split", "reopen", "reconcile"),
            continuation_modes=("close", "followup", "split", "wait_user"),
            supports_inline_dispatch=False,
            supports_external_handoff=True,
        ),
        default_tool_profile="control_plane_safe_write",
        supported_tool_profiles=(
            "default",
            "control_plane_safe_write",
            "commander_docs_write",
            "commander_readonly",
            "local_script_readonly",
        ),
        supported_launcher_presets=("claude-code-cli",),
        governance_notes=(
            "External-window provider with the same governance contract as other code-capable providers.",
        ),
        host_adapter_id="external-window",
        tags=("external_window", "code_worker"),
    ),
    "qwen": WorkerProviderMetadata(
        provider_id="qwen",
        label="Qwen Worker Window",
        capabilities=WorkerProviderCapabilities(
            read_files=True,
            edit_files=False,
            run_shell=False,
            run_tests=False,
            commit_git=False,
            review_only=True,
        ),
        lifecycle=WorkerProviderLifecycle(
            dispatch_kinds=("fresh", "followup", "reconcile"),
            continuation_modes=("followup", "wait_user"),
            supports_inline_dispatch=False,
            supports_external_handoff=True,
        ),
        default_tool_profile="review_only",
        supported_tool_profiles=("default", "review_only", "commander_readonly"),
        supported_launcher_presets=("qwen-cli",),
        governance_notes=(
            "Review-only provider: cannot safely execute shell, tests, git, or file edits.",
        ),
        host_adapter_id="external-window",
        tags=("external_window", "review_only"),
    ),
    "doubao": WorkerProviderMetadata(
        provider_id="doubao",
        label="Doubao Worker Window",
        capabilities=WorkerProviderCapabilities(
            read_files=True,
            edit_files=False,
            run_shell=False,
            run_tests=False,
            commit_git=False,
            review_only=True,
        ),
        lifecycle=WorkerProviderLifecycle(
            dispatch_kinds=("fresh", "followup", "reconcile"),
            continuation_modes=("followup", "wait_user"),
            supports_inline_dispatch=False,
            supports_external_handoff=True,
        ),
        default_tool_profile="review_only",
        supported_tool_profiles=("default", "review_only", "commander_readonly"),
        supported_launcher_presets=("doubao-cli",),
        governance_notes=(
            "Review-only provider: cannot safely execute shell, tests, git, or file edits.",
        ),
        host_adapter_id="external-window",
        tags=("external_window", "review_only"),
    ),
    "local-script": WorkerProviderMetadata(
        provider_id="local-script",
        label="Local Script Worker",
        capabilities=WorkerProviderCapabilities(
            read_files=True,
            edit_files=False,
            run_shell=True,
            run_tests=True,
            commit_git=False,
            review_only=False,
        ),
        lifecycle=WorkerProviderLifecycle(
            dispatch_kinds=("fresh", "followup", "split", "reopen", "reconcile"),
            continuation_modes=("close", "followup", "split", "wait_user"),
            supports_inline_dispatch=True,
            supports_external_handoff=False,
        ),
        default_tool_profile="default",
        supported_tool_profiles=("default", "commander_readonly", "local_script_readonly"),
        governance_notes=(
            "Inline provider runs repo-local commands only and never grants file-edit authority by itself.",
        ),
        host_adapter_id=None,
        tags=("inline", "script"),
    ),
}


_PROVIDER_FACTORIES: dict[str, Callable[[], WorkerProvider]] = {
    "codex": CodexWorkerProvider,
    "claude-code": ClaudeCodeWorkerProvider,
    "qwen": QwenWorkerProvider,
    "doubao": DoubaoWorkerProvider,
    "local-script": LocalScriptWorkerProvider,
}


def list_worker_provider_metadata() -> list[WorkerProviderMetadata]:
    return list(_PROVIDER_METADATA.values())


def get_tool_profile(profile_id: str) -> WorkerToolProfile:
    normalized = profile_id.strip().lower()
    try:
        return TOOL_PROFILES[normalized]
    except KeyError as error:
        raise WorkerDispatchGovernanceError(
            f"Unknown tool profile: {profile_id!r}",
            tool_profile=profile_id,
            violations=[f"tool_profile {profile_id!r} is not registered"],
        ) from error


def get_worker_provider_metadata(provider_id: str) -> WorkerProviderMetadata:
    normalized = provider_id.strip().lower()
    try:
        return _PROVIDER_METADATA[normalized]
    except KeyError as error:
        raise WorkerDispatchGovernanceError(
            f"Unknown worker provider: {provider_id!r}",
            provider_id=provider_id,
            violations=[f"provider_id {provider_id!r} is not registered"],
        ) from error


def get_worker_provider(provider_id: str) -> WorkerProvider:
    normalized = provider_id.strip().lower()
    try:
        provider = _PROVIDER_FACTORIES[normalized]()
    except KeyError as error:
        raise WorkerDispatchGovernanceError(
            f"Unknown worker provider: {provider_id!r}",
            provider_id=provider_id,
            violations=[f"provider_id {provider_id!r} is not registered"],
        ) from error
    provider.metadata = get_worker_provider_metadata(normalized)
    return provider


def validate_worker_dispatch_governance(
    task_packet: dict[str, Any],
    *,
    provider_id: str,
) -> WorkerDispatchGovernance:
    provider = get_worker_provider_metadata(provider_id)
    tool_profile_value = resolve_worker_tool_profile_id(
        worker_profile=task_packet.get("worker_profile"),
        requested_tool_profile=task_packet.get("tool_profile"),
        provider_default_tool_profile=provider.default_tool_profile,
    )
    tool_profile = get_tool_profile(tool_profile_value)
    allowed_tools = _normalize_string_list(task_packet.get("allowed_tools"))
    forbidden_paths = _normalize_string_list(task_packet.get("forbidden_paths"))
    owned_paths = _normalize_string_list(task_packet.get("owned_paths"))
    dispatch_kind = _normalize_optional_string(task_packet.get("dispatch_kind"))
    closure_policy = _normalize_optional_string(task_packet.get("closure_policy"))
    packet_task_id = _normalize_optional_string(task_packet.get("task_id"))

    tool_policy = build_tool_governance_policy(
        tool_profile=tool_profile,
        allowed_tools=allowed_tools,
        capabilities=provider.capabilities,
    )
    lane_policy = build_lane_contract_policy(
        worker_profile=task_packet.get("worker_profile"),
        tool_profile=tool_profile,
        owned_paths=owned_paths,
    )
    path_policy = build_path_governance_policy(
        forbidden_paths=forbidden_paths,
        owned_paths=owned_paths,
        write_intent=bool(tool_policy.get("write_intent")),
    )

    violations: list[str] = [
        *list(tool_policy.get("violations") or []),
        *list(lane_policy.get("violations") or []),
        *list(path_policy.get("violations") or []),
    ]
    warnings: list[str] = [
        *list(tool_policy.get("warnings") or []),
        *list(lane_policy.get("warnings") or []),
        *list(path_policy.get("warnings") or []),
    ]
    contract_notes = list(provider.governance_notes)
    contract_notes.append(
        "tool_policy and path_policy are runtime governance snapshots; they explain allowed surface but do not replace filesystem sandboxing."
    )
    contract_notes.append(
        "lane_policy maps worker_profile semantics to the minimum tool profile contract before provider dispatch."
    )
    contract_notes.append(
        "forbidden_paths and owned_paths are contract boundaries; governance can reject unsafe combinations but does not sandbox file IO by itself."
    )

    if tool_profile.profile_id not in provider.supported_tool_profiles:
        violations.append(
            f"provider {provider.provider_id!r} does not support tool_profile {tool_profile.profile_id!r}"
        )

    if dispatch_kind and dispatch_kind not in provider.lifecycle.dispatch_kinds:
        violations.append(
            f"provider {provider.provider_id!r} does not support dispatch_kind {dispatch_kind!r}"
        )

    unsupported_tools = [
        tool for tool in allowed_tools if tool not in tool_profile.allowed_tools
    ]
    if unsupported_tools:
        violations.append(
            f"allowed_tools {unsupported_tools!r} exceed tool_profile {tool_profile.profile_id!r}"
        )

    if provider.capabilities.review_only and not tool_profile.read_only:
        violations.append(
            f"review-only provider {provider.provider_id!r} cannot use writable tool_profile {tool_profile.profile_id!r}"
        )

    governance = WorkerDispatchGovernance(
        provider=provider,
        tool_profile=tool_profile,
        allowed_tools=allowed_tools,
        forbidden_paths=forbidden_paths,
        owned_paths=owned_paths,
        tool_policy=tool_policy,
        path_policy=path_policy,
        violations=tuple(violations),
        warnings=tuple(warnings),
        contract_notes=tuple(contract_notes),
        dispatch_kind=dispatch_kind,
        closure_policy=closure_policy,
        packet_task_id=packet_task_id,
    )
    if not governance.ok:
        raise WorkerDispatchGovernanceError(
            "Worker dispatch governance rejected the provider/tool profile combination.",
            provider_id=provider.provider_id,
            tool_profile=tool_profile.profile_id,
            violations=list(governance.violations),
            governance=governance.as_dict(),
        )
    return governance


def _normalize_string_list(raw_value: Any) -> tuple[str, ...]:
    if not isinstance(raw_value, list):
        return ()
    values: list[str] = []
    for item in raw_value:
        if not isinstance(item, str):
            continue
        normalized = item.strip()
        if normalized and normalized not in values:
            values.append(normalized)
    return tuple(values)


def _normalize_optional_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None
