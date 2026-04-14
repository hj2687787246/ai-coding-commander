from __future__ import annotations

from typing import Any


READ_ONLY_WORKER_PROFILES: frozenset[str] = frozenset(
    {
        "analysis-worker",
        "explorer-worker",
        "verifier-worker",
        "local-runtime-smoke",
    }
)

SCRIBE_WORKER_PROFILES: frozenset[str] = frozenset(
    {
        "scribe-worker",
    }
)

READ_ONLY_TOOL_PROFILES: frozenset[str] = frozenset(
    {
        "default",
        "review_only",
        "commander_readonly",
        "local_script_readonly",
    }
)

DOCS_WRITE_TOOL_PROFILES: frozenset[str] = frozenset(
    {
        "commander_docs_write",
    }
)

LEGACY_READ_ONLY_TOOL_PROFILES: frozenset[str] = frozenset(
    {
        "default",
        "review_only",
        "local_script_readonly",
    }
)

COMMANDER_DOC_SURFACE_PREFIXES: tuple[str, ...] = (
    "AGENTS.md",
    "commander/core",
    "commander/state",
    "commander/outer",
    "commander/skill-source",
)


def normalize_profile_id(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    return normalized or None


def is_read_only_worker_profile(worker_profile: Any) -> bool:
    normalized_worker_profile = normalize_profile_id(worker_profile)
    if normalized_worker_profile is None:
        return False
    if normalized_worker_profile in READ_ONLY_WORKER_PROFILES:
        return True
    return normalized_worker_profile.endswith("-readonly") or normalized_worker_profile.endswith("_readonly")


def is_scribe_worker_profile(worker_profile: Any) -> bool:
    normalized_worker_profile = normalize_profile_id(worker_profile)
    if normalized_worker_profile is None:
        return False
    if normalized_worker_profile in SCRIBE_WORKER_PROFILES:
        return True
    return normalized_worker_profile.endswith("-scribe") or normalized_worker_profile.endswith("_scribe")


def resolve_worker_tool_profile_id(
    *,
    worker_profile: Any,
    requested_tool_profile: Any,
    provider_default_tool_profile: str,
) -> str:
    requested_profile_id = normalize_profile_id(requested_tool_profile)
    provider_default_profile_id = normalize_profile_id(provider_default_tool_profile)
    if is_scribe_worker_profile(worker_profile):
        if requested_profile_id is None or requested_profile_id == "default":
            return "commander_docs_write"
    if is_read_only_worker_profile(worker_profile):
        if requested_profile_id is None or requested_profile_id == "default":
            return "commander_readonly"
    if requested_profile_id is None or requested_profile_id == "default":
        if provider_default_profile_id is not None:
            return provider_default_profile_id
        return "default"
    if requested_profile_id is not None:
        return requested_profile_id
    return "default"


def resolve_default_allowed_tools(
    *,
    worker_profile: Any,
    requested_allowed_tools: tuple[str, ...],
) -> tuple[str, ...]:
    if requested_allowed_tools:
        return requested_allowed_tools
    if is_scribe_worker_profile(worker_profile):
        return ("shell_command", "apply_patch")
    if is_read_only_worker_profile(worker_profile):
        return ("shell_command",)
    return ()


def build_lane_contract_policy(
    *,
    worker_profile: Any,
    tool_profile: Any,
    owned_paths: Any = (),
) -> dict[str, Any]:
    normalized_worker_profile = normalize_profile_id(worker_profile)
    normalized_tool_profile = normalize_profile_id(getattr(tool_profile, "profile_id", tool_profile))
    read_only_lane = is_read_only_worker_profile(normalized_worker_profile)
    scribe_lane = is_scribe_worker_profile(normalized_worker_profile)
    tool_profile_is_read_only = bool(getattr(tool_profile, "read_only", False))
    normalized_owned_paths = _normalize_repo_path_list(owned_paths)
    violations: list[str] = []
    warnings: list[str] = []

    if read_only_lane and not tool_profile_is_read_only:
        violations.append(
            f"read-only worker_profile {normalized_worker_profile!r} cannot use writable tool_profile {normalized_tool_profile!r}"
        )

    if scribe_lane and normalized_tool_profile not in DOCS_WRITE_TOOL_PROFILES:
        violations.append(
            f"scribe worker_profile {normalized_worker_profile!r} must use commander_docs_write tool_profile, got {normalized_tool_profile!r}"
        )

    if scribe_lane:
        illegal_owned_paths = [
            owned_path
            for owned_path in normalized_owned_paths
            if not _is_commander_docs_surface_path(owned_path)
        ]
        if illegal_owned_paths:
            violations.append(
                "scribe worker_profile owned_paths escape commander docs surfaces: "
                + ", ".join(illegal_owned_paths)
            )

    if read_only_lane and normalized_tool_profile in LEGACY_READ_ONLY_TOOL_PROFILES:
        warnings.append(
            "read-only lane used a legacy read-only tool_profile alias; prefer commander_readonly"
        )

    return {
        "worker_profile": normalized_worker_profile,
        "tool_profile": normalized_tool_profile,
        "lane_kind": "docs_write" if scribe_lane else "read_only" if read_only_lane else "write_capable",
        "scribe_lane": scribe_lane,
        "read_only_lane": read_only_lane,
        "expected_tool_profile": (
            "commander_docs_write"
            if scribe_lane
            else "commander_readonly"
            if read_only_lane
            else None
        ),
        "tool_profile_read_only": tool_profile_is_read_only,
        "owned_paths": list(normalized_owned_paths),
        "violations": violations,
        "warnings": warnings,
    }


def _is_commander_docs_surface_path(path: str) -> bool:
    for prefix in COMMANDER_DOC_SURFACE_PREFIXES:
        if path == prefix or path.startswith(f"{prefix}/"):
            return True
    return False


def _normalize_repo_path_list(raw_value: Any) -> tuple[str, ...]:
    if not isinstance(raw_value, (list, tuple)):
        return ()
    values: list[str] = []
    for item in raw_value:
        if not isinstance(item, str):
            continue
        normalized = item.strip().replace("\\", "/")
        while "//" in normalized:
            normalized = normalized.replace("//", "/")
        while normalized.startswith("./"):
            normalized = normalized[2:]
        if normalized.endswith("/"):
            normalized = normalized[:-1]
        if normalized and normalized not in values:
            values.append(normalized)
    return tuple(values)
