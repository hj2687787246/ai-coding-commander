from __future__ import annotations

from typing import Any


_CAPABILITY_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "shell_command": ("run_shell",),
    "apply_patch": ("edit_files",),
}


def build_tool_governance_policy(
    *,
    tool_profile: Any,
    allowed_tools: tuple[str, ...],
    capabilities: Any,
) -> dict[str, Any]:
    unsupported_tools = [
        tool for tool in allowed_tools if tool not in tool_profile.allowed_tools
    ]
    capability_checks: list[dict[str, Any]] = []
    violations: list[str] = []
    warnings: list[str] = []

    for tool in allowed_tools:
        requirements = _CAPABILITY_REQUIREMENTS.get(tool)
        if requirements is None:
            violations.append(f"allowed_tools contains unregistered tool {tool!r}")
            capability_checks.append(
                {
                    "tool": tool,
                    "registered": False,
                    "requirements": [],
                    "missing_capabilities": [],
                    "allowed": False,
                }
            )
            continue

        missing = [
            attribute
            for attribute in requirements
            if not bool(getattr(capabilities, attribute))
        ]
        if missing:
            violations.append(
                f"tool {tool!r} requires provider capabilities {missing!r}"
            )
        capability_checks.append(
            {
                "tool": tool,
                "registered": True,
                "requirements": list(requirements),
                "missing_capabilities": missing,
                "allowed": not missing,
            }
        )

    write_intent = bool(allowed_tools) and not tool_profile.read_only
    if not allowed_tools:
        warnings.append(
            "task packet declared no allowed_tools; governance cannot infer execution surface"
        )

    return {
        "profile_id": tool_profile.profile_id,
        "profile_label": tool_profile.label,
        "profile_allowed_tools": list(tool_profile.allowed_tools),
        "requested_tools": list(allowed_tools),
        "unsupported_tools": unsupported_tools,
        "capability_checks": capability_checks,
        "write_intent": write_intent,
        "read_only": tool_profile.read_only,
        "violations": violations,
        "warnings": warnings,
    }


def build_path_governance_policy(
    *,
    forbidden_paths: tuple[str, ...],
    owned_paths: tuple[str, ...],
    write_intent: bool,
) -> dict[str, Any]:
    normalized_forbidden = tuple(_normalize_repo_path(item) for item in forbidden_paths)
    normalized_owned = tuple(_normalize_repo_path(item) for item in owned_paths)

    conflicting_pairs: list[dict[str, str]] = []
    violations: list[str] = []
    warnings: list[str] = []

    for owned_path in normalized_owned:
        for forbidden_path in normalized_forbidden:
            if _paths_overlap(owned_path, forbidden_path):
                conflicting_pairs.append(
                    {
                        "owned_path": owned_path,
                        "forbidden_path": forbidden_path,
                    }
                )
                violations.append(
                    f"owned_path {owned_path!r} overlaps forbidden_path {forbidden_path!r}"
                )

    if write_intent and not normalized_owned:
        warnings.append(
            "writable task declared no owned_paths; governance cannot prove write scope isolation"
        )
    if not normalized_forbidden:
        warnings.append(
            "task packet declared no forbidden_paths; governance cannot infer protected write boundaries"
        )
    if normalized_owned and not write_intent:
        warnings.append(
            "read-only task declared owned_paths; write scope metadata may be broader than needed"
        )

    return {
        "forbidden_paths": list(normalized_forbidden),
        "owned_paths": list(normalized_owned),
        "write_intent": write_intent,
        "protected_paths_declared": bool(normalized_forbidden),
        "write_scope_declared": bool(normalized_owned),
        "conflicting_path_pairs": conflicting_pairs,
        "violations": violations,
        "warnings": warnings,
    }


def build_changed_file_governance_policy(
    *,
    changed_files: Any,
    forbidden_paths: Any,
    owned_paths: Any,
    write_intent: Any = None,
) -> dict[str, Any]:
    normalized_changed = _normalize_repo_path_list(changed_files)
    normalized_forbidden = _normalize_repo_path_list(forbidden_paths)
    normalized_owned = _normalize_repo_path_list(owned_paths)
    normalized_write_intent = write_intent if isinstance(write_intent, bool) else None
    forbidden_hits: list[dict[str, str]] = []
    owned_scope_misses: list[str] = []
    violations: list[str] = []

    if normalized_write_intent is False and normalized_changed:
        violations.append(
            "read-only governance reported changed_files without write intent: "
            + ", ".join(normalized_changed)
        )

    for changed_path in normalized_changed:
        for forbidden_path in normalized_forbidden:
            if _paths_overlap(changed_path, forbidden_path):
                forbidden_hits.append(
                    {
                        "changed_file": changed_path,
                        "forbidden_path": forbidden_path,
                    }
                )
        if normalized_owned and not any(
            _paths_overlap(changed_path, owned_path)
            for owned_path in normalized_owned
        ):
            owned_scope_misses.append(changed_path)

    if forbidden_hits:
        first_hit = forbidden_hits[0]
        violations.append(
            "changed_files touches forbidden_path: "
            f"{first_hit['changed_file']} overlaps {first_hit['forbidden_path']}"
        )
    if owned_scope_misses:
        violations.append(
            "changed_files escapes owned_paths: "
            + ", ".join(owned_scope_misses)
        )

    return {
        "changed_files": list(normalized_changed),
        "forbidden_paths": list(normalized_forbidden),
        "owned_paths": list(normalized_owned),
        "write_intent": normalized_write_intent,
        "forbidden_hits": forbidden_hits,
        "owned_scope_misses": owned_scope_misses,
        "forbidden_hit_count": len(forbidden_hits),
        "owned_scope_miss_count": len(owned_scope_misses),
        "violations": violations,
        "ok": not violations,
    }


def _normalize_repo_path(value: str) -> str:
    normalized = value.strip().replace("\\", "/")
    while "//" in normalized:
        normalized = normalized.replace("//", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if normalized.endswith("/"):
        normalized = normalized[:-1]
    return normalized


def _normalize_repo_path_list(raw_value: Any) -> tuple[str, ...]:
    if not isinstance(raw_value, (list, tuple)):
        return ()
    values: list[str] = []
    for item in raw_value:
        if not isinstance(item, str) or not item.strip():
            continue
        normalized = _normalize_repo_path(item)
        if normalized and normalized not in values:
            values.append(normalized)
    return tuple(values)


def _paths_overlap(left: str, right: str) -> bool:
    if not left or not right:
        return False
    if left == right:
        return True
    return left.startswith(f"{right}/") or right.startswith(f"{left}/")
