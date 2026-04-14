from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


COMMANDER_LOCAL_ALLOWED_PREFIXES: tuple[str, ...] = (
    "AGENTS.md",
    "commander/core",
    "commander/state",
    "commander/outer",
    "commander/skill-source",
)
COMMANDER_LOCAL_IGNORED_PREFIXES: tuple[str, ...] = (
    ".runtime",
    ".pytest_tmp",
    "__pycache__",
    "codex_test/pytest",
    "codex_test/pytest_runs",
)
COMMANDER_LOCAL_IGNORED_PATHS: tuple[str, ...] = (
    "web/tsconfig.node.tsbuildinfo",
)


def collect_repo_status_paths(project_root: str | Path) -> list[str]:
    root = Path(project_root)
    changed_paths = _run_git_path_list(
        root,
        [
            "git",
            "-c",
            "core.quotepath=false",
            "diff",
            "--name-only",
            "--relative",
            "HEAD",
            "--",
        ],
    )
    for path in _run_git_path_list(
        root,
        [
            "git",
            "-c",
            "core.quotepath=false",
            "ls-files",
            "--others",
            "--exclude-standard",
        ],
    ):
        if path not in changed_paths:
            changed_paths.append(path)
    return changed_paths


def build_commander_role_guard_report(
    changed_files: Any,
    *,
    enabled: bool,
    allowed_prefixes: tuple[str, ...] = COMMANDER_LOCAL_ALLOWED_PREFIXES,
    ignored_prefixes: tuple[str, ...] = COMMANDER_LOCAL_IGNORED_PREFIXES,
    ignored_paths: tuple[str, ...] = COMMANDER_LOCAL_IGNORED_PATHS,
) -> dict[str, Any]:
    normalized_changed = _normalize_repo_path_list(changed_files)
    allowed_hits: list[str] = []
    ignored_hits: list[str] = []
    violation_paths: list[str] = []

    for changed_path in normalized_changed:
        if _is_exact_or_nested_match(changed_path, ignored_paths) or _is_prefix_match(
            changed_path, ignored_prefixes
        ):
            ignored_hits.append(changed_path)
            continue
        if _is_exact_or_nested_match(changed_path, allowed_prefixes):
            allowed_hits.append(changed_path)
            continue
        violation_paths.append(changed_path)

    if not enabled:
        reason = "role_guard_disabled_for_non_default_runtime"
    elif violation_paths:
        reason = "commander_local_changes_escape_allowed_doc_surfaces"
    else:
        reason = "commander_local_changes_within_allowed_doc_surfaces"

    return {
        "enabled": enabled,
        "changed_files": list(normalized_changed),
        "allowed_prefixes": list(allowed_prefixes),
        "ignored_prefixes": list(ignored_prefixes),
        "ignored_paths": list(ignored_paths),
        "allowed_local_paths": allowed_hits,
        "ignored_changed_paths": ignored_hits,
        "violation_paths": violation_paths,
        "violation_count": len(violation_paths),
        "ok": (not enabled) or not violation_paths,
        "reason": reason,
    }


def _run_git_path_list(project_root: Path, command: list[str]) -> list[str]:
    try:
        completed = subprocess.run(
            command,
            cwd=project_root,
            text=True,
            capture_output=True,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
    except OSError:
        return []
    if completed.returncode != 0:
        return []
    normalized: list[str] = []
    for raw_line in completed.stdout.splitlines():
        normalized_path = _normalize_repo_path(raw_line)
        if normalized_path and normalized_path not in normalized:
            normalized.append(normalized_path)
    return normalized


def _normalize_repo_path(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if normalized.startswith('"') and normalized.endswith('"') and len(normalized) >= 2:
        normalized = normalized[1:-1]
    normalized = normalized.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    while "//" in normalized:
        normalized = normalized.replace("//", "/")
    normalized = normalized.strip("/")
    return normalized or None


def _normalize_repo_path_list(raw_value: Any) -> tuple[str, ...]:
    if not isinstance(raw_value, (list, tuple)):
        return ()
    values: list[str] = []
    for item in raw_value:
        normalized = _normalize_repo_path(item)
        if normalized and normalized not in values:
            values.append(normalized)
    return tuple(values)


def _is_exact_or_nested_match(path: str, candidates: tuple[str, ...]) -> bool:
    for candidate in candidates:
        if path == candidate or path.startswith(f"{candidate}/"):
            return True
    return False


def _is_prefix_match(path: str, prefixes: tuple[str, ...]) -> bool:
    for prefix in prefixes:
        if path == prefix or path.startswith(f"{prefix}/"):
            return True
    return False
