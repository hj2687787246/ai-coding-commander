from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from commander.graph.runners.run_until_objective_handoff import (
    run_until_objective_handoff,
)
from commander.transport.scripts.commander_harness import (
    _file_lock,
    load_json,
    normalize_runtime_root,
    parse_utc_timestamp,
    refresh_status,
    resolve_task_paths,
    utc_now,
    write_json,
)
from commander.transport.scripts.commander_objective_plan import (
    build_objective_plan_summary,
    load_primary_active_objective_plan_summary,
    reconcile_objective_plan,
)
from commander.transport.scripts.commander_phase_plan import (
    load_primary_active_phase_plan_summary,
    promote_ready_phase_goals,
)


HOST_DAEMON_SCHEMA_VERSION = "commander-host-daemon-v1"
HOST_DAEMON_ID = "primary"
HOST_DAEMON_STATUS_NOT_STARTED = "not_started"
HOST_DAEMON_STATUS_STARTING = "starting"
HOST_DAEMON_STATUS_IDLE = "idle"
HOST_DAEMON_STATUS_RUNNING = "running"
HOST_DAEMON_STATUS_WAITING_EXTERNAL = "waiting_external_result"
HOST_DAEMON_STATUS_WAITING_USER = "waiting_user"
HOST_DAEMON_STATUS_ATTENTION_REQUIRED = "attention_required"
HOST_DAEMON_STATUS_STOPPING = "stopping"
HOST_DAEMON_STATUS_STOPPED = "stopped"
HOST_DAEMON_STATUS_ERROR = "error"

REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class HostDaemonPaths:
    runtime_root: Path
    daemon_dir: Path
    commands_dir: Path
    locks_dir: Path
    state_path: Path
    log_path: Path
    state_lock_path: Path
    command_lock_path: Path


def resolve_host_daemon_paths(runtime_root: str | Path | None) -> HostDaemonPaths:
    resolved_runtime_root = normalize_runtime_root(runtime_root)
    daemon_dir = resolved_runtime_root / "host_daemon"
    locks_dir = daemon_dir / "locks"
    return HostDaemonPaths(
        runtime_root=resolved_runtime_root,
        daemon_dir=daemon_dir,
        commands_dir=daemon_dir / "commands",
        locks_dir=locks_dir,
        state_path=daemon_dir / "daemon_state.json",
        log_path=daemon_dir / "daemon.log.jsonl",
        state_lock_path=locks_dir / "daemon_state.lock",
        command_lock_path=locks_dir / "daemon_commands.lock",
    )


def _default_runtime_config() -> dict[str, Any]:
    return {
        "thread_id": None,
        "task_card_path": None,
        "objective_id": None,
        "task_id": None,
        "checkpoint_db": None,
        "max_objective_rounds": 6,
        "max_graph_rounds": 8,
        "wait_timeout_seconds": 0.0,
        "poll_interval_seconds": 1.0,
        "idle_sleep_seconds": 5.0,
        "wait_sleep_seconds": 2.0,
        "user_sleep_seconds": 5.0,
        "attention_sleep_seconds": 5.0,
    }


def _default_resume_payload() -> dict[str, Any]:
    return {
        "last_open_offer": None,
        "pending_user_reply_target": None,
        "offer_confirmed": None,
        "latest_user_reply_text": None,
    }


def _default_state(runtime_root: Path) -> dict[str, Any]:
    now = utc_now()
    return {
        "schema_version": HOST_DAEMON_SCHEMA_VERSION,
        "daemon_id": HOST_DAEMON_ID,
        "runtime_root": str(runtime_root),
        "status": HOST_DAEMON_STATUS_NOT_STARTED,
        "pid": None,
        "process_alive": False,
        "started_at": None,
        "stopped_at": None,
        "updated_at": now,
        "last_heartbeat_at": None,
        "cycle_count": 0,
        "last_cycle_started_at": None,
        "last_cycle_completed_at": None,
        "last_result": None,
        "last_error": None,
        "last_command": None,
        "runtime_config": _default_runtime_config(),
        "pending_resume_payload": _default_resume_payload(),
        "wait_context": None,
        "logs_path": str(resolve_host_daemon_paths(runtime_root).log_path),
    }


