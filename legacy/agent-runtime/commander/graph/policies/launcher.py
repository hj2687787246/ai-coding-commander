from __future__ import annotations

from typing import Any

from commander.graph.adapters.worker_providers.base import WorkerLauncherPreset


LAUNCHER_PRESETS: dict[str, WorkerLauncherPreset] = {
    "codex-cli": WorkerLauncherPreset(
        preset_id="codex-cli",
        label="Codex CLI",
        command=("codex",),
        detached=True,
        notes=("Default Codex CLI launcher preset for external-window sessions.",),
    ),
    "claude-code-cli": WorkerLauncherPreset(
        preset_id="claude-code-cli",
        label="Claude Code CLI",
        command=("claude",),
        detached=True,
        notes=("Default Claude Code launcher preset for external-window sessions.",),
    ),
    "qwen-cli": WorkerLauncherPreset(
        preset_id="qwen-cli",
        label="Qwen CLI",
        command=("qwen",),
        detached=True,
        notes=("Default Qwen launcher preset for external-window sessions.",),
    ),
    "doubao-cli": WorkerLauncherPreset(
        preset_id="doubao-cli",
        label="Doubao CLI",
        command=("doubao",),
        detached=True,
        notes=("Default Doubao launcher preset for external-window sessions.",),
    ),
}


def resolve_launcher_preset(
    provider_id: str,
    preset_id: str,
    *,
    args: Any = None,
    cwd: Any = None,
    env: Any = None,
    detached: Any = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    from commander.graph.adapters.worker_providers.registry import (
        get_worker_provider_metadata,
    )

    provider = get_worker_provider_metadata(provider_id)
    normalized_preset_id = preset_id.strip().lower()
    if normalized_preset_id not in provider.supported_launcher_presets:
        raise ValueError(
            f"provider {provider.provider_id!r} does not support launcher preset {preset_id!r}"
        )
    try:
        preset = LAUNCHER_PRESETS[normalized_preset_id]
    except KeyError as error:
        raise ValueError(f"launcher preset {preset_id!r} is not registered") from error

    normalized_args = _normalize_string_list(args)
    launcher_config: dict[str, Any] = {
        "command": [*preset.command, *normalized_args],
        "detached": (
            bool(detached) if isinstance(detached, bool) else bool(preset.detached)
        ),
    }
    summary: dict[str, Any] = {
        "preset_id": preset.preset_id,
        "label": preset.label,
        "command": launcher_config["command"],
        "detached": launcher_config["detached"],
        "env_keys": [],
        "notes": list(preset.notes),
    }

    if isinstance(cwd, str) and cwd.strip():
        launcher_config["cwd"] = cwd.strip()
        summary["cwd"] = cwd.strip()

    normalized_env = _normalize_env(env)
    if normalized_env:
        launcher_config["env"] = normalized_env
        summary["env_keys"] = sorted(normalized_env)

    return launcher_config, summary


def _normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _normalize_env(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, str] = {}
    for key, item in value.items():
        if (
            isinstance(key, str)
            and key.strip()
            and isinstance(item, str)
        ):
            normalized[key.strip()] = item
    return normalized
