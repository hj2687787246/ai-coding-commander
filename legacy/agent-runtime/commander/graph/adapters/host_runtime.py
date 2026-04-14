from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from commander.transport.scripts.commander_host_runtime import (
    HOST_SESSION_FAILED,
    HOST_SESSION_PENDING_LAUNCH,
    HOST_SESSION_WAITING_WORKER,
    assign_reusable_host_session_to_task,
    create_host_session,
    list_host_session_reuse_candidates,
    record_host_session_launch_result,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class HostRuntimeSessionContext:
    thread_id: str
    task_id: str
    runtime_root: str
    provider_id: str
    provider_label: str
    launch_prompt: str
    provider_notes: list[str]
    launch_bundle_paths: dict[str, str]
    launch_bundle: dict[str, Any] | None = None
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
    launcher_config: dict[str, Any] | None = None


class HostRuntimeAdapter(Protocol):
    adapter_id: str

    def create_or_attach_session(
        self,
        session_context: HostRuntimeSessionContext,
    ) -> dict[str, Any]:
        """Create or reuse a managed host session for an external worker."""


class ExternalWindowHostRuntimeAdapter:
    adapter_id = "external-window"

    def create_or_attach_session(
        self,
        session_context: HostRuntimeSessionContext,
    ) -> dict[str, Any]:
        if session_context.reuse_allowed:
            candidates = list_host_session_reuse_candidates(
                session_context.runtime_root,
                provider_id=session_context.provider_id,
                worker_profile=session_context.worker_profile,
                tool_profile=session_context.tool_profile,
                allowed_tools=list(session_context.allowed_tools),
                owned_paths=list(session_context.owned_paths),
            )
            reusable_sessions = [
                candidate
                for candidate in candidates.get("candidates", [])
                if bool(candidate.get("can_accept_new_task"))
            ]
            if reusable_sessions:
                session_id = reusable_sessions[0].get("session_id")
                if isinstance(session_id, str) and session_id.strip():
                    return assign_reusable_host_session_to_task(
                        session_context.runtime_root,
                        task_id=session_context.task_id,
                        thread_id=session_context.thread_id,
                        launch_prompt=session_context.launch_prompt,
                        session_id=session_id.strip(),
                        provider_id=session_context.provider_id,
                        worker_profile=session_context.worker_profile,
                        tool_profile=session_context.tool_profile,
                        allowed_tools=list(session_context.allowed_tools),
                        owned_paths=list(session_context.owned_paths),
                        launch_bundle_paths=session_context.launch_bundle_paths,
                        launch_bundle=session_context.launch_bundle,
                        dispatch_idempotency_key=session_context.dispatch_idempotency_key,
                    )
        session = create_host_session(
            session_context.runtime_root,
            thread_id=session_context.thread_id,
            task_id=session_context.task_id,
            provider_id=session_context.provider_id,
            provider_label=session_context.provider_label,
            host_adapter_id=self.adapter_id,
            launch_prompt=session_context.launch_prompt,
            provider_notes=session_context.provider_notes,
            launch_bundle_paths=session_context.launch_bundle_paths,
            launch_bundle=session_context.launch_bundle,
            dispatch_idempotency_key=session_context.dispatch_idempotency_key,
            worker_id=session_context.worker_id,
            worker_profile=session_context.worker_profile,
            preferred_worker_profile=session_context.preferred_worker_profile,
            tool_profile=session_context.tool_profile,
            allowed_tools=list(session_context.allowed_tools),
            forbidden_paths=list(session_context.forbidden_paths),
            owned_paths=list(session_context.owned_paths),
            reuse_allowed=session_context.reuse_allowed,
            dispatch_kind=session_context.dispatch_kind,
            closure_policy=session_context.closure_policy,
            governance=session_context.governance,
            session_status=(
                HOST_SESSION_PENDING_LAUNCH
                if isinstance(session_context.launcher_config, dict)
                else HOST_SESSION_WAITING_WORKER
            ),
        )
        if isinstance(session_context.launcher_config, dict):
            return self._auto_launch_session(session_context, session)
        return session

    def _auto_launch_session(
        self,
        session_context: HostRuntimeSessionContext,
        session: dict[str, Any],
    ) -> dict[str, Any]:
        session_id = session.get("session_id")
        if not isinstance(session_id, str) or not session_id.strip():
            return session
        try:
            launch_result = _launch_external_command(session_context.launcher_config or {})
        except Exception as error:
            return record_host_session_launch_result(
                session_context.runtime_root,
                session_id.strip(),
                launch_status="failed",
                session_status=HOST_SESSION_FAILED,
                launch_result={
                    "started_at": None,
                    "error": str(error),
                },
                note="auto_launch_failed",
            )
        return record_host_session_launch_result(
            session_context.runtime_root,
            session_id.strip(),
            launch_status="launched",
            session_status=HOST_SESSION_WAITING_WORKER,
            launch_result=launch_result,
            note="auto_launch_started",
        )


def _launch_external_command(launcher_config: dict[str, Any]) -> dict[str, Any]:
    command = launcher_config.get("command")
    if not isinstance(command, list) or not command or not all(
        isinstance(item, str) and item.strip() for item in command
    ):
        raise ValueError("launcher.command must be a non-empty string list")
    resolved_command = [item.strip() for item in command]
    detached = bool(launcher_config.get("detached", True))
    cwd = _resolve_launcher_cwd(launcher_config.get("cwd"))
    env = os.environ.copy()
    raw_env = launcher_config.get("env")
    env_keys: list[str] = []
    if isinstance(raw_env, dict):
        for key, value in raw_env.items():
            if (
                isinstance(key, str)
                and key.strip()
                and isinstance(value, str)
            ):
                normalized_key = key.strip()
                env[normalized_key] = value
                env_keys.append(normalized_key)

    creationflags = 0
    if detached and os.name == "nt":
        creationflags = (
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "DETACHED_PROCESS", 0)
        )
    process = subprocess.Popen(
        resolved_command,
        cwd=str(cwd),
        env=env,
        text=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL if detached else subprocess.PIPE,
        stderr=subprocess.DEVNULL if detached else subprocess.PIPE,
        creationflags=creationflags,
        start_new_session=not detached and os.name != "nt",
    )
    launch_result: dict[str, Any] = {
        "command": resolved_command,
        "cwd": str(cwd),
        "detached": detached,
        "env_keys": sorted(env_keys),
        "started_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "pid": process.pid,
    }
    if detached:
        return launch_result
    stdout, stderr = process.communicate()
    launch_result["returncode"] = process.returncode
    if stdout:
        launch_result["stdout"] = stdout.strip()
    if stderr:
        launch_result["stderr"] = stderr.strip()
    if process.returncode != 0:
        raise RuntimeError(
            f"launcher exited with code {process.returncode}: {(stderr or stdout or '').strip()}"
        )
    return launch_result


def _resolve_launcher_cwd(cwd_value: Any) -> Path:
    if not isinstance(cwd_value, str) or not cwd_value.strip():
        return PROJECT_ROOT
    candidate = Path(cwd_value)
    resolved = (
        (PROJECT_ROOT / candidate).resolve()
        if not candidate.is_absolute()
        else candidate.resolve()
    )
    if resolved != PROJECT_ROOT and PROJECT_ROOT not in resolved.parents:
        raise ValueError("launcher.cwd must stay within the repository")
    return resolved


def get_host_runtime_adapter(adapter_id: str) -> HostRuntimeAdapter:
    normalized = adapter_id.strip().lower()
    if normalized == "external-window":
        return ExternalWindowHostRuntimeAdapter()
    raise ValueError(f"Host runtime adapter {adapter_id!r} is not wired yet")