def _merge_runtime_config(
    current: dict[str, Any] | None,
    patch: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = _default_runtime_config()
    if isinstance(current, dict):
        merged.update(current)
    if isinstance(patch, dict):
        for key, value in patch.items():
            if key in merged:
                merged[key] = value
    return merged


def _merge_resume_payload(
    current: dict[str, Any] | None,
    patch: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = _default_resume_payload()
    if isinstance(current, dict):
        merged.update(current)
    if isinstance(patch, dict):
        for key, value in patch.items():
            if key in merged:
                merged[key] = value
    return merged


def load_host_daemon_state(runtime_root: str | Path | None) -> dict[str, Any] | None:
    paths = resolve_host_daemon_paths(runtime_root)
    if not paths.state_path.exists():
        return None
    payload = load_json(paths.state_path)
    return payload if isinstance(payload, dict) else None


def _write_host_daemon_state(
    runtime_root: str | Path | None,
    payload: dict[str, Any],
) -> dict[str, Any]:
    paths = resolve_host_daemon_paths(runtime_root)
    paths.state_path.parent.mkdir(parents=True, exist_ok=True)
    normalized = dict(payload)
    normalized["runtime_root"] = str(paths.runtime_root)
    normalized["logs_path"] = str(paths.log_path)
    normalized["runtime_config"] = _merge_runtime_config(
        normalized.get("runtime_config"),
        None,
    )
    normalized["pending_resume_payload"] = _merge_resume_payload(
        normalized.get("pending_resume_payload"),
        None,
    )
    normalized["updated_at"] = utc_now()
    with _file_lock(paths.state_lock_path, scope="host_daemon_state"):
        write_json(paths.state_path, normalized)
    return normalized


def update_host_daemon_state(
    runtime_root: str | Path | None,
    *,
    patch: dict[str, Any] | None = None,
    runtime_config_patch: dict[str, Any] | None = None,
    resume_payload_patch: dict[str, Any] | None = None,
) -> dict[str, Any]:
    paths = resolve_host_daemon_paths(runtime_root)
    current = load_host_daemon_state(paths.runtime_root) or _default_state(
        paths.runtime_root
    )
    updated = dict(current)
    if isinstance(patch, dict):
        updated.update(patch)
    updated["runtime_config"] = _merge_runtime_config(
        updated.get("runtime_config"),
        runtime_config_patch,
    )
    updated["pending_resume_payload"] = _merge_resume_payload(
        updated.get("pending_resume_payload"),
        resume_payload_patch,
    )
    return _write_host_daemon_state(paths.runtime_root, updated)


def append_host_daemon_log(
    runtime_root: str | Path | None,
    *,
    level: str,
    message: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    paths = resolve_host_daemon_paths(runtime_root)
    paths.log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": utc_now(),
        "level": level,
        "message": message,
        "payload": payload or {},
    }
    with _file_lock(paths.command_lock_path, scope="host_daemon_log"):
        with paths.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def load_host_daemon_logs(
    runtime_root: str | Path | None,
    *,
    limit: int = 40,
) -> dict[str, Any]:
    paths = resolve_host_daemon_paths(runtime_root)
    if not paths.log_path.exists():
        return {
            "runtime_root": str(paths.runtime_root),
            "log_path": str(paths.log_path),
            "line_count": 0,
            "entries": [],
        }
    lines = paths.log_path.read_text(encoding="utf-8").splitlines()
    tail = lines[-max(limit, 1) :]
    entries: list[dict[str, Any]] = []
    for line in tail:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            payload = {"timestamp": None, "level": "raw", "message": line}
        if isinstance(payload, dict):
            entries.append(payload)
    return {
        "runtime_root": str(paths.runtime_root),
        "log_path": str(paths.log_path),
        "line_count": len(lines),
        "entries": entries,
    }


def _command_file_name(command: str) -> str:
    safe_command = "".join(
        ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in command
    )
    return f"{utc_now().replace(':', '').replace('-', '')}-{safe_command}.json"


def enqueue_host_daemon_command(
    runtime_root: str | Path | None,
    *,
    command: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    paths = resolve_host_daemon_paths(runtime_root)
    paths.commands_dir.mkdir(parents=True, exist_ok=True)
    command_payload = {
        "schema_version": HOST_DAEMON_SCHEMA_VERSION,
        "command": command,
        "issued_at": utc_now(),
        "payload": payload or {},
    }
    command_path = paths.commands_dir / _command_file_name(command)
    with _file_lock(paths.command_lock_path, scope="host_daemon_commands"):
        write_json(command_path, command_payload)
    append_host_daemon_log(
        paths.runtime_root,
        level="info",
        message=f"Queued daemon command: {command}",
        payload={"command_path": str(command_path), "payload": payload or {}},
    )
    return {
        "runtime_root": str(paths.runtime_root),
        "command_path": str(command_path),
        "command": command,
        "payload": payload or {},
    }


def _drain_host_daemon_commands(runtime_root: str | Path | None) -> list[dict[str, Any]]:
    paths = resolve_host_daemon_paths(runtime_root)
    if not paths.commands_dir.exists():
        return []
    commands: list[dict[str, Any]] = []
    with _file_lock(paths.command_lock_path, scope="host_daemon_commands"):
        for path in sorted(paths.commands_dir.glob("*.json")):
            payload = load_json(path)
            if isinstance(payload, dict):
                commands.append(payload)
            path.unlink(missing_ok=True)
    return commands


def _pid_is_alive(pid: int | None) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == "nt":
        # Windows does not support POSIX-style os.kill(pid, 0) probing.
        # Use the process query API so a liveness check cannot terminate a process.
        import ctypes
        from ctypes import wintypes

        process_query_limited_information = 0x1000
        still_active = 259
        handle = ctypes.windll.kernel32.OpenProcess(
            process_query_limited_information,
            False,
            pid,
        )
        if not handle:
            return False
        try:
            exit_code = wintypes.DWORD()
            ok = ctypes.windll.kernel32.GetExitCodeProcess(
                handle,
                ctypes.byref(exit_code),
            )
            return bool(ok) and int(exit_code.value) == still_active
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def build_host_daemon_summary(
    runtime_root: str | Path | None,
) -> dict[str, Any]:
    paths = resolve_host_daemon_paths(runtime_root)
    state = load_host_daemon_state(paths.runtime_root) or _default_state(
        paths.runtime_root
    )
    pid = state.get("pid")
    process_alive = _pid_is_alive(pid if isinstance(pid, int) else None)
    heartbeat_age_seconds = None
    heartbeat = parse_utc_timestamp(state.get("last_heartbeat_at"))
    if heartbeat is not None:
        heartbeat_age_seconds = max(int((time.time() - heartbeat.timestamp())), 0)
    pending_command_count = (
        len(list(paths.commands_dir.glob("*.json"))) if paths.commands_dir.exists() else 0
    )
    return {
        "runtime_root": str(paths.runtime_root),
        "daemon_id": state.get("daemon_id"),
        "status": state.get("status"),
        "pid": pid,
        "process_alive": process_alive,
        "started_at": state.get("started_at"),
        "stopped_at": state.get("stopped_at"),
        "updated_at": state.get("updated_at"),
        "last_heartbeat_at": state.get("last_heartbeat_at"),
        "heartbeat_age_seconds": heartbeat_age_seconds,
        "cycle_count": state.get("cycle_count"),
        "last_result": state.get("last_result"),
        "last_error": state.get("last_error"),
        "last_command": state.get("last_command"),
        "wait_context": state.get("wait_context"),
        "runtime_config": state.get("runtime_config"),
        "pending_resume_payload": state.get("pending_resume_payload"),
        "log_path": str(paths.log_path),
        "state_path": str(paths.state_path),
        "pending_command_count": pending_command_count,
    }


def _resolve_runtime_task_id(
    runtime_root: Path,
    runtime_config: dict[str, Any],
) -> str | None:
    configured_task_id = runtime_config.get("task_id")
    resolved_task_id = (
        str(configured_task_id).strip()
        if isinstance(configured_task_id, str) and configured_task_id.strip()
        else None
    )

    def _pick_task_id(task_ids: list[str]) -> str | None:
        preferred_terminal: list[str] = []
        fallback: list[str] = []
        for task_id in task_ids:
            if not isinstance(task_id, str) or not task_id.strip():
                continue
            normalized_task_id = task_id.strip()
            paths = resolve_task_paths(runtime_root, normalized_task_id)
            if not paths.task_dir.exists():
                continue
            snapshot = refresh_status(paths)
            current_phase = str(snapshot.get("current_phase") or "").strip()
            worker_status = str(snapshot.get("worker_status") or "").strip()
            lifecycle_status = str(snapshot.get("lifecycle_status") or "").strip()
            if current_phase in {
                "ready_to_close",
                "needs_commander_decision",
                "pending_user",
                "ready_for_user_delivery",
                "blocked",
            } or worker_status in {"done", "blocked", "need_split"} or lifecycle_status in {
                "closed",
                "archived",
                "canceled",
            }:
                preferred_terminal.append(normalized_task_id)
            fallback.append(normalized_task_id)
        if preferred_terminal:
            return preferred_terminal[0]
        if fallback:
            return fallback[0]
        return None

    objective_id = runtime_config.get("objective_id")
    objective_summary = None
    if isinstance(objective_id, str) and objective_id.strip():
        objective_summary = build_objective_plan_summary(
            runtime_root,
            reconcile_objective_plan(runtime_root, objective_id=objective_id.strip()),
        )
    else:
        objective_summary = load_primary_active_objective_plan_summary(runtime_root)

    if isinstance(objective_summary, dict):
        current_phase = objective_summary.get("current_phase")
        if isinstance(current_phase, dict):
            active_task_ids = current_phase.get("active_task_ids")
            if isinstance(active_task_ids, list):
                preferred_task_id = _pick_task_id(active_task_ids)
                if preferred_task_id is not None:
                    return preferred_task_id
            current_phase_task_id = current_phase.get("current_task_id")
            if isinstance(current_phase_task_id, str) and current_phase_task_id.strip():
                return current_phase_task_id.strip()

    phase_summary = load_primary_active_phase_plan_summary(runtime_root)
    if isinstance(phase_summary, dict):
        current_task_ids = phase_summary.get("current_task_ids")
        if isinstance(current_task_ids, list):
            preferred_task_id = _pick_task_id(current_task_ids)
            if preferred_task_id is not None:
                return preferred_task_id
        current_task_id = phase_summary.get("current_task_id")
        if isinstance(current_task_id, str) and current_task_id.strip():
            return current_task_id.strip()

    return resolved_task_id


def _build_daemon_launch_command(runtime_root: Path) -> list[str]:
    return [
        sys.executable,
        "-m",
        "commander.transport.scripts.commander_host_daemon",
        "run-loop",
        "--runtime-root",
        str(runtime_root),
    ]


def _spawn_detached_process(command: list[str], cwd: Path) -> int:
    kwargs: dict[str, Any] = {
        "cwd": str(cwd),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        creationflags = 0
        creationflags |= int(getattr(subprocess, "DETACHED_PROCESS", 0))
        creationflags |= int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        if creationflags:
            kwargs["creationflags"] = creationflags
        kwargs["close_fds"] = True
    else:
        kwargs["start_new_session"] = True
    process = subprocess.Popen(command, **kwargs)
    return int(process.pid)


def start_host_daemon(
    runtime_root: str | Path | None,
    *,
    thread_id: str | None = None,
    task_card_path: str | None = None,
    objective_id: str | None = None,
    task_id: str | None = None,
    checkpoint_db: str | None = None,
    max_objective_rounds: int = 6,
    max_graph_rounds: int = 8,
    wait_timeout_seconds: float = 0.0,
    poll_interval_seconds: float = 1.0,
    idle_sleep_seconds: float = 5.0,
    wait_sleep_seconds: float = 2.0,
    user_sleep_seconds: float = 5.0,
    attention_sleep_seconds: float = 5.0,
    spawn_fn: Callable[[list[str], Path], int] | None = None,
) -> dict[str, Any]:
    paths = resolve_host_daemon_paths(runtime_root)
    existing = build_host_daemon_summary(paths.runtime_root)
    if existing["process_alive"] and existing["status"] not in {
        HOST_DAEMON_STATUS_STOPPED,
        HOST_DAEMON_STATUS_ERROR,
        HOST_DAEMON_STATUS_NOT_STARTED,
    }:
        return {"status": "already_running", "daemon": existing}

    state = update_host_daemon_state(
        paths.runtime_root,
        patch={
            "schema_version": HOST_DAEMON_SCHEMA_VERSION,
            "daemon_id": HOST_DAEMON_ID,
            "status": HOST_DAEMON_STATUS_STARTING,
            "started_at": utc_now(),
            "stopped_at": None,
            "last_error": None,
            "wait_context": None,
            "last_result": None,
        },
        runtime_config_patch={
            "thread_id": thread_id,
            "task_card_path": task_card_path,
            "objective_id": objective_id,
            "task_id": task_id,
            "checkpoint_db": checkpoint_db,
            "max_objective_rounds": max(max_objective_rounds, 1),
            "max_graph_rounds": max(max_graph_rounds, 1),
            "wait_timeout_seconds": max(wait_timeout_seconds, 0.0),
            "poll_interval_seconds": max(poll_interval_seconds, 0.1),
            "idle_sleep_seconds": max(idle_sleep_seconds, 0.1),
            "wait_sleep_seconds": max(wait_sleep_seconds, 0.1),
            "user_sleep_seconds": max(user_sleep_seconds, 0.1),
            "attention_sleep_seconds": max(attention_sleep_seconds, 0.1),
        },
        resume_payload_patch=_default_resume_payload(),
    )
    launch_command = _build_daemon_launch_command(paths.runtime_root)
    resolved_spawn_fn = spawn_fn or _spawn_detached_process
    pid = resolved_spawn_fn(launch_command, REPO_ROOT)
    state = update_host_daemon_state(
        paths.runtime_root,
        patch={
            "pid": pid,
            "process_alive": True,
            "launch_command": launch_command,
        },
    )
    append_host_daemon_log(
        paths.runtime_root,
        level="info",
        message="Started host daemon process",
        payload={"pid": pid, "launch_command": launch_command},
    )
    return {
        "status": "started",
        "pid": pid,
        "daemon": build_host_daemon_summary(paths.runtime_root),
        "launch_command": launch_command,
        "state": state,
    }


def request_stop_host_daemon(
    runtime_root: str | Path | None,
    *,
    reason: str = "manual_stop",
) -> dict[str, Any]:
    command = enqueue_host_daemon_command(
        runtime_root,
        command="stop",
        payload={"reason": reason},
    )
    daemon = build_host_daemon_summary(runtime_root)
    return {"status": "stop_requested", "command": command, "daemon": daemon}


def request_resume_host_daemon(
    runtime_root: str | Path | None,
    *,
    note: str | None = None,
    last_open_offer: dict[str, Any] | None = None,
    pending_user_reply_target: str | None = None,
    offer_confirmed: bool | None = None,
    latest_user_reply_text: str | None = None,
) -> dict[str, Any]:
    command = enqueue_host_daemon_command(
        runtime_root,
        command="resume",
        payload={
            "note": note,
            "last_open_offer": last_open_offer,
            "pending_user_reply_target": pending_user_reply_target,
            "offer_confirmed": offer_confirmed,
            "latest_user_reply_text": latest_user_reply_text,
        },
    )
    daemon = build_host_daemon_summary(runtime_root)
    return {"status": "resume_requested", "command": command, "daemon": daemon}


def _summarize_result(result: dict[str, Any]) -> dict[str, Any]:
    final_handoff_result = (
        result.get("final_handoff_result")
        if isinstance(result.get("final_handoff_result"), dict)
        else None
    )
    return {
        "driver_status": result.get("driver_status"),
        "stop_reason": result.get("stop_reason"),
        "objective_id": result.get("objective_id"),
        "task_id": result.get("task_id"),
        "objective_round_count": result.get("objective_round_count"),
        "final_handoff_driver_status": (
            final_handoff_result.get("driver_status")
            if isinstance(final_handoff_result, dict)
            else None
        ),
        "final_handoff_stop_reason": (
            final_handoff_result.get("stop_reason")
            if isinstance(final_handoff_result, dict)
            else None
        ),
        "wait_monitor": (
            final_handoff_result.get("wait_monitor")
            if isinstance(final_handoff_result, dict)
            else None
        ),
    }


def _derive_cycle_outcome(
    result: dict[str, Any],
    *,
    runtime_config: dict[str, Any],
) -> tuple[str, float, bool]:
    driver_status = str(result.get("driver_status") or "").strip()
    stop_reason = str(result.get("stop_reason") or "").strip()
    if driver_status == "waiting_external_result":
        return (
            HOST_DAEMON_STATUS_WAITING_EXTERNAL,
            float(runtime_config.get("wait_sleep_seconds") or 2.0),
            False,
        )
    if stop_reason == "user_handoff":
        return (
            HOST_DAEMON_STATUS_WAITING_USER,
            float(runtime_config.get("user_sleep_seconds") or 5.0),
            True,
        )
    if driver_status in {
        "paused_no_progress",
        "max_rounds_exhausted",
        "max_objective_rounds_exhausted",
    }:
        return (
            HOST_DAEMON_STATUS_ATTENTION_REQUIRED,
            float(runtime_config.get("attention_sleep_seconds") or 5.0),
            True,
        )
    if (
        driver_status in {"stopped", "completed_without_handoff"}
        and stop_reason == "terminal"
    ):
        return (
            HOST_DAEMON_STATUS_IDLE,
            float(runtime_config.get("idle_sleep_seconds") or 5.0),
            False,
        )
    return (
        HOST_DAEMON_STATUS_RUNNING,
        float(runtime_config.get("idle_sleep_seconds") or 5.0),
        False,
    )


def run_host_daemon_cycle(
    runtime_root: str | Path | None,
    *,
    objective_runner: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    paths = resolve_host_daemon_paths(runtime_root)
    state = load_host_daemon_state(paths.runtime_root) or _default_state(paths.runtime_root)
    runtime_config = _merge_runtime_config(state.get("runtime_config"), None)
    resume_payload = _merge_resume_payload(state.get("pending_resume_payload"), None)
    phase_prefill: dict[str, Any] | None = None
    phase_summary = load_primary_active_phase_plan_summary(paths.runtime_root)
    if isinstance(phase_summary, dict):
        available_parallel_slots = int(phase_summary.get("available_parallel_slots") or 0)
        if available_parallel_slots > 0:
            phase_prefill = promote_ready_phase_goals(
                paths.runtime_root,
                phase_id=str(phase_summary["phase_id"]),
                max_promotions=available_parallel_slots,
            )
            if phase_prefill.get("promoted_goal_ids"):
                append_host_daemon_log(
                    paths.runtime_root,
                    level="info",
                    message="Prefilled parallel phase slots",
                    payload={
                        "phase_id": phase_summary.get("phase_id"),
                        "promoted_goal_ids": phase_prefill.get("promoted_goal_ids"),
                    },
                )
    resolved_task_id = _resolve_runtime_task_id(paths.runtime_root, runtime_config)
    if resolved_task_id != runtime_config.get("task_id"):
        runtime_config = dict(runtime_config)
        runtime_config["task_id"] = resolved_task_id
    started_at = utc_now()
    state = update_host_daemon_state(
        paths.runtime_root,
        patch={
            "status": HOST_DAEMON_STATUS_RUNNING,
            "last_cycle_started_at": started_at,
            "last_heartbeat_at": started_at,
            "process_alive": True,
        },
    )

    runner = objective_runner or run_until_objective_handoff
    result = runner(
        thread_id=runtime_config.get("thread_id"),
        runtime_root=str(paths.runtime_root),
        task_card_path=runtime_config.get("task_card_path"),
        objective_id=runtime_config.get("objective_id"),
        task_id=runtime_config.get("task_id"),
        checkpoint_db=runtime_config.get("checkpoint_db"),
        last_open_offer=resume_payload.get("last_open_offer"),
        pending_user_reply_target=resume_payload.get("pending_user_reply_target"),
        offer_confirmed=resume_payload.get("offer_confirmed"),
        latest_user_reply_text=resume_payload.get("latest_user_reply_text"),
        max_objective_rounds=int(runtime_config.get("max_objective_rounds") or 6),
        max_graph_rounds=int(runtime_config.get("max_graph_rounds") or 8),
        wait_timeout_seconds=float(runtime_config.get("wait_timeout_seconds") or 0.0),
        poll_interval_seconds=float(runtime_config.get("poll_interval_seconds") or 1.0),
    )
    status, sleep_seconds, waiting_for_resume = _derive_cycle_outcome(
        result,
        runtime_config=runtime_config,
    )
    last_result = _summarize_result(result)
    last_task_id = result.get("task_id")
    wait_context = last_result.get("wait_monitor")
    state = update_host_daemon_state(
        paths.runtime_root,
        patch={
            "status": status,
            "cycle_count": int(state.get("cycle_count") or 0) + 1,
            "last_cycle_completed_at": utc_now(),
            "last_heartbeat_at": utc_now(),
            "last_result": last_result,
            "last_error": None,
            "wait_context": wait_context,
        },
        runtime_config_patch={
            "task_id": last_task_id or runtime_config.get("task_id"),
        },
        resume_payload_patch=_default_resume_payload(),
    )
    append_host_daemon_log(
        paths.runtime_root,
        level="info",
        message="Completed host daemon cycle",
        payload={"status": status, "result": last_result},
    )
    return {
        "runtime_root": str(paths.runtime_root),
        "daemon_state": state,
        "result": result,
        "phase_prefill": phase_prefill,
        "sleep_seconds": sleep_seconds,
        "waiting_for_resume": waiting_for_resume,
    }


def _apply_host_daemon_commands(
    runtime_root: str | Path | None,
    commands: list[dict[str, Any]],
) -> dict[str, Any]:
    paths = resolve_host_daemon_paths(runtime_root)
    state = load_host_daemon_state(paths.runtime_root) or _default_state(paths.runtime_root)
    stop_requested = False
    for command in commands:
        command_name = str(command.get("command") or "").strip()
        payload = command.get("payload") if isinstance(command.get("payload"), dict) else {}
        state = update_host_daemon_state(
            paths.runtime_root,
            patch={
                "last_command": {
                    "command": command_name,
                    "issued_at": command.get("issued_at"),
                    "payload": payload,
                },
                "last_heartbeat_at": utc_now(),
            },
        )
        if command_name == "stop":
            stop_requested = True
            state = update_host_daemon_state(
                paths.runtime_root,
                patch={"status": HOST_DAEMON_STATUS_STOPPING},
            )
            append_host_daemon_log(
                paths.runtime_root,
                level="info",
                message="Received host daemon stop command",
                payload=payload,
            )
        elif command_name == "resume":
            state = update_host_daemon_state(
                paths.runtime_root,
                patch={"status": HOST_DAEMON_STATUS_RUNNING},
                resume_payload_patch={
                    "last_open_offer": payload.get("last_open_offer"),
                    "pending_user_reply_target": payload.get("pending_user_reply_target"),
                    "offer_confirmed": payload.get("offer_confirmed"),
                    "latest_user_reply_text": payload.get("latest_user_reply_text"),
                },
            )
            append_host_daemon_log(
                paths.runtime_root,
                level="info",
                message="Received host daemon resume command",
                payload=payload,
            )
    return {"stop_requested": stop_requested, "state": state}


def process_host_daemon_commands_once(
    runtime_root: str | Path | None,
) -> dict[str, Any]:
    commands = _drain_host_daemon_commands(runtime_root)
    result = _apply_host_daemon_commands(runtime_root, commands)
    return {"processed_command_count": len(commands), **result}


def run_host_daemon_loop(
    runtime_root: str | Path | None,
    *,
    max_cycles: int | None = None,
) -> dict[str, Any]:
    paths = resolve_host_daemon_paths(runtime_root)
    state = update_host_daemon_state(
        paths.runtime_root,
        patch={
            "status": HOST_DAEMON_STATUS_RUNNING,
            "last_heartbeat_at": utc_now(),
            "process_alive": True,
            "pid": os.getpid(),
        },
    )
    append_host_daemon_log(
        paths.runtime_root,
        level="info",
        message="Host daemon loop started",
        payload={"pid": os.getpid()},
    )
    completed_cycles = 0
    try:
        while True:
            command_result = _apply_host_daemon_commands(
                paths.runtime_root,
                _drain_host_daemon_commands(paths.runtime_root),
            )
            state = command_result["state"]
            if command_result["stop_requested"]:
                state = update_host_daemon_state(
                    paths.runtime_root,
                    patch={
                        "status": HOST_DAEMON_STATUS_STOPPED,
                        "stopped_at": utc_now(),
                        "last_heartbeat_at": utc_now(),
                        "process_alive": False,
                    },
                )
                append_host_daemon_log(
                    paths.runtime_root,
                    level="info",
                    message="Host daemon loop stopped by command",
                )
                return {
                    "status": "stopped",
                    "daemon": build_host_daemon_summary(paths.runtime_root),
                    "state": state,
                }

            status = str(state.get("status") or "").strip()
            if status in {
                HOST_DAEMON_STATUS_WAITING_USER,
                HOST_DAEMON_STATUS_ATTENTION_REQUIRED,
            }:
                sleep_seconds = float(
                    state.get("runtime_config", {}).get(
                        "user_sleep_seconds"
                        if status == HOST_DAEMON_STATUS_WAITING_USER
                        else "attention_sleep_seconds",
                        5.0,
                    )
                )
                state = update_host_daemon_state(
                    paths.runtime_root,
                    patch={"last_heartbeat_at": utc_now(), "process_alive": True},
                )
                time.sleep(max(sleep_seconds, 0.1))
                continue

            cycle_result = run_host_daemon_cycle(paths.runtime_root)
            completed_cycles += 1
            if (
                isinstance(max_cycles, int)
                and max_cycles > 0
                and completed_cycles >= max_cycles
            ):
                return {
                    "status": "max_cycles_reached",
                    "completed_cycles": completed_cycles,
                    "daemon": build_host_daemon_summary(paths.runtime_root),
                    "last_cycle": {
                        "status": cycle_result["daemon_state"].get("status"),
                        "sleep_seconds": cycle_result["sleep_seconds"],
                        "last_result": cycle_result["daemon_state"].get("last_result"),
                        "waiting_for_resume": cycle_result["waiting_for_resume"],
                    },
                }
            time.sleep(max(float(cycle_result["sleep_seconds"]), 0.1))
    except Exception as exc:
        state = update_host_daemon_state(
            paths.runtime_root,
            patch={
                "status": HOST_DAEMON_STATUS_ERROR,
                "last_error": {"message": str(exc), "type": exc.__class__.__name__},
                "last_heartbeat_at": utc_now(),
                "process_alive": False,
            },
        )
        append_host_daemon_log(
            paths.runtime_root,
            level="error",
            message="Host daemon loop crashed",
            payload=state.get("last_error"),
        )
        raise


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Persistent host daemon for the commander runtime.",
    )
    parser.add_argument("--runtime-root", default=None, help="Override runtime root")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_loop_parser = subparsers.add_parser("run-loop")
    run_loop_parser.add_argument("--max-cycles", type=int, default=None)

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--log-limit", type=int, default=20)

    logs_parser = subparsers.add_parser("logs")
    logs_parser.add_argument("--limit", type=int, default=40)

    stop_parser = subparsers.add_parser("stop")
    stop_parser.add_argument("--reason", default="manual_stop")

    resume_parser = subparsers.add_parser("resume")
    resume_parser.add_argument("--note", default=None)
    resume_parser.add_argument("--last-open-offer-json", default=None)
    resume_parser.add_argument("--pending-user-reply-target", default=None)
    resume_parser.add_argument("--offer-confirmed", action="store_true")
    resume_parser.add_argument("--latest-user-reply-text", default=None)

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "run-loop":
        payload = run_host_daemon_loop(
            args.runtime_root,
            max_cycles=args.max_cycles,
        )
    elif args.command == "status":
        payload = build_host_daemon_summary(args.runtime_root)
        payload["logs"] = load_host_daemon_logs(args.runtime_root, limit=args.log_limit)
    elif args.command == "logs":
        payload = load_host_daemon_logs(args.runtime_root, limit=args.limit)
    elif args.command == "stop":
        payload = request_stop_host_daemon(
            args.runtime_root,
            reason=args.reason,
        )
    elif args.command == "resume":
        payload = request_resume_host_daemon(
            args.runtime_root,
            note=args.note,
            last_open_offer=(
                json.loads(args.last_open_offer_json)
                if args.last_open_offer_json
                else None
            ),
            pending_user_reply_target=args.pending_user_reply_target,
            offer_confirmed=True if args.offer_confirmed else None,
            latest_user_reply_text=args.latest_user_reply_text,
        )
    else:
        raise SystemExit(f"Unsupported command: {args.command}")

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
