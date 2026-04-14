from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from commander.graph.policies import build_intent_binding_state


COMMANDER_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = COMMANDER_ROOT.parent
SCHEMA_DIR = COMMANDER_ROOT / "transport" / "schemas"
DEFAULT_RUNTIME_ROOT = PROJECT_ROOT / ".runtime" / "commander"
PACKET_SCHEMA_PATH = SCHEMA_DIR / "commander_task_packet.schema.json"
REPORT_SCHEMA_PATH = SCHEMA_DIR / "commander_task_report.schema.json"
IMPROVEMENT_SCHEMA_PATH = SCHEMA_DIR / "commander_improvement_candidate.schema.json"
WORKER_SLOT_SCHEMA_PATH = SCHEMA_DIR / "commander_worker_slot.schema.json"
REPORT_STATUSES = ("done", "blocked", "need_split")
DISPATCH_KIND_FRESH = "fresh"
DISPATCH_KIND_FOLLOWUP = "followup"
DISPATCH_KIND_SPLIT = "split"
DISPATCH_KIND_REOPEN = "reopen"
DISPATCH_KIND_RECONCILE = "reconcile"
DISPATCH_KINDS = (
    DISPATCH_KIND_FRESH,
    DISPATCH_KIND_FOLLOWUP,
    DISPATCH_KIND_SPLIT,
    DISPATCH_KIND_REOPEN,
    DISPATCH_KIND_RECONCILE,
)
CLOSURE_POLICY_CLOSE_WHEN_VALIDATED = "close_when_validated"
CLOSURE_POLICY_REQUIRE_COMMANDER_REVIEW = "require_commander_review"
CLOSURE_POLICY_RETURN_FOR_USER_DELIVERY = "return_for_user_delivery"
CLOSURE_POLICIES = (
    CLOSURE_POLICY_CLOSE_WHEN_VALIDATED,
    CLOSURE_POLICY_REQUIRE_COMMANDER_REVIEW,
    CLOSURE_POLICY_RETURN_FOR_USER_DELIVERY,
)
RESULT_GRADE_CLOSED = "closed"
RESULT_GRADE_PARTIAL = "partial"
RESULT_GRADE_BLOCKED = "blocked"
RESULT_GRADES = (
    RESULT_GRADE_CLOSED,
    RESULT_GRADE_PARTIAL,
    RESULT_GRADE_BLOCKED,
)
NEXT_ACTION_OWNER_COMMANDER = "commander"
NEXT_ACTION_OWNER_USER = "user"
NEXT_ACTION_OWNER_WORKER = "worker"
NEXT_ACTION_OWNERS = (
    NEXT_ACTION_OWNER_COMMANDER,
    NEXT_ACTION_OWNER_USER,
    NEXT_ACTION_OWNER_WORKER,
)
CONTINUATION_MODE_CLOSE = "close"
CONTINUATION_MODE_FOLLOWUP = "followup"
CONTINUATION_MODE_SPLIT = "split"
CONTINUATION_MODE_WAIT_USER = "wait_user"
CONTINUATION_MODES = (
    CONTINUATION_MODE_CLOSE,
    CONTINUATION_MODE_FOLLOWUP,
    CONTINUATION_MODE_SPLIT,
    CONTINUATION_MODE_WAIT_USER,
)
REPORT_DRAFT_MARKERS = ("待执行窗口填写", "待填写")
REPORT_DRAFT_METADATA_FIELD = "harness_metadata"
REPORT_DRAFT_METADATA_FLAG = "is_dispatch_draft"
COMPACTION_EVENT_SCHEMA_VERSION = "commander-compaction-event-v1"
COMPACTION_ARTIFACT_SCHEMA_VERSION = "commander-compaction-artifact-v1"
TASK_LIFECYCLE_ACTIVE = "active"
TASK_LIFECYCLE_CLOSED = "closed"
TASK_LIFECYCLE_ARCHIVED = "archived"
TASK_LIFECYCLE_STALE = "stale"
TASK_LIFECYCLE_CANCELED = "canceled"
TASK_LIFECYCLE_STATUSES = (
    TASK_LIFECYCLE_ACTIVE,
    TASK_LIFECYCLE_CLOSED,
    TASK_LIFECYCLE_ARCHIVED,
    TASK_LIFECYCLE_STALE,
    TASK_LIFECYCLE_CANCELED,
)
DEFAULT_STALE_AFTER_HOURS = 24
DEFAULT_ARCHIVE_RETENTION_DAYS = 7
DEFAULT_WORKER_LEASE_SECONDS = 1800
DEFAULT_WORKER_LOCK_TIMEOUT_SECONDS = 5
DEFAULT_WORKER_LOCK_STALE_SECONDS = 30
DEFAULT_CONTEXT_ROUND_BUDGET_TOKENS = 12000
CONTEXT_ROUND_BUDGET_ENV = "COMMANDER_CONTEXT_ROUND_BUDGET_TOKENS"
CONTEXT_ACCOUNT_WINDOW_BUDGET_ENV = "COMMANDER_CONTEXT_ACCOUNT_WINDOW_BUDGET_TOKENS"
ACTIVE_SUBAGENT_RUNNING = "running"
ACTIVE_SUBAGENT_COMPLETED_WAITING_CLOSE = "completed_waiting_close"
ACTIVE_SUBAGENT_BLOCKED = "blocked"
ACTIVE_SUBAGENT_CLOSED = "closed"
ACTIVE_SUBAGENT_OPEN_STATES = (
    ACTIVE_SUBAGENT_RUNNING,
    ACTIVE_SUBAGENT_BLOCKED,
    ACTIVE_SUBAGENT_COMPLETED_WAITING_CLOSE,
)
ACTIVE_SUBAGENT_WARNING_ACTION = "reconcile_active_subagents"
CONTROLLER_HANDOFF_CONTINUE = "continue"
CONTROLLER_HANDOFF_WAIT_EXTERNAL_RESULT = "wait_external_result"
CONTROLLER_HANDOFF_REQUEST_USER_DECISION = "request_user_decision"
CONTROLLER_HANDOFF_RETURN_FINAL_RESULT = "return_final_result"
WORKER_SLOT_WARM_IDLE = "warm_idle"
WORKER_SLOT_BUSY = "busy"
WORKER_SLOT_COMPLETED_WAITING_CLOSE = "completed_waiting_close"
WORKER_SLOT_CLOSED = "closed"
WORKER_SLOT_LEASED_STATES = (
    WORKER_SLOT_BUSY,
    WORKER_SLOT_COMPLETED_WAITING_CLOSE,
)
WORKER_SLOT_RELEASE_STATES = (
    WORKER_SLOT_WARM_IDLE,
    WORKER_SLOT_COMPLETED_WAITING_CLOSE,
    WORKER_SLOT_CLOSED,
)
WORKER_SLOT_RELEASE_ALLOWED_FROM_STATES = (
    WORKER_SLOT_BUSY,
    WORKER_SLOT_COMPLETED_WAITING_CLOSE,
)
CATALOG_REFRESHABLE_TYPES = {
    "task_dispatched",
    "task_report_ingested",
    "task_closed",
    "task_archived",
    "task_stale_marked",
    "task_reopened",
    "task_canceled",
}
CATALOG_REFRESH_STATUS_NEVER_ATTEMPTED = "never_attempted"
CATALOG_REFRESH_STATUS_SYNCED = "synced"
CATALOG_REFRESH_STATUS_FAILED = "failed"
CATALOG_REFRESH_STATUS_SKIPPED = "skipped"


class SchemaValidationError(ValueError):
    """Raised when a JSON document does not satisfy the local schema contract."""


@dataclass(frozen=True)
class TaskPaths:
    task_id: str
    runtime_root: Path
    task_dir: Path
    compactions_dir: Path
    packet_path: Path
    context_bundle_path: Path
    worker_brief_path: Path
    worker_report_path: Path
    report_path: Path
    improvement_candidate_path: Path
    catalog_refresh_path: Path
    reports_dir: Path
    events_path: Path
    lifecycle_path: Path
    status_path: Path
    checkpoint_path: Path
    resume_anchor_path: Path
    compaction_event_path: Path


@dataclass(frozen=True)
class WorkerPoolPaths:
    pool_dir: Path
    slots_dir: Path
    locks_dir: Path
    registry_path: Path
    pool_lock_path: Path


@dataclass(frozen=True)
class WorkerSlotPaths:
    worker_id: str
    slot_path: Path
    lock_path: Path


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def utc_after(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=max(seconds, 0))).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Any:
    last_error: json.JSONDecodeError | None = None
    for attempt in range(3):
        text = path.read_text(encoding="utf-8-sig")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            last_error = exc
            if text.strip() and attempt == 2:
                raise
            time.sleep(0.02)
    assert last_error is not None
    raise last_error


def write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
    try:
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    return path


def _load_positive_int_env(name: str) -> int | None:
    raw_value = os.getenv(name)
    if raw_value is None:
        return None
    try:
        value = int(raw_value)
    except ValueError:
        return None
    return value if value > 0 else None


def resolve_context_budget_tokens() -> tuple[int, int | None]:
    round_budget = (
        _load_positive_int_env(CONTEXT_ROUND_BUDGET_ENV)
        or DEFAULT_CONTEXT_ROUND_BUDGET_TOKENS
    )
    account_window_budget = _load_positive_int_env(CONTEXT_ACCOUNT_WINDOW_BUDGET_ENV)
    return round_budget, account_window_budget


def estimate_text_tokens(text: str) -> int:
    if not text:
        return 0
    ascii_chars = sum(1 for char in text if ord(char) < 128)
    non_ascii_chars = len(text) - ascii_chars
    return ((ascii_chars + 3) // 4) + non_ascii_chars


def _budget_percent(tokens: int, budget_tokens: int | None) -> float | None:
    if budget_tokens is None or budget_tokens <= 0:
        return None
    return round((tokens / budget_tokens) * 100, 2)


def describe_token_artifact_from_text(
    *,
    artifact_key: str,
    label: str,
    kind: str,
    text: str,
    path: str | Path | None = None,
) -> dict[str, Any]:
    normalized_path = str(path) if path is not None else None
    return {
        "artifact_key": artifact_key,
        "label": label,
        "kind": kind,
        "path": normalized_path,
        "exists": True,
        "estimated_tokens": estimate_text_tokens(text),
        "byte_count": len(text.encode("utf-8")),
        "estimation_source": "text_payload",
    }


def describe_token_artifact_from_path(
    path: str | Path,
    *,
    label: str | None = None,
    kind: str = "file_path",
) -> dict[str, Any]:
    normalized_path = str(Path(path))
    candidate = Path(path)
    if not candidate.exists():
        return {
            "artifact_key": normalized_path,
            "label": label or candidate.name or normalized_path,
            "kind": kind,
            "path": normalized_path,
            "exists": False,
            "estimated_tokens": 0,
            "byte_count": 0,
            "estimation_source": "missing_path",
        }
    raw_bytes = candidate.read_bytes()
    try:
        text = raw_bytes.decode("utf-8-sig")
        estimated_tokens = estimate_text_tokens(text)
        estimation_source = "utf8_text"
    except UnicodeDecodeError:
        estimated_tokens = max((len(raw_bytes) + 3) // 4, 1)
        estimation_source = "binary_fallback"
    return {
        "artifact_key": normalized_path,
        "label": label or candidate.name or normalized_path,
        "kind": kind,
        "path": normalized_path,
        "exists": True,
        "estimated_tokens": estimated_tokens,
        "byte_count": len(raw_bytes),
        "estimation_source": estimation_source,
    }


def build_token_budget_estimate(
    *,
    scope: str,
    open_now_artifacts: list[dict[str, Any]],
    deferred_artifacts: list[dict[str, Any]],
) -> dict[str, Any]:
    round_budget_tokens, account_window_budget_tokens = resolve_context_budget_tokens()
    deduped_open_now: list[dict[str, Any]] = []
    deduped_deferred: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

    for artifact in open_now_artifacts:
        artifact_key = str(artifact.get("artifact_key") or "").strip()
        if not artifact_key or artifact_key in seen_keys:
            continue
        deduped_open_now.append(artifact)
        seen_keys.add(artifact_key)

    for artifact in deferred_artifacts:
        artifact_key = str(artifact.get("artifact_key") or "").strip()
        if not artifact_key or artifact_key in seen_keys:
            continue
        deduped_deferred.append(artifact)
        seen_keys.add(artifact_key)

    open_now_tokens = sum(
        int(artifact.get("estimated_tokens") or 0) for artifact in deduped_open_now
    )
    deferred_tokens = sum(
        int(artifact.get("estimated_tokens") or 0) for artifact in deduped_deferred
    )
    full_expand_tokens = open_now_tokens + deferred_tokens
    largest_artifacts = sorted(
        [*deduped_open_now, *deduped_deferred],
        key=lambda artifact: int(artifact.get("estimated_tokens") or 0),
        reverse=True,
    )[:5]

    return {
        "scope": scope,
        "estimation_mode": "heuristic_non_metered",
        "note": (
            "Estimated from current text and file artifacts inside the repo/runtime; "
            "this is not the Codex client or Plus quota meter."
        ),
        "round_budget_tokens": round_budget_tokens,
        "account_window_budget_tokens": account_window_budget_tokens,
        "open_now_estimated_tokens": open_now_tokens,
        "deferred_estimated_tokens": deferred_tokens,
        "full_expand_estimated_tokens": full_expand_tokens,
        "open_now_percent_of_round_budget": _budget_percent(
            open_now_tokens, round_budget_tokens
        ),
        "full_expand_percent_of_round_budget": _budget_percent(
            full_expand_tokens, round_budget_tokens
        ),
        "open_now_percent_of_account_window_budget": _budget_percent(
            open_now_tokens, account_window_budget_tokens
        ),
        "full_expand_percent_of_account_window_budget": _budget_percent(
            full_expand_tokens, account_window_budget_tokens
        ),
        "artifacts_read_now": deduped_open_now,
        "artifacts_deferred": deduped_deferred,
        "largest_artifacts": largest_artifacts,
    }


def _lock_payload(*, scope: str, owner_id: str, stale_after_seconds: int) -> dict[str, Any]:
    return {
        "schema_version": "commander-harness-v1",
        "scope": scope,
        "owner_id": owner_id,
        "acquired_at": utc_now(),
        "stale_after_seconds": max(int(stale_after_seconds), 1),
        "expires_at": utc_after(max(int(stale_after_seconds), 1)),
    }


def _load_lock_payload(lock_path: Path) -> dict[str, Any] | None:
    if not lock_path.exists():
        return None
    try:
        payload = load_json(lock_path)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _is_lock_stale(payload: dict[str, Any] | None, *, now: datetime | None = None) -> bool:
    if not isinstance(payload, dict):
        return True
    expires_at = parse_utc_timestamp(payload.get("expires_at"))
    if expires_at is None:
        acquired_at = parse_utc_timestamp(payload.get("acquired_at"))
        stale_after_seconds = payload.get("stale_after_seconds")
        if acquired_at is None or not isinstance(stale_after_seconds, int):
            return True
        expires_at = acquired_at + timedelta(seconds=max(stale_after_seconds, 1))
    comparison_time = now or datetime.now(timezone.utc)
    return comparison_time >= expires_at


@contextmanager
def _file_lock(
    lock_path: Path,
    *,
    scope: str,
    timeout_seconds: int = DEFAULT_WORKER_LOCK_TIMEOUT_SECONDS,
    stale_after_seconds: int = DEFAULT_WORKER_LOCK_STALE_SECONDS,
) -> Any:
    owner_id = uuid4().hex
    timeout_seconds = max(int(timeout_seconds), 0)
    stale_after_seconds = max(int(stale_after_seconds), 1)
    deadline = time.monotonic() + timeout_seconds
    payload = _lock_payload(scope=scope, owner_id=owner_id, stale_after_seconds=stale_after_seconds)

    while True:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            existing = _load_lock_payload(lock_path)
            if _is_lock_stale(existing):
                try:
                    lock_path.unlink()
                except FileNotFoundError:
                    pass
                continue
            if time.monotonic() >= deadline:
                raise SchemaValidationError(f"Timed out waiting for {scope} lock: {lock_path}")
            time.sleep(0.05)
            continue

        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        break

    try:
        yield {
            "owner_id": owner_id,
            "scope": scope,
            "lock_path": str(lock_path),
        }
    finally:
        existing = _load_lock_payload(lock_path)
        if isinstance(existing, dict) and existing.get("owner_id") == owner_id:
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass


def load_catalog_refresh_state(paths: TaskPaths) -> dict[str, Any] | None:
    if not paths.catalog_refresh_path.exists():
        return None
    payload = load_json(paths.catalog_refresh_path)
    if not isinstance(payload, dict):
        return None
    return payload


def _catalog_refresh_error_fields(error: Exception | None) -> tuple[str | None, str | None]:
    if error is None:
        return None, None
    error_type = type(error).__name__
    error_message = str(error).strip() or error_type
    return error_type, error_message


def _build_catalog_refresh_state(
    paths: TaskPaths,
    previous: dict[str, Any] | None,
    *,
    refresh_status: str,
    reason: str,
    event_type: str | None,
    attempted: bool,
    database_sync_available: bool,
    error: Exception | None = None,
) -> dict[str, Any]:
    attempted_at = utc_now()
    failure_count = int(previous.get("failure_count", 0)) if isinstance(previous, dict) else 0
    last_success_at = previous.get("last_success_at") if isinstance(previous, dict) else None
    last_success_event_type = previous.get("last_success_event_type") if isinstance(previous, dict) else None
    error_type, error_message = _catalog_refresh_error_fields(error)

    if refresh_status == CATALOG_REFRESH_STATUS_SYNCED:
        last_success_at = attempted_at
        last_success_event_type = event_type
        failure_count = 0
        error_type = None
        error_message = None
    elif refresh_status == CATALOG_REFRESH_STATUS_FAILED:
        failure_count += 1

    return {
        "schema_version": "commander-harness-v1",
        "task_id": paths.task_id,
        "status": refresh_status,
        "reason": reason,
        "event_type": event_type,
        "attempted": attempted,
        "attempted_at": attempted_at,
        "database_sync_available": database_sync_available,
        "last_success_at": last_success_at,
        "last_success_event_type": last_success_event_type,
        "failure_count": failure_count,
        "error_type": error_type,
        "error_message": error_message,
        "catalog_refresh_path": str(paths.catalog_refresh_path),
    }


def build_catalog_refresh_summary(paths: TaskPaths) -> dict[str, Any]:
    payload = load_catalog_refresh_state(paths)
    if not isinstance(payload, dict):
        return {
            "status": CATALOG_REFRESH_STATUS_NEVER_ATTEMPTED,
            "reason": None,
            "event_type": None,
            "attempted": False,
            "attempted_at": None,
            "database_sync_available": None,
            "last_success_at": None,
            "last_success_event_type": None,
            "failure_count": 0,
            "error_type": None,
            "error_message": None,
            "path": str(paths.catalog_refresh_path),
        }

    return {
        "status": payload.get("status") or CATALOG_REFRESH_STATUS_NEVER_ATTEMPTED,
        "reason": payload.get("reason"),
        "event_type": payload.get("event_type"),
        "attempted": bool(payload.get("attempted")),
        "attempted_at": payload.get("attempted_at"),
        "database_sync_available": payload.get("database_sync_available"),
        "last_success_at": payload.get("last_success_at"),
        "last_success_event_type": payload.get("last_success_event_type"),
        "failure_count": int(payload.get("failure_count") or 0),
        "error_type": payload.get("error_type"),
        "error_message": payload.get("error_message"),
        "path": str(paths.catalog_refresh_path),
    }


def refresh_commander_task_catalog(paths: TaskPaths, *, event_type: str | None = None) -> dict[str, Any]:
    """把单个 task 的文件快照刷新到主数据库 catalog 索引，并显式记录成功或失败。"""
    previous = load_catalog_refresh_state(paths)

    if event_type is not None and event_type not in CATALOG_REFRESHABLE_TYPES:
        payload = _build_catalog_refresh_state(
            paths,
            previous,
            refresh_status=CATALOG_REFRESH_STATUS_SKIPPED,
            reason="event_type_not_refreshable",
            event_type=event_type,
            attempted=False,
            database_sync_available=True,
        )
        write_json(paths.catalog_refresh_path, payload)
        refresh_status(paths)
        return payload

    try:
        from api.db import upsert_commander_task_catalog_entry
    except Exception as error:
        payload = _build_catalog_refresh_state(
            paths,
            previous,
            refresh_status=CATALOG_REFRESH_STATUS_FAILED,
            reason="api_db_import_failed",
            event_type=event_type,
            attempted=True,
            database_sync_available=False,
            error=error,
        )
        write_json(paths.catalog_refresh_path, payload)
        refresh_status(paths)
        return payload

    try:
        packet = load_json(paths.packet_path) if paths.packet_path.exists() else {}
        report = load_json(paths.report_path) if paths.report_path.exists() else {}
        status = load_json(paths.status_path) if paths.status_path.exists() else {}
        checkpoint = load_json(paths.checkpoint_path) if paths.checkpoint_path.exists() else {}
        lifecycle = load_json(paths.lifecycle_path) if paths.lifecycle_path.exists() else {}
        events = load_events(paths.events_path)
        latest_event = events[-1] if events else None

        event_summary = {
            "event_count": len(events),
            "last_event_type": latest_event.get("event_type") if latest_event else "",
            "last_event_at": latest_event.get("timestamp") if latest_event else "",
        }
        candidate_entry = {
            "task_id": packet.get("task_id")
            or status.get("task_id")
            or checkpoint.get("task_id")
            or report.get("task_id")
            or paths.task_id,
            "title": status.get("title") or checkpoint.get("title") or packet.get("title") or "",
            "current_phase": status.get("current_phase") or checkpoint.get("current_phase") or "",
            "status": status.get("worker_status")
            or report.get("status")
            or checkpoint.get("current_phase")
            or status.get("status")
            or packet.get("status")
            or "",
            "worker_profile": status.get("worker_profile") or checkpoint.get("worker_profile") or packet.get("worker_profile") or "",
            "preferred_worker_profile": status.get("preferred_worker_profile")
            or checkpoint.get("preferred_worker_profile")
            or packet.get("preferred_worker_profile")
            or "",
            "tool_profile": status.get("tool_profile") or checkpoint.get("tool_profile") or packet.get("tool_profile") or "",
            "controller_handoff": status.get("controller_handoff") or checkpoint.get("controller_handoff") or "",
            "commander_recommendation": status.get("commander_recommendation")
            or checkpoint.get("commander_recommendation")
            or "",
            "recommended_action": status.get("recommended_action") or checkpoint.get("recommended_action") or "",
            "next_minimal_action": status.get("next_minimal_action") or checkpoint.get("next_minimal_action") or "",
            "lifecycle_status": status.get("lifecycle_status")
            or checkpoint.get("lifecycle_status")
            or lifecycle.get("lifecycle_status")
            or "",
            "cleanup_eligible": bool(
                status.get("cleanup_eligible") or checkpoint.get("cleanup_eligible") or lifecycle.get("cleanup_eligible")
            ),
            "worker_status": status.get("worker_status") or checkpoint.get("worker_status") or report.get("status") or "",
            "needs_commander_decision": bool(
                status.get("needs_commander_decision")
                or checkpoint.get("needs_commander_decision")
                or report.get("needs_commander_decision")
            ),
            "needs_user_decision": bool(
                status.get("needs_user_decision")
                or checkpoint.get("needs_user_decision")
                or report.get("needs_user_decision")
            ),
            "ready_for_user_delivery": bool(
                status.get("ready_for_user_delivery")
                or checkpoint.get("ready_for_user_delivery")
                or report.get("ready_for_user_delivery")
            ),
            "has_packet": paths.packet_path.exists(),
            "has_report": paths.report_path.exists(),
            "event_count": int(status.get("event_count") or checkpoint.get("event_count") or event_summary["event_count"] or 0),
            "last_event_type": status.get("last_event_type") or checkpoint.get("last_event_type") or event_summary["last_event_type"],
            "last_event_at": status.get("last_event_at") or checkpoint.get("last_event_at") or event_summary["last_event_at"],
            "closed_at": status.get("closed_at") or checkpoint.get("closed_at") or lifecycle.get("closed_at") or "",
            "archived_at": status.get("archived_at") or checkpoint.get("archived_at") or lifecycle.get("archived_at") or "",
            "stale_at": status.get("stale_at") or checkpoint.get("stale_at") or lifecycle.get("stale_at") or "",
            "updated_at": status.get("updated_at")
            or checkpoint.get("updated_at")
            or packet.get("updated_at")
            or report.get("updated_at")
            or utc_now(),
        }
    except Exception as error:
        payload = _build_catalog_refresh_state(
            paths,
            previous,
            refresh_status=CATALOG_REFRESH_STATUS_FAILED,
            reason="catalog_entry_build_failed",
            event_type=event_type,
            attempted=True,
            database_sync_available=True,
            error=error,
        )
        write_json(paths.catalog_refresh_path, payload)
        refresh_status(paths)
        return payload

    try:
        upsert_commander_task_catalog_entry(candidate_entry)
    except Exception as error:
        payload = _build_catalog_refresh_state(
            paths,
            previous,
            refresh_status=CATALOG_REFRESH_STATUS_FAILED,
            reason="catalog_entry_upsert_failed",
            event_type=event_type,
            attempted=True,
            database_sync_available=True,
            error=error,
        )
        write_json(paths.catalog_refresh_path, payload)
        refresh_status(paths)
        return payload

    payload = _build_catalog_refresh_state(
        paths,
        previous,
        refresh_status=CATALOG_REFRESH_STATUS_SYNCED,
        reason="catalog_entry_upserted",
        event_type=event_type,
        attempted=True,
        database_sync_available=True,
    )
    write_json(paths.catalog_refresh_path, payload)
    refresh_status(paths)
    return payload


def load_schema(path: Path) -> dict[str, Any]:
    schema = load_json(path)
    if not isinstance(schema, dict):
        raise SchemaValidationError(f"Schema root must be an object: {path}")
    return schema


def load_worker_slot(path: Path) -> dict[str, Any]:
    payload = load_json(path)
    if isinstance(payload, dict):
        payload = normalize_worker_slot(payload)
        write_json(path, payload)
    validate_instance(payload, load_schema(WORKER_SLOT_SCHEMA_PATH))
    return payload


def list_worker_slots(runtime_root: Path) -> list[dict[str, Any]]:
    pool_paths = resolve_worker_pool_paths(runtime_root)
    if not pool_paths.slots_dir.exists():
        return []
    slots: list[dict[str, Any]] = []
    for slot_path in sorted(pool_paths.slots_dir.glob("*.json")):
        slots.append(load_worker_slot(slot_path))
    return slots


def _slug_worker_profile(worker_profile: str) -> str:
    slug = "".join(char if char.isalnum() else "-" for char in worker_profile.lower())
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-") or "worker"


def _next_worker_id_for_slots(slots: list[dict[str, Any]], worker_profile: str) -> str:
    slug = _slug_worker_profile(worker_profile)
    prefix = f"{slug}-"
    next_index = 1
    for slot in slots:
        worker_id = slot.get("worker_id")
        if not isinstance(worker_id, str) or not worker_id.startswith(prefix):
            continue
        suffix = worker_id[len(prefix) :]
        if suffix.isdigit():
            next_index = max(next_index, int(suffix) + 1)
    return f"{slug}-{next_index:03d}"


def _next_worker_id(runtime_root: Path, worker_profile: str) -> str:
    return _next_worker_id_for_slots(list_worker_slots(runtime_root), worker_profile)


def build_worker_slot(
    *,
    worker_id: str,
    worker_profile: str,
    preferred_worker_profile: str | None,
    tool_profile: str,
    allowed_tools: list[str],
    state: str,
    current_task_id: str | None,
    acquire_count: int,
    reuse_count: int,
    lease_duration_seconds: int,
    lease_expires_at: str | None,
    heartbeat_at: str | None,
    created_at: str,
    updated_at: str,
    last_used_at: str,
    last_released_at: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": "commander-harness-v1",
        "worker_id": worker_id,
        "worker_profile": worker_profile,
        "preferred_worker_profile": preferred_worker_profile,
        "tool_profile": tool_profile,
        "allowed_tools": allowed_tools,
        "state": state,
        "current_task_id": current_task_id,
        "acquire_count": acquire_count,
        "reuse_count": reuse_count,
        "lease_duration_seconds": lease_duration_seconds,
        "lease_expires_at": lease_expires_at,
        "heartbeat_at": heartbeat_at,
        "created_at": created_at,
        "updated_at": updated_at,
        "last_used_at": last_used_at,
        "last_released_at": last_released_at,
    }


def normalize_worker_slot(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    lease_duration_seconds = normalized.get("lease_duration_seconds")
    if not isinstance(lease_duration_seconds, int) or isinstance(lease_duration_seconds, bool) or lease_duration_seconds < 0:
        lease_duration_seconds = DEFAULT_WORKER_LEASE_SECONDS
    normalized["lease_duration_seconds"] = lease_duration_seconds

    state = normalized.get("state")
    fallback_timestamp = normalized.get("updated_at") or normalized.get("last_used_at")
    lease_expires_at = normalized.get("lease_expires_at")
    heartbeat_at = normalized.get("heartbeat_at")

    if state in WORKER_SLOT_LEASED_STATES:
        if not isinstance(heartbeat_at, str) or not heartbeat_at:
            heartbeat_at = fallback_timestamp if isinstance(fallback_timestamp, str) and fallback_timestamp else utc_now()
        if not isinstance(lease_expires_at, str) or not lease_expires_at:
            lease_expires_at = heartbeat_at
    else:
        lease_expires_at = None
        if not isinstance(heartbeat_at, str) or not heartbeat_at:
            heartbeat_at = None

    normalized["lease_expires_at"] = lease_expires_at
    normalized["heartbeat_at"] = heartbeat_at
    return normalized


def is_worker_slot_lease_expired(slot: dict[str, Any], *, now: datetime | None = None) -> bool:
    if slot.get("state") not in WORKER_SLOT_LEASED_STATES:
        return False
    lease_expires_at = parse_utc_timestamp(slot.get("lease_expires_at"))
    if lease_expires_at is None:
        return True
    comparison_time = now or datetime.now(timezone.utc)
    return comparison_time >= lease_expires_at


def list_task_worker_slots(
    runtime_root: Path,
    task_id: str,
    *,
    slots: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    worker_slots = slots if slots is not None else list_worker_slots(runtime_root)
    return [slot for slot in worker_slots if slot.get("current_task_id") == task_id]


def _worker_binding_arbitration_key(slot: dict[str, Any]) -> tuple[datetime, int, str]:
    timestamp = (
        parse_utc_timestamp(slot.get("updated_at"))
        or parse_utc_timestamp(slot.get("heartbeat_at"))
        or parse_utc_timestamp(slot.get("created_at"))
        or datetime.min.replace(tzinfo=timezone.utc)
    )
    state_priority = 1 if slot.get("state") == WORKER_SLOT_BUSY else 0
    worker_id = slot.get("worker_id") if isinstance(slot.get("worker_id"), str) else ""
    return (timestamp, state_priority, worker_id)


def build_task_worker_binding_summary(
    runtime_root: Path,
    task_id: str,
    *,
    slots: list[dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    bound_slots = list_task_worker_slots(runtime_root, task_id, slots=slots)
    sorted_slots = sorted(
        bound_slots,
        key=lambda item: parse_utc_timestamp(item.get("updated_at")) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    state_counts: dict[str, int] = {}
    worker_ids: list[str] = []
    open_worker_ids: list[str] = []
    leased_worker_ids: list[str] = []
    expired_leased_worker_ids: list[str] = []
    canonical_worker_id: str | None = None
    duplicate_worker_ids: list[str] = []
    for slot in sorted_slots:
        worker_id = slot.get("worker_id")
        state = slot.get("state")
        if isinstance(state, str):
            state_counts[state] = state_counts.get(state, 0) + 1
        if not isinstance(worker_id, str) or not worker_id:
            continue
        worker_ids.append(worker_id)
        if state != WORKER_SLOT_CLOSED:
            open_worker_ids.append(worker_id)
        if state in WORKER_SLOT_LEASED_STATES:
            leased_worker_ids.append(worker_id)
            if is_worker_slot_lease_expired(slot, now=now):
                expired_leased_worker_ids.append(worker_id)

    leased_slots = [slot for slot in sorted_slots if slot.get("state") in WORKER_SLOT_LEASED_STATES]
    if leased_slots:
        canonical_slot = max(leased_slots, key=_worker_binding_arbitration_key)
        canonical_worker_id = canonical_slot.get("worker_id") if isinstance(canonical_slot.get("worker_id"), str) else None
        duplicate_worker_ids = [
            slot["worker_id"]
            for slot in leased_slots
            if isinstance(slot.get("worker_id"), str) and slot.get("worker_id") != canonical_worker_id
        ]

    if not worker_ids:
        binding_health = "unbound"
    elif expired_leased_worker_ids:
        binding_health = "lease_expired"
    elif len(leased_worker_ids) > 1:
        binding_health = "multiple_leased_workers"
    elif any(slot.get("state") == WORKER_SLOT_WARM_IDLE for slot in sorted_slots):
        binding_health = "released_binding_drift"
    elif any(slot.get("state") == WORKER_SLOT_CLOSED for slot in sorted_slots):
        binding_health = "closed_binding_drift"
    else:
        binding_health = "healthy"

    return {
        "task_id": task_id,
        "worker_count": len(worker_ids),
        "worker_ids": worker_ids,
        "open_worker_count": len(open_worker_ids),
        "open_worker_ids": open_worker_ids,
        "leased_worker_count": len(leased_worker_ids),
        "leased_worker_ids": leased_worker_ids,
        "expired_leased_worker_count": len(expired_leased_worker_ids),
        "expired_leased_worker_ids": expired_leased_worker_ids,
        "canonical_worker_id": canonical_worker_id,
        "duplicate_worker_ids": duplicate_worker_ids,
        "state_counts": state_counts,
        "binding_health": binding_health,
        "has_binding": bool(worker_ids),
        "has_active_lease": bool(leased_worker_ids),
    }


def refresh_worker_registry(runtime_root: Path) -> dict[str, Any]:
    pool_paths = resolve_worker_pool_paths(runtime_root)
    slots = list_worker_slots(runtime_root)
    state_counts: dict[str, int] = {}
    worker_profiles = sorted(
        {
            slot["worker_profile"]
            for slot in slots
            if isinstance(slot.get("worker_profile"), str) and slot["worker_profile"]
        }
    )
    open_count = 0
    for slot in slots:
        state = slot.get("state")
        if isinstance(state, str):
            state_counts[state] = state_counts.get(state, 0) + 1
            if state != WORKER_SLOT_CLOSED:
                open_count += 1

    registry = {
        "schema_version": "commander-harness-v1",
        "worker_count": len(slots),
        "open_count": open_count,
        "state_counts": state_counts,
        "worker_profiles": worker_profiles,
        "workers": slots,
        "updated_at": utc_now(),
    }
    write_json(pool_paths.registry_path, registry)
    return registry


def _persist_worker_slot(runtime_root: Path, slot_paths: WorkerSlotPaths, slot: dict[str, Any]) -> dict[str, Any]:
    validate_instance(slot, load_schema(WORKER_SLOT_SCHEMA_PATH))
    write_json(slot_paths.slot_path, slot)
    return refresh_worker_registry(runtime_root)


def _require_worker_state_for_action(
    slot: dict[str, Any],
    *,
    action: str,
    allowed_states: tuple[str, ...],
) -> None:
    current_state = slot.get("state")
    if current_state not in allowed_states:
        raise SchemaValidationError(
            f"Worker {slot.get('worker_id')} cannot {action} from state {current_state!r}; "
            f"allowed states: {allowed_states!r}"
        )


def acquire_worker_slot(
    runtime_root: Path,
    *,
    task_id: str,
    worker_profile: str,
    preferred_worker_profile: str | None,
    tool_profile: str,
    allowed_tools: list[str],
    reuse_allowed: bool,
    lease_seconds: int = DEFAULT_WORKER_LEASE_SECONDS,
) -> dict[str, Any]:
    pool_paths = resolve_worker_pool_paths(runtime_root)
    candidate_profiles = [profile for profile in (preferred_worker_profile, worker_profile) if profile]

    with worker_pool_lock(runtime_root):
        selected: dict[str, Any] | None = None
        reused = False
        slots = list_worker_slots(runtime_root)
        if reuse_allowed:
            for candidate_profile in candidate_profiles:
                for slot in slots:
                    if slot.get("state") != WORKER_SLOT_WARM_IDLE:
                        continue
                    if slot.get("worker_profile") != candidate_profile:
                        continue
                    selected = slot
                    reused = True
                    break
                if selected is not None:
                    break

        now = utc_now()
        lease_expires_at = utc_after(lease_seconds)
        if selected is None:
            worker_id = _next_worker_id_for_slots(slots, worker_profile)
            slot = build_worker_slot(
                worker_id=worker_id,
                worker_profile=worker_profile,
                preferred_worker_profile=preferred_worker_profile,
                tool_profile=tool_profile,
                allowed_tools=allowed_tools,
                state=WORKER_SLOT_BUSY,
                current_task_id=task_id,
                acquire_count=1,
                reuse_count=0,
                lease_duration_seconds=lease_seconds,
                lease_expires_at=lease_expires_at,
                heartbeat_at=now,
                created_at=now,
                updated_at=now,
                last_used_at=now,
                last_released_at=None,
            )
            slot_paths = resolve_worker_slot_paths(runtime_root, worker_id)
            registry = _persist_worker_slot(runtime_root, slot_paths, slot)
            return {
                "created": True,
                "reused": False,
                "worker_id": worker_id,
                "slot_path": str(slot_paths.slot_path),
                "worker": slot,
                "registry_path": str(pool_paths.registry_path),
                "registry": registry,
            }

        worker_id = selected["worker_id"]
        slot_paths = resolve_worker_slot_paths(runtime_root, worker_id)
        with worker_slot_lock(runtime_root, worker_id):
            current = load_worker_slot(slot_paths.slot_path)
            if current.get("state") != WORKER_SLOT_WARM_IDLE:
                raise SchemaValidationError(
                    f"Worker {worker_id} is no longer reusable; expected warm_idle, got {current.get('state')!r}"
                )
            slot = build_worker_slot(
                worker_id=worker_id,
                worker_profile=current["worker_profile"],
                preferred_worker_profile=preferred_worker_profile,
                tool_profile=tool_profile,
                allowed_tools=allowed_tools,
                state=WORKER_SLOT_BUSY,
                current_task_id=task_id,
                acquire_count=int(current.get("acquire_count", 0)) + 1,
                reuse_count=int(current.get("reuse_count", 0)) + 1,
                lease_duration_seconds=lease_seconds,
                lease_expires_at=lease_expires_at,
                heartbeat_at=now,
                created_at=current["created_at"],
                updated_at=now,
                last_used_at=now,
                last_released_at=current.get("last_released_at"),
            )
            registry = _persist_worker_slot(runtime_root, slot_paths, slot)
            return {
                "created": False,
                "reused": reused,
                "worker_id": worker_id,
                "slot_path": str(slot_paths.slot_path),
                "worker": slot,
                "registry_path": str(pool_paths.registry_path),
                "registry": registry,
            }


def release_worker_slot(runtime_root: Path, *, worker_id: str, state: str) -> dict[str, Any]:
    if state not in WORKER_SLOT_RELEASE_STATES:
        raise SchemaValidationError(
            f"Worker release state must be one of {WORKER_SLOT_RELEASE_STATES!r}, got {state!r}"
        )

    slot_paths = resolve_worker_slot_paths(runtime_root, worker_id)
    with worker_pool_lock(runtime_root):
        with worker_slot_lock(runtime_root, worker_id):
            slot = load_worker_slot(slot_paths.slot_path)
            _require_worker_state_for_action(
                slot,
                action="release",
                allowed_states=WORKER_SLOT_RELEASE_ALLOWED_FROM_STATES,
            )
            now = utc_now()
            current_task_id = slot.get("current_task_id")
            if state in {WORKER_SLOT_WARM_IDLE, WORKER_SLOT_CLOSED}:
                current_task_id = None

            released = build_worker_slot(
                worker_id=slot["worker_id"],
                worker_profile=slot["worker_profile"],
                preferred_worker_profile=slot.get("preferred_worker_profile"),
                tool_profile=slot["tool_profile"],
                allowed_tools=slot["allowed_tools"],
                state=state,
                current_task_id=current_task_id,
                acquire_count=int(slot.get("acquire_count", 0)),
                reuse_count=int(slot.get("reuse_count", 0)),
                lease_duration_seconds=int(slot.get("lease_duration_seconds", DEFAULT_WORKER_LEASE_SECONDS)),
                lease_expires_at=None,
                heartbeat_at=now if state in WORKER_SLOT_LEASED_STATES else slot.get("heartbeat_at"),
                created_at=slot["created_at"],
                updated_at=now,
                last_used_at=slot["last_used_at"],
                last_released_at=now,
            )
            registry = _persist_worker_slot(runtime_root, slot_paths, released)
            return {
                "worker_id": worker_id,
                "slot_path": str(slot_paths.slot_path),
                "worker": released,
                "registry_path": str(resolve_worker_pool_paths(runtime_root).registry_path),
                "registry": registry,
            }


def heartbeat_worker_slot(
    runtime_root: Path,
    *,
    worker_id: str,
    lease_seconds: int | None = None,
) -> dict[str, Any]:
    slot_paths = resolve_worker_slot_paths(runtime_root, worker_id)
    with worker_pool_lock(runtime_root):
        with worker_slot_lock(runtime_root, worker_id):
            slot = load_worker_slot(slot_paths.slot_path)
            _require_worker_state_for_action(
                slot,
                action="heartbeat",
                allowed_states=WORKER_SLOT_LEASED_STATES,
            )

            now = utc_now()
            lease_duration_seconds = int(slot.get("lease_duration_seconds", DEFAULT_WORKER_LEASE_SECONDS))
            if lease_seconds is not None:
                lease_duration_seconds = max(int(lease_seconds), 0)

            renewed = build_worker_slot(
                worker_id=slot["worker_id"],
                worker_profile=slot["worker_profile"],
                preferred_worker_profile=slot.get("preferred_worker_profile"),
                tool_profile=slot["tool_profile"],
                allowed_tools=slot["allowed_tools"],
                state=slot["state"],
                current_task_id=slot.get("current_task_id"),
                acquire_count=int(slot.get("acquire_count", 0)),
                reuse_count=int(slot.get("reuse_count", 0)),
                lease_duration_seconds=lease_duration_seconds,
                lease_expires_at=utc_after(lease_duration_seconds),
                heartbeat_at=now,
                created_at=slot["created_at"],
                updated_at=now,
                last_used_at=slot["last_used_at"],
                last_released_at=slot.get("last_released_at"),
            )
            registry = _persist_worker_slot(runtime_root, slot_paths, renewed)
            return {
                "worker_id": worker_id,
                "slot_path": str(slot_paths.slot_path),
                "worker": renewed,
                "registry_path": str(resolve_worker_pool_paths(runtime_root).registry_path),
                "registry": registry,
            }


def _reconcile_release_state(slot: dict[str, Any]) -> str:
    if slot.get("state") == WORKER_SLOT_BUSY:
        return WORKER_SLOT_CLOSED
    return WORKER_SLOT_WARM_IDLE


def _task_requires_live_worker(task_status: dict[str, Any] | None) -> bool:
    if not isinstance(task_status, dict):
        return False
    if task_status.get("lifecycle_status") != TASK_LIFECYCLE_ACTIVE:
        return False
    return task_status.get("current_phase") == "awaiting_report"


def reconcile_worker_slots(
    runtime_root: Path,
    *,
    worker_id: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    with worker_pool_lock(runtime_root):
        slots = list_worker_slots(runtime_root)
        if worker_id is not None:
            slots = [slot for slot in slots if slot.get("worker_id") == worker_id]

        results: list[dict[str, Any]] = []
        reclaimed_worker_ids: list[str] = []
        stale_worker_ids: list[str] = []
        orphan_task_ids: list[str] = []
        duplicate_binding_task_ids: list[str] = []
        duplicate_leased_bindings: dict[str, dict[str, Any]] = {}
        leased_slots_by_task_id: dict[str, list[dict[str, Any]]] = {}
        for slot in slots:
            task_id = slot.get("current_task_id")
            if slot.get("state") not in WORKER_SLOT_LEASED_STATES:
                continue
            if not isinstance(task_id, str) or not task_id:
                continue
            leased_slots_by_task_id.setdefault(task_id, []).append(slot)
        for task_id, task_slots in leased_slots_by_task_id.items():
            if len(task_slots) < 2:
                continue
            canonical_slot = max(task_slots, key=_worker_binding_arbitration_key)
            canonical_worker_id = (
                canonical_slot.get("worker_id") if isinstance(canonical_slot.get("worker_id"), str) else None
            )
            duplicate_worker_ids = [
                slot["worker_id"]
                for slot in task_slots
                if isinstance(slot.get("worker_id"), str) and slot.get("worker_id") != canonical_worker_id
            ]
            if canonical_worker_id is None or not duplicate_worker_ids:
                continue
            duplicate_leased_bindings[task_id] = {
                "canonical_worker_id": canonical_worker_id,
                "duplicate_worker_ids": duplicate_worker_ids,
            }
            duplicate_binding_task_ids.append(task_id)

        for slot in slots:
            slot_paths = resolve_worker_slot_paths(runtime_root, slot["worker_id"])
            with worker_slot_lock(runtime_root, slot["worker_id"]):
                current_slot = load_worker_slot(slot_paths.slot_path)
                current_task_id = (
                    current_slot.get("current_task_id") if isinstance(current_slot.get("current_task_id"), str) else None
                )
                lease_expired = is_worker_slot_lease_expired(current_slot, now=now)
                task_status: dict[str, Any] | None = None
                task_exists = False
                task_marked_stale = False
                action = "noop"
                reason = None
                released = current_slot
                release_to = None
                task_paths: TaskPaths | None = None
                duplicate_binding = (
                    duplicate_leased_bindings.get(current_task_id) if isinstance(current_task_id, str) else None
                )

                if current_task_id:
                    task_paths = resolve_task_paths(runtime_root, current_task_id)
                    task_exists = task_paths.task_dir.exists()
                    if task_exists:
                        task_status = refresh_status(task_paths)

                if (
                    current_slot.get("state") in WORKER_SLOT_LEASED_STATES
                    and isinstance(duplicate_binding, dict)
                    and current_slot["worker_id"] in duplicate_binding.get("duplicate_worker_ids", [])
                ):
                    action = "reclaim_duplicate_leased_worker"
                    reason = (
                        f"duplicate_leased_worker_for_task_{current_task_id}_keep_"
                        f"{duplicate_binding.get('canonical_worker_id')}"
                    )
                    release_to = _reconcile_release_state(current_slot)
                elif current_slot.get("state") in {WORKER_SLOT_WARM_IDLE, WORKER_SLOT_CLOSED} and current_task_id is not None:
                    action = "clear_released_binding"
                    reason = f"released_worker_kept_task_binding_{current_slot.get('state')}"
                    release_to = current_slot.get("state")
                elif current_slot.get("state") in WORKER_SLOT_LEASED_STATES and current_task_id is None:
                    action = "reclaim_unbound_leased_worker"
                    reason = "leased_worker_missing_task_binding"
                    release_to = _reconcile_release_state(current_slot)
                elif current_slot.get("state") in WORKER_SLOT_LEASED_STATES and not task_exists:
                    action = "reclaim_worker_for_missing_task"
                    reason = "worker_bound_to_missing_task"
                    release_to = _reconcile_release_state(current_slot)
                elif current_slot.get("state") in WORKER_SLOT_LEASED_STATES and isinstance(task_status, dict):
                    lifecycle_status = task_status.get("lifecycle_status")
                    if lifecycle_status in {
                        TASK_LIFECYCLE_ARCHIVED,
                        TASK_LIFECYCLE_CLOSED,
                        TASK_LIFECYCLE_CANCELED,
                    }:
                        action = "reclaim_worker_for_terminal_task"
                        reason = f"worker_bound_to_terminal_task_{lifecycle_status}"
                        release_to = _reconcile_release_state(current_slot)
                    elif lease_expired:
                        stale_worker_ids.append(current_slot["worker_id"])
                        release_to = _reconcile_release_state(current_slot)
                        if _task_requires_live_worker(task_status) and task_paths is not None:
                            action = "reclaim_expired_worker_and_mark_task_stale"
                            reason = f"worker_lease_expired_before_report_{current_slot['worker_id']}"
                            orphan_task_ids.append(current_task_id)
                            if not dry_run:
                                mark_task_stale(task_paths, reason=reason)
                                append_event(
                                    task_paths,
                                    "task_stale_marked",
                                    {
                                        "reason": reason,
                                        "worker_id": current_slot["worker_id"],
                                        "worker_state": current_slot.get("state"),
                                        "lease_expires_at": current_slot.get("lease_expires_at"),
                                    },
                                )
                                refresh_status(task_paths)
                                refresh_commander_task_catalog(task_paths, event_type="task_stale_marked")
                                task_status = refresh_status(task_paths)
                            task_marked_stale = True
                        else:
                            action = "reclaim_expired_worker"
                            reason = f"worker_lease_expired_{current_slot['worker_id']}"

                if release_to is not None:
                    if not dry_run:
                        released_task_id = current_slot.get("current_task_id")
                        if release_to in {WORKER_SLOT_WARM_IDLE, WORKER_SLOT_CLOSED}:
                            released_task_id = None
                        released = build_worker_slot(
                            worker_id=current_slot["worker_id"],
                            worker_profile=current_slot["worker_profile"],
                            preferred_worker_profile=current_slot.get("preferred_worker_profile"),
                            tool_profile=current_slot["tool_profile"],
                            allowed_tools=current_slot["allowed_tools"],
                            state=release_to,
                            current_task_id=released_task_id,
                            acquire_count=int(current_slot.get("acquire_count", 0)),
                            reuse_count=int(current_slot.get("reuse_count", 0)),
                            lease_duration_seconds=int(
                                current_slot.get("lease_duration_seconds", DEFAULT_WORKER_LEASE_SECONDS)
                            ),
                            lease_expires_at=None,
                            heartbeat_at=(
                                utc_now() if release_to in WORKER_SLOT_LEASED_STATES else current_slot.get("heartbeat_at")
                            ),
                            created_at=current_slot["created_at"],
                            updated_at=utc_now(),
                            last_used_at=current_slot["last_used_at"],
                            last_released_at=utc_now(),
                        )
                        validate_instance(released, load_schema(WORKER_SLOT_SCHEMA_PATH))
                        write_json(slot_paths.slot_path, released)
                        if action == "reclaim_duplicate_leased_worker" and task_paths is not None:
                            append_event(
                                task_paths,
                                "worker_binding_reconciled",
                                {
                                    "reason": reason,
                                    "canonical_worker_id": duplicate_binding.get("canonical_worker_id"),
                                    "released_worker_id": current_slot["worker_id"],
                                },
                            )
                            refresh_status(task_paths)
                            refresh_commander_task_catalog(task_paths, event_type=None)
                    reclaimed_worker_ids.append(current_slot["worker_id"])

                result = {
                    "worker_id": current_slot["worker_id"],
                    "slot_path": str(slot_paths.slot_path),
                    "lock_path": str(slot_paths.lock_path),
                    "changed": release_to is not None,
                    "action": action,
                    "reason": reason,
                    "dry_run": dry_run,
                    "previous_state": current_slot.get("state"),
                    "state": released.get("state"),
                    "release_to": release_to,
                    "lease_expired": lease_expired,
                    "current_task_id": current_task_id,
                    "task_exists": task_exists,
                    "task_phase": task_status.get("current_phase") if isinstance(task_status, dict) else None,
                    "task_lifecycle_status": task_status.get("lifecycle_status") if isinstance(task_status, dict) else None,
                    "task_marked_stale": task_marked_stale,
                    "canonical_worker_id": duplicate_binding.get("canonical_worker_id") if isinstance(duplicate_binding, dict) else None,
                    "duplicate_worker_ids": duplicate_binding.get("duplicate_worker_ids", []) if isinstance(duplicate_binding, dict) else [],
                }
                if current_task_id:
                    result["task_worker_binding"] = build_task_worker_binding_summary(
                        runtime_root,
                        current_task_id,
                        now=now,
                    )
                results.append(result)

        if dry_run:
            registry = {
                "schema_version": "commander-harness-v1",
                "worker_count": len(slots),
                "open_count": sum(1 for slot in slots if slot.get("state") != WORKER_SLOT_CLOSED),
                "state_counts": {},
                "worker_profiles": sorted(
                    {
                        slot["worker_profile"]
                        for slot in slots
                        if isinstance(slot.get("worker_profile"), str) and slot["worker_profile"]
                    }
                ),
                "workers": slots,
                "updated_at": utc_now(),
            }
            for slot in slots:
                state = slot.get("state")
                if isinstance(state, str):
                    registry["state_counts"][state] = registry["state_counts"].get(state, 0) + 1
        else:
            registry = refresh_worker_registry(runtime_root)

    return {
        "runtime_root": str(runtime_root),
        "worker_count": len(results),
        "changed_count": sum(1 for item in results if item["changed"]),
        "reclaimed_worker_ids": reclaimed_worker_ids,
        "stale_worker_ids": sorted(set(stale_worker_ids)),
        "orphan_task_ids": sorted(set(orphan_task_ids)),
        "duplicate_binding_task_ids": sorted(set(duplicate_binding_task_ids)),
        "dry_run": dry_run,
        "workers": results,
        "registry": registry,
    }


def resolve_task_paths(runtime_root: Path, task_id: str) -> TaskPaths:
    task_dir = runtime_root / "tasks" / task_id
    return TaskPaths(
        task_id=task_id,
        runtime_root=runtime_root,
        task_dir=task_dir,
        compactions_dir=task_dir / "compactions",
        packet_path=task_dir / "packet.json",
        context_bundle_path=task_dir / "context_bundle.json",
        worker_brief_path=task_dir / "worker_brief.md",
        worker_report_path=task_dir / "worker_report.json",
        report_path=task_dir / "report.json",
        improvement_candidate_path=runtime_root / "improvements" / f"{task_id}.candidate.json",
        catalog_refresh_path=task_dir / "catalog_refresh.json",
        reports_dir=task_dir / "reports",
        events_path=task_dir / "events.jsonl",
        lifecycle_path=task_dir / "lifecycle.json",
        status_path=task_dir / "status.json",
        checkpoint_path=task_dir / "checkpoint.json",
        resume_anchor_path=task_dir / "resume_anchor.json",
        compaction_event_path=task_dir / "compaction_event.json",
    )


def resolve_worker_pool_paths(runtime_root: Path) -> WorkerPoolPaths:
    pool_dir = runtime_root / "workers"
    locks_dir = pool_dir / "locks"
    return WorkerPoolPaths(
        pool_dir=pool_dir,
        slots_dir=pool_dir / "slots",
        locks_dir=locks_dir,
        registry_path=pool_dir / "registry.json",
        pool_lock_path=locks_dir / "pool.lock",
    )


def resolve_worker_slot_paths(runtime_root: Path, worker_id: str) -> WorkerSlotPaths:
    pool_paths = resolve_worker_pool_paths(runtime_root)
    return WorkerSlotPaths(
        worker_id=worker_id,
        slot_path=pool_paths.slots_dir / f"{worker_id}.json",
        lock_path=pool_paths.locks_dir / f"{worker_id}.lock",
    )


@contextmanager
def worker_pool_lock(
    runtime_root: Path,
    *,
    timeout_seconds: int = DEFAULT_WORKER_LOCK_TIMEOUT_SECONDS,
    stale_after_seconds: int = DEFAULT_WORKER_LOCK_STALE_SECONDS,
) -> Any:
    pool_paths = resolve_worker_pool_paths(runtime_root)
    with _file_lock(
        pool_paths.pool_lock_path,
        scope="worker_pool",
        timeout_seconds=timeout_seconds,
        stale_after_seconds=stale_after_seconds,
    ) as lock_info:
        yield lock_info


@contextmanager
def worker_slot_lock(
    runtime_root: Path,
    worker_id: str,
    *,
    timeout_seconds: int = DEFAULT_WORKER_LOCK_TIMEOUT_SECONDS,
    stale_after_seconds: int = DEFAULT_WORKER_LOCK_STALE_SECONDS,
) -> Any:
    slot_paths = resolve_worker_slot_paths(runtime_root, worker_id)
    with _file_lock(
        slot_paths.lock_path,
        scope=f"worker_slot:{worker_id}",
        timeout_seconds=timeout_seconds,
        stale_after_seconds=stale_after_seconds,
    ) as lock_info:
        yield lock_info


def append_event(paths: TaskPaths, event_type: str, detail: dict[str, Any]) -> None:
    payload = {
        "event_id": uuid4().hex,
        "task_id": paths.task_id,
        "event_type": event_type,
        "timestamp": utc_now(),
        "detail": detail,
    }
    paths.events_path.parent.mkdir(parents=True, exist_ok=True)
    with paths.events_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def load_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        events.append(json.loads(line))
    return events


def parse_utc_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _extract_intent_binding(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    direct = payload.get("intent_binding")
    if isinstance(direct, dict):
        return direct
    return {
        "last_open_offer": payload.get("last_open_offer"),
        "pending_user_reply_target": payload.get("pending_user_reply_target"),
        "offer_confirmed": payload.get("offer_confirmed"),
        "latest_user_reply_text": payload.get("latest_user_reply_text"),
        "latest_user_reply_kind": payload.get("latest_user_reply_kind"),
        "resolved_reply_target": payload.get("resolved_reply_target"),
        "binding_reason": payload.get("binding_reason"),
    }


def _load_existing_intent_binding(paths: TaskPaths) -> dict[str, Any] | None:
    for candidate_path in (
        paths.checkpoint_path,
        paths.status_path,
        paths.resume_anchor_path,
    ):
        if not candidate_path.exists():
            continue
        try:
            payload = load_json(candidate_path)
        except Exception:
            continue
        binding = _extract_intent_binding(payload)
        if isinstance(binding, dict):
            return binding
    return None


def build_default_task_lifecycle(
    *,
    task_id: str,
    created_at: str,
    updated_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": "commander-harness-v1",
        "task_id": task_id,
        "lifecycle_status": TASK_LIFECYCLE_ACTIVE,
        "created_at": created_at,
        "updated_at": updated_at,
        "closed_at": None,
        "closed_reason": None,
        "archived_at": None,
        "archive_reason": None,
        "stale_at": None,
        "stale_reason": None,
        "canceled_at": None,
        "cancel_reason": None,
        "last_reconciled_at": None,
    }


def normalize_task_lifecycle(
    payload: Any,
    *,
    task_id: str,
    fallback_created_at: str,
    fallback_updated_at: str,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return build_default_task_lifecycle(
            task_id=task_id,
            created_at=fallback_created_at,
            updated_at=fallback_updated_at,
        )

    lifecycle_status = payload.get("lifecycle_status")
    if lifecycle_status not in TASK_LIFECYCLE_STATUSES:
        lifecycle_status = TASK_LIFECYCLE_ACTIVE

    created_at = payload.get("created_at")
    if not isinstance(created_at, str) or not created_at:
        created_at = fallback_created_at
    updated_at = payload.get("updated_at")
    if not isinstance(updated_at, str) or not updated_at:
        updated_at = fallback_updated_at

    lifecycle = build_default_task_lifecycle(
        task_id=task_id,
        created_at=created_at,
        updated_at=updated_at,
    )
    lifecycle["lifecycle_status"] = lifecycle_status
    for key in (
        "closed_at",
        "closed_reason",
        "archived_at",
        "archive_reason",
        "stale_at",
        "stale_reason",
        "canceled_at",
        "cancel_reason",
        "last_reconciled_at",
    ):
        lifecycle[key] = payload.get(key)
    return lifecycle


def ensure_task_lifecycle(paths: TaskPaths, *, packet: Any = None, events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    event_list = events if events is not None else load_events(paths.events_path)
    latest_event = event_list[-1] if event_list else None
    fallback_created_at = None
    fallback_updated_at = None
    if isinstance(packet, dict):
        fallback_created_at = packet.get("created_at")
        fallback_updated_at = packet.get("updated_at")
    if not isinstance(fallback_created_at, str) or not fallback_created_at:
        fallback_created_at = latest_event.get("timestamp") if isinstance(latest_event, dict) else utc_now()
    if not isinstance(fallback_updated_at, str) or not fallback_updated_at:
        fallback_updated_at = latest_event.get("timestamp") if isinstance(latest_event, dict) else fallback_created_at

    try:
        payload = load_json(paths.lifecycle_path) if paths.lifecycle_path.exists() else None
    except Exception:
        payload = None
    lifecycle = normalize_task_lifecycle(
        payload,
        task_id=paths.task_id,
        fallback_created_at=fallback_created_at,
        fallback_updated_at=fallback_updated_at,
    )
    if payload != lifecycle:
        write_json(paths.lifecycle_path, lifecycle)
    return lifecycle


def update_task_lifecycle(
    paths: TaskPaths,
    *,
    lifecycle_status: str | None = None,
    closed_at: str | None = None,
    closed_reason: str | None = None,
    archived_at: str | None = None,
    archive_reason: str | None = None,
    stale_at: str | None = None,
    stale_reason: str | None = None,
    canceled_at: str | None = None,
    cancel_reason: str | None = None,
    last_reconciled_at: str | None = None,
    clear_stale_fields: bool = False,
    clear_cancel_fields: bool = False,
) -> dict[str, Any]:
    lifecycle = ensure_task_lifecycle(paths)
    if lifecycle_status is not None:
        if lifecycle_status not in TASK_LIFECYCLE_STATUSES:
            raise SchemaValidationError(
                f"Task lifecycle status must be one of {TASK_LIFECYCLE_STATUSES!r}, got {lifecycle_status!r}"
            )
        lifecycle["lifecycle_status"] = lifecycle_status
    if closed_at is not None:
        lifecycle["closed_at"] = closed_at
    if closed_reason is not None:
        lifecycle["closed_reason"] = closed_reason
    if archived_at is not None:
        lifecycle["archived_at"] = archived_at
    if archive_reason is not None:
        lifecycle["archive_reason"] = archive_reason
    if stale_at is not None:
        lifecycle["stale_at"] = stale_at
    if stale_reason is not None:
        lifecycle["stale_reason"] = stale_reason
    if canceled_at is not None:
        lifecycle["canceled_at"] = canceled_at
    if cancel_reason is not None:
        lifecycle["cancel_reason"] = cancel_reason
    if last_reconciled_at is not None:
        lifecycle["last_reconciled_at"] = last_reconciled_at
    if clear_stale_fields:
        lifecycle["stale_at"] = None
        lifecycle["stale_reason"] = None
    if clear_cancel_fields:
        lifecycle["canceled_at"] = None
        lifecycle["cancel_reason"] = None
    lifecycle["updated_at"] = utc_now()
    write_json(paths.lifecycle_path, lifecycle)
    return lifecycle


def mark_task_closed(paths: TaskPaths, *, reason: str) -> dict[str, Any]:
    now = utc_now()
    return update_task_lifecycle(
        paths,
        lifecycle_status=TASK_LIFECYCLE_CLOSED,
        closed_at=now,
        closed_reason=reason,
        clear_stale_fields=True,
        last_reconciled_at=now,
    )


def mark_task_archived(paths: TaskPaths, *, reason: str) -> dict[str, Any]:
    now = utc_now()
    return update_task_lifecycle(
        paths,
        lifecycle_status=TASK_LIFECYCLE_ARCHIVED,
        archived_at=now,
        archive_reason=reason,
        last_reconciled_at=now,
    )


def mark_task_stale(paths: TaskPaths, *, reason: str) -> dict[str, Any]:
    now = utc_now()
    return update_task_lifecycle(
        paths,
        lifecycle_status=TASK_LIFECYCLE_STALE,
        stale_at=now,
        stale_reason=reason,
        last_reconciled_at=now,
    )


def mark_task_canceled(paths: TaskPaths, *, reason: str) -> dict[str, Any]:
    now = utc_now()
    return update_task_lifecycle(
        paths,
        lifecycle_status=TASK_LIFECYCLE_CANCELED,
        canceled_at=now,
        cancel_reason=reason,
        clear_stale_fields=True,
        last_reconciled_at=now,
    )


def reopen_task(paths: TaskPaths, *, reason: str) -> dict[str, Any]:
    now = utc_now()
    return update_task_lifecycle(
        paths,
        lifecycle_status=TASK_LIFECYCLE_ACTIVE,
        stale_reason=reason,
        last_reconciled_at=now,
        clear_stale_fields=True,
        clear_cancel_fields=True,
    )


def is_cleanup_eligible(lifecycle: dict[str, Any], *, now: datetime | None = None) -> bool:
    if lifecycle.get("lifecycle_status") != TASK_LIFECYCLE_ARCHIVED:
        return False
    archived_at = parse_utc_timestamp(lifecycle.get("archived_at"))
    if archived_at is None:
        return False
    comparison_time = now or datetime.now(timezone.utc)
    return comparison_time - archived_at >= timedelta(days=DEFAULT_ARCHIVE_RETENTION_DAYS)


def build_lifecycle_summary(lifecycle: dict[str, Any]) -> dict[str, Any]:
    return {
        "lifecycle_status": lifecycle.get("lifecycle_status"),
        "created_at": lifecycle.get("created_at"),
        "updated_at": lifecycle.get("updated_at"),
        "closed_at": lifecycle.get("closed_at"),
        "closed_reason": lifecycle.get("closed_reason"),
        "archived_at": lifecycle.get("archived_at"),
        "archive_reason": lifecycle.get("archive_reason"),
        "stale_at": lifecycle.get("stale_at"),
        "stale_reason": lifecycle.get("stale_reason"),
        "canceled_at": lifecycle.get("canceled_at"),
        "cancel_reason": lifecycle.get("cancel_reason"),
        "last_reconciled_at": lifecycle.get("last_reconciled_at"),
        "cleanup_eligible": is_cleanup_eligible(lifecycle),
    }


def build_recent_trusted_completion(paths: TaskPaths, report: Any) -> dict[str, Any] | None:
    if not isinstance(report, dict):
        return None

    return {
        "status": report.get("status"),
        "summary": report.get("summary"),
        "changed_files": report.get("changed_files", []),
        "verification": report.get("verification", []),
        "commit": report.get("commit"),
        "report_path": str(paths.report_path) if paths.report_path.exists() else None,
    }


def build_task_host_session_summary(
    runtime_root: str | Path | None,
    task_id: str,
) -> dict[str, Any] | None:
    try:
        from commander.transport.scripts.commander_host_runtime import (
            get_task_host_session_summary,
        )
    except Exception:
        return None
    return get_task_host_session_summary(runtime_root, task_id)


def build_task_host_wait_summary(
    runtime_root: str | Path | None,
    task_id: str,
) -> dict[str, Any] | None:
    try:
        from commander.transport.scripts.commander_host_runtime import (
            build_task_host_wait_summary as _build_task_host_wait_summary,
        )
    except Exception:
        return None
    return _build_task_host_wait_summary(runtime_root, task_id)


def _slugify_compaction_part(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return "unknown"
    normalized = []
    for character in text:
        normalized.append(character if character.isalnum() else "-")
    slug = "".join(normalized).strip("-")
    return slug or "unknown"


def _compact_resume_path_map(paths: TaskPaths) -> dict[str, str]:
    return {
        "anchor": str(paths.resume_anchor_path),
        "checkpoint": str(paths.checkpoint_path),
        "packet": str(paths.packet_path),
        "context_bundle": str(paths.context_bundle_path),
        "report": str(paths.report_path),
        "worker_report": str(paths.worker_report_path),
        "worker_brief": str(paths.worker_brief_path),
        "improvement_candidate": str(paths.improvement_candidate_path),
        "status": str(paths.status_path),
        "events": str(paths.events_path),
        "compaction_event": str(paths.compaction_event_path),
        "compactions_dir": str(paths.compactions_dir),
    }


def load_compaction_event(paths: TaskPaths) -> dict[str, Any] | None:
    if not paths.compaction_event_path.exists():
        return None
    payload = load_json(paths.compaction_event_path)
    return payload if isinstance(payload, dict) else None


def build_compaction_event_summary(paths: TaskPaths) -> dict[str, Any] | None:
    payload = load_compaction_event(paths)
    if not isinstance(payload, dict):
        return None
    artifact = payload.get("artifact") if isinstance(payload.get("artifact"), dict) else {}
    return {
        "event_id": payload.get("event_id"),
        "recorded_at": payload.get("recorded_at"),
        "source": payload.get("source"),
        "trigger": payload.get("trigger"),
        "driver_status": payload.get("driver_status"),
        "stop_reason": payload.get("stop_reason"),
        "resume_mode": payload.get("resume_mode"),
        "summary": payload.get("summary"),
        "artifact_path": artifact.get("path"),
        "artifact_kind": artifact.get("kind"),
    }


def record_task_compaction_event(
    paths: TaskPaths,
    *,
    source: str,
    trigger: str,
    thread_id: str | None = None,
    objective_id: str | None = None,
    driver_status: str | None = None,
    stop_reason: str | None = None,
    round_count: int | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    checkpoint = load_json(paths.checkpoint_path) if paths.checkpoint_path.exists() else {}
    if not isinstance(checkpoint, dict):
        checkpoint = {}
    existing = load_compaction_event(paths) or {}
    event_id = uuid4().hex
    recorded_at = utc_now()
    timestamp_slug = (
        recorded_at.replace(":", "")
        .replace("-", "")
        .replace("T", "_")
        .replace("Z", "Z")
    )
    artifact_path = paths.compactions_dir / (
        f"{timestamp_slug}_{_slugify_compaction_part(trigger)}_"
        f"{_slugify_compaction_part(driver_status)}_{event_id}.json"
    )
    artifact_payload = {
        "schema_version": COMPACTION_ARTIFACT_SCHEMA_VERSION,
        "event_id": event_id,
        "task_id": paths.task_id,
        "thread_id": thread_id,
        "objective_id": objective_id,
        "source": source,
        "trigger": trigger,
        "recorded_at": recorded_at,
        "driver_status": driver_status,
        "stop_reason": stop_reason,
        "round_count": round_count,
        "payload": payload or {},
    }
    write_json(artifact_path, artifact_payload)

    summary = (
        f"{driver_status or 'unknown'} / {stop_reason or 'unknown'} -> "
        f"{checkpoint.get('next_minimal_action') or checkpoint.get('recommended_action') or 'resume from compact event'}"
    )
    compaction_event = {
        "schema_version": COMPACTION_EVENT_SCHEMA_VERSION,
        "resume_mode": "compaction_event",
        "event_id": event_id,
        "recorded_at": recorded_at,
        "task_id": paths.task_id,
        "thread_id": thread_id,
        "objective_id": objective_id,
        "source": source,
        "trigger": trigger,
        "driver_status": driver_status,
        "stop_reason": stop_reason,
        "round_count": round_count,
        "summary": summary,
        "current_phase": checkpoint.get("current_phase"),
        "lifecycle_status": checkpoint.get("lifecycle_status"),
        "worker_status": checkpoint.get("worker_status"),
        "controller_handoff": checkpoint.get("controller_handoff"),
        "continuation_mode": checkpoint.get("continuation_mode"),
        "recommended_action": checkpoint.get("recommended_action"),
        "next_minimal_action": checkpoint.get("next_minimal_action"),
        "pending_decisions": checkpoint.get("pending_decisions") or [],
        "blockers": checkpoint.get("blockers") or [],
        "intent_binding": checkpoint.get("intent_binding"),
        "host_session": checkpoint.get("host_session"),
        "host_wait": checkpoint.get("host_wait"),
        "recent_trusted_completion": checkpoint.get("recent_trusted_completion"),
        "artifact": {
            "kind": "graph_handoff_payload",
            "path": str(artifact_path),
        },
        "resume_entry": {
            "task_id": paths.task_id,
            "compact_anchor_path": str(paths.compaction_event_path),
            "resume_anchor_path": str(paths.resume_anchor_path),
            "checkpoint_path": str(paths.checkpoint_path),
        },
        "previous_event_id": existing.get("event_id"),
        "key_paths": _compact_resume_path_map(paths),
    }
    write_json(paths.compaction_event_path, compaction_event)
    if paths.task_dir.exists():
        refresh_status(paths)
    return compaction_event


def build_resume_anchor(paths: TaskPaths, checkpoint: dict[str, Any]) -> dict[str, Any]:
    recent_trusted_completion = checkpoint.get("recent_trusted_completion")
    if isinstance(recent_trusted_completion, dict):
        recent_trusted_completion = {
            "status": recent_trusted_completion.get("status"),
            "summary": recent_trusted_completion.get("summary"),
            "commit": recent_trusted_completion.get("commit"),
            "report_path": recent_trusted_completion.get("report_path"),
        }
    else:
        recent_trusted_completion = None

    active_subagents_summary = checkpoint.get("active_subagents_summary")
    if not isinstance(active_subagents_summary, dict):
        active_subagents_summary = {
            "open_count": 0,
            "open_agent_ids": [],
            "open_nicknames": [],
            "states": [],
            "blocked_count": 0,
            "blocked_agent_ids": [],
            "blocked_nicknames": [],
            "has_open_subagents": False,
            "has_blocked_subagents": False,
        }

    worker_binding = checkpoint.get("worker_binding")
    if not isinstance(worker_binding, dict):
        worker_binding = {}

    improvement_candidate = checkpoint.get("improvement_candidate")
    if isinstance(improvement_candidate, dict):
        improvement_candidate = {
            "candidate_id": improvement_candidate.get("candidate_id"),
            "recommended_layer": improvement_candidate.get("recommended_layer"),
            "recommended_target": improvement_candidate.get("recommended_target"),
            "status": improvement_candidate.get("status"),
            "candidate_path": improvement_candidate.get("candidate_path"),
        }
    else:
        improvement_candidate = None

    intent_binding = checkpoint.get("intent_binding")
    if isinstance(intent_binding, dict):
        intent_binding = {
            "last_open_offer": intent_binding.get("last_open_offer"),
            "pending_user_reply_target": intent_binding.get(
                "pending_user_reply_target"
            ),
            "offer_confirmed": bool(intent_binding.get("offer_confirmed")),
            "latest_user_reply_text": intent_binding.get("latest_user_reply_text"),
            "latest_user_reply_kind": intent_binding.get("latest_user_reply_kind"),
            "resolved_reply_target": intent_binding.get("resolved_reply_target"),
            "binding_reason": intent_binding.get("binding_reason"),
        }
    else:
        intent_binding = build_intent_binding_state()

    host_session = checkpoint.get("host_session")
    if isinstance(host_session, dict):
        host_session = {
            "session_id": host_session.get("session_id"),
            "provider_id": host_session.get("provider_id"),
            "provider_label": host_session.get("provider_label"),
            "session_status": host_session.get("session_status"),
            "updated_at": host_session.get("updated_at"),
            "last_heartbeat_at": host_session.get("last_heartbeat_at"),
            "attached_report_path": host_session.get("attached_report_path"),
            "host_controls": host_session.get("host_controls"),
        }
    else:
        host_session = None

    host_wait = checkpoint.get("host_wait")
    if isinstance(host_wait, dict):
        host_wait = {
            "session_id": host_wait.get("session_id"),
            "session_status": host_wait.get("session_status"),
            "wait_reason": host_wait.get("wait_reason"),
            "next_action": host_wait.get("next_action"),
            "report_available": bool(host_wait.get("report_available")),
            "report_source": host_wait.get("report_source"),
            "report_path": host_wait.get("report_path"),
            "timed_out": bool(host_wait.get("timed_out")),
            "resume_recommended": bool(host_wait.get("resume_recommended")),
            "host_controls": host_wait.get("host_controls"),
        }
    else:
        host_wait = None

    compaction_event = build_compaction_event_summary(paths)
    context_budget = build_compact_context_budget_summary(
        checkpoint.get("context_budget")
        if isinstance(checkpoint.get("context_budget"), dict)
        else None
    )

    return {
        "schema_version": checkpoint.get("schema_version", "commander-harness-v1"),
        "resume_mode": "compact",
        "task_id": checkpoint.get("task_id", paths.task_id),
        "title": checkpoint.get("title"),
        "summary": (
            f"{checkpoint.get('current_phase')} -> {checkpoint.get('next_minimal_action')}"
            if checkpoint.get("current_phase") or checkpoint.get("next_minimal_action")
            else None
        ),
        "current_phase": checkpoint.get("current_phase"),
        "recommended_action": checkpoint.get("recommended_action"),
        "next_minimal_action": checkpoint.get("next_minimal_action"),
        "lifecycle_status": checkpoint.get("lifecycle_status"),
        "cleanup_eligible": checkpoint.get("cleanup_eligible"),
        "controller_handoff": checkpoint.get("controller_handoff"),
        "conversation_stop_required": checkpoint.get("conversation_stop_required"),
        "conversation_stop_reason": checkpoint.get("conversation_stop_reason"),
        "commander_recommendation": checkpoint.get("commander_recommendation"),
        "worker_status": checkpoint.get("worker_status"),
        "result_grade": checkpoint.get("result_grade"),
        "next_action_owner": checkpoint.get("next_action_owner"),
        "continuation_mode": checkpoint.get("continuation_mode"),
        "decision_reason": checkpoint.get("decision_reason"),
        "needs_commander_decision": checkpoint.get("needs_commander_decision"),
        "needs_user_decision": checkpoint.get("needs_user_decision"),
        "ready_for_user_delivery": checkpoint.get("ready_for_user_delivery"),
        "last_open_offer": intent_binding.get("last_open_offer"),
        "pending_user_reply_target": intent_binding.get(
            "pending_user_reply_target"
        ),
        "offer_confirmed": bool(intent_binding.get("offer_confirmed")),
        "latest_user_reply_text": intent_binding.get("latest_user_reply_text"),
        "intent_binding": intent_binding,
        "dispatch_kind": checkpoint.get("dispatch_kind"),
        "source_task_id": checkpoint.get("source_task_id"),
        "parent_task_id": checkpoint.get("parent_task_id"),
        "task_owner": checkpoint.get("task_owner"),
        "closure_policy": checkpoint.get("closure_policy"),
        "worker_profile": checkpoint.get("worker_profile"),
        "preferred_worker_profile": checkpoint.get("preferred_worker_profile"),
        "reuse_allowed": checkpoint.get("reuse_allowed"),
        "tool_profile": checkpoint.get("tool_profile"),
        "allowed_tools": checkpoint.get("allowed_tools"),
        "worker_binding": worker_binding,
        "host_session": host_session,
        "host_wait": host_wait,
        "context_budget": context_budget,
        "compaction_event": compaction_event,
        "active_subagents_summary": active_subagents_summary,
        "recent_trusted_completion": recent_trusted_completion,
        "improvement_candidate": improvement_candidate,
        "blockers": list(checkpoint.get("blockers", []))[:3],
        "pending_decisions": list(checkpoint.get("pending_decisions", []))[:3],
        "key_paths": _compact_resume_path_map(paths),
        "read_order": [
            str(paths.compaction_event_path),
            str(paths.resume_anchor_path),
            str(paths.checkpoint_path),
        ],
        "event_count": checkpoint.get("event_count"),
        "last_event_type": checkpoint.get("last_event_type"),
        "last_event_at": checkpoint.get("last_event_at"),
        "updated_at": checkpoint.get("updated_at"),
        "resume_hint": "Read compaction_event.json first after compression; open resume_anchor.json or checkpoint.json only when deeper detail is needed.",
    }


def load_improvement_candidate(paths: TaskPaths) -> dict[str, Any] | None:
    if not paths.improvement_candidate_path.exists():
        return None

    try:
        candidate = load_json(paths.improvement_candidate_path)
        if not isinstance(candidate, dict):
            return None
        validate_instance(candidate, load_schema(IMPROVEMENT_SCHEMA_PATH))
    except Exception:
        return None
    return candidate


def build_improvement_candidate_anchor(paths: TaskPaths, candidate: Any) -> dict[str, Any] | None:
    if not isinstance(candidate, dict):
        return None

    return {
        "candidate_id": candidate.get("candidate_id"),
        "status": candidate.get("status"),
        "recommended_layer": candidate.get("recommended_layer"),
        "recommended_target": candidate.get("recommended_target"),
        "source_summary": candidate.get("source_summary"),
        "source_report_path": candidate.get("source_report_path"),
        "created_at": candidate.get("created_at"),
        "candidate_path": str(paths.improvement_candidate_path),
    }


def build_pending_close_worker_attention(
    *,
    controller_handoff: str,
    next_minimal_action: str,
    recent_trusted_completion: dict[str, Any] | None,
    improvement_candidate: dict[str, Any] | None,
    catalog_refresh: dict[str, Any] | None,
    worker_binding: dict[str, Any] | None,
    active_subagent_summary: dict[str, Any],
    decision_gates: dict[str, Any],
    split_suggestion: dict[str, Any] | None,
) -> dict[str, Any]:
    anchors: list[dict[str, Any]] = []
    if recent_trusted_completion is not None:
        anchors.append(
            {
                "kind": "trusted_report",
                "path": recent_trusted_completion.get("report_path"),
                "status": recent_trusted_completion.get("status"),
                "summary": recent_trusted_completion.get("summary"),
            }
        )
    if improvement_candidate is not None:
        anchors.append(
            {
                "kind": "improvement_candidate",
                "candidate_id": improvement_candidate.get("candidate_id"),
                "candidate_path": improvement_candidate.get("candidate_path"),
                "status": improvement_candidate.get("status"),
                "recommended_layer": improvement_candidate.get("recommended_layer"),
                "recommended_target": improvement_candidate.get("recommended_target"),
            }
        )
    if isinstance(catalog_refresh, dict) and catalog_refresh.get("status") == CATALOG_REFRESH_STATUS_FAILED:
        anchors.append(
            {
                "kind": "catalog_refresh",
                "status": catalog_refresh.get("status"),
                "reason": catalog_refresh.get("reason"),
                "attempted_at": catalog_refresh.get("attempted_at"),
                "error_type": catalog_refresh.get("error_type"),
                "error_message": catalog_refresh.get("error_message"),
                "path": catalog_refresh.get("path"),
            }
        )
    if isinstance(worker_binding, dict) and worker_binding.get("has_binding"):
        anchors.append(
            {
                "kind": "worker_binding",
                "binding_health": worker_binding.get("binding_health"),
                "worker_ids": worker_binding.get("worker_ids", []),
                "leased_worker_ids": worker_binding.get("leased_worker_ids", []),
                "expired_leased_worker_ids": worker_binding.get("expired_leased_worker_ids", []),
                "canonical_worker_id": worker_binding.get("canonical_worker_id"),
                "duplicate_worker_ids": worker_binding.get("duplicate_worker_ids", []),
            }
        )

    anchors.append(
        {
            "kind": "controller_handoff",
            "value": controller_handoff,
        }
    )
    anchors.append(
        {
            "kind": "decision_gate",
            "summary": decision_gates.get("summary"),
            "commander_required": decision_gates.get("commander_required"),
            "user_required": decision_gates.get("user_required"),
            "reason": decision_gates.get("reason"),
        }
    )
    if split_suggestion is not None:
        anchors.append(
            {
                "kind": "split_suggestion",
                "title": split_suggestion.get("title"),
                "goal": split_suggestion.get("goal"),
                "reason": split_suggestion.get("reason"),
                "suggested_task_id": split_suggestion.get("suggested_task_id"),
            }
        )

    if active_subagent_summary["has_open_subagents"]:
        active_subagent_blocker = describe_active_subagent_blocker(active_subagent_summary)
        anchors.append(
            {
                "kind": "open_subagents",
                "open_agent_ids": active_subagent_summary["open_agent_ids"],
                "open_nicknames": active_subagent_summary["open_nicknames"],
                "states": active_subagent_summary["states"],
                "state_counts": active_subagent_summary["state_counts"],
                "reason": (
                    active_subagent_blocker["reason"]
                    if active_subagent_blocker is not None
                    else "Reconcile or close active_subagents before closing the task"
                ),
            }
        )

    return {
        "anchors": anchors,
        "controller_handoff": controller_handoff,
        "next_minimal_action": next_minimal_action,
        "has_open_subagents": active_subagent_summary["has_open_subagents"],
    }


def load_checkpoint_payload(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    checkpoint = load_json(path)
    if not isinstance(checkpoint, dict):
        raise SchemaValidationError(f"Checkpoint root must be an object: {path}")
    return checkpoint


def normalize_active_subagent(payload: Any, *, fallback_task_id: str) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None

    agent_id = payload.get("agent_id")
    state = payload.get("state")
    nickname = payload.get("nickname")
    opened_at = payload.get("opened_at")
    updated_at = payload.get("updated_at")
    task_id = payload.get("task_id")

    if not isinstance(agent_id, str) or not agent_id:
        return None
    if not isinstance(state, str) or state not in ACTIVE_SUBAGENT_OPEN_STATES:
        return None

    opened_at_value = opened_at if isinstance(opened_at, str) and opened_at else None
    updated_at_value = updated_at if isinstance(updated_at, str) and updated_at else None
    if opened_at_value is None:
        opened_at_value = updated_at_value
    if updated_at_value is None:
        updated_at_value = opened_at_value

    return {
        "agent_id": agent_id,
        "nickname": nickname if isinstance(nickname, str) and nickname else agent_id,
        "state": state,
        "opened_at": opened_at_value,
        "updated_at": updated_at_value,
        "task_id": task_id if isinstance(task_id, str) and task_id else fallback_task_id,
    }


def load_active_subagents(paths: TaskPaths) -> list[dict[str, Any]]:
    checkpoint = load_checkpoint_payload(paths.checkpoint_path)
    if checkpoint is None:
        return []
    raw_active_subagents = checkpoint.get("active_subagents")
    if not isinstance(raw_active_subagents, list):
        return []

    active_subagents: list[dict[str, Any]] = []
    for item in raw_active_subagents:
        normalized = normalize_active_subagent(item, fallback_task_id=paths.task_id)
        if normalized is not None:
            active_subagents.append(normalized)
    return active_subagents


def build_active_subagent_summary(active_subagents: list[dict[str, Any]]) -> dict[str, Any]:
    state_counts: dict[str, int] = {}
    state_agent_ids: dict[str, list[str]] = {}
    state_nicknames: dict[str, list[str]] = {}
    for item in active_subagents:
        state = item["state"]
        state_counts[state] = state_counts.get(state, 0) + 1
        state_agent_ids.setdefault(state, []).append(item["agent_id"])
        state_nicknames.setdefault(state, []).append(item["nickname"])

    return {
        "open_count": len(active_subagents),
        "open_agent_ids": [item["agent_id"] for item in active_subagents],
        "open_nicknames": [item["nickname"] for item in active_subagents],
        "states": sorted({item["state"] for item in active_subagents}),
        "state_counts": state_counts,
        "running_count": state_counts.get(ACTIVE_SUBAGENT_RUNNING, 0),
        "running_agent_ids": state_agent_ids.get(ACTIVE_SUBAGENT_RUNNING, []),
        "running_nicknames": state_nicknames.get(ACTIVE_SUBAGENT_RUNNING, []),
        "blocked_count": state_counts.get(ACTIVE_SUBAGENT_BLOCKED, 0),
        "blocked_agent_ids": state_agent_ids.get(ACTIVE_SUBAGENT_BLOCKED, []),
        "blocked_nicknames": state_nicknames.get(ACTIVE_SUBAGENT_BLOCKED, []),
        "completed_waiting_close_count": state_counts.get(ACTIVE_SUBAGENT_COMPLETED_WAITING_CLOSE, 0),
        "completed_waiting_close_agent_ids": state_agent_ids.get(ACTIVE_SUBAGENT_COMPLETED_WAITING_CLOSE, []),
        "completed_waiting_close_nicknames": state_nicknames.get(ACTIVE_SUBAGENT_COMPLETED_WAITING_CLOSE, []),
        "has_open_subagents": bool(active_subagents),
        "has_running_subagents": bool(state_counts.get(ACTIVE_SUBAGENT_RUNNING, 0)),
        "has_blocked_subagents": bool(state_counts.get(ACTIVE_SUBAGENT_BLOCKED, 0)),
        "has_completed_waiting_close_subagents": bool(
            state_counts.get(ACTIVE_SUBAGENT_COMPLETED_WAITING_CLOSE, 0)
        ),
    }


def describe_active_subagent_blocker(active_subagent_summary: dict[str, Any]) -> dict[str, Any] | None:
    if not bool(active_subagent_summary.get("has_open_subagents")):
        return None

    running_count = int(active_subagent_summary.get("running_count") or 0)
    blocked_count = int(active_subagent_summary.get("blocked_count") or 0)
    waiting_close_count = int(active_subagent_summary.get("completed_waiting_close_count") or 0)
    if running_count:
        return {
            "state": ACTIVE_SUBAGENT_RUNNING,
            "reason": "active_subagents_are_still_running",
            "count": running_count,
            "next_action": "Wait for running sub-agents to finish or reassign them before closing the task.",
        }
    if blocked_count:
        return {
            "state": ACTIVE_SUBAGENT_BLOCKED,
            "reason": "active_subagents_are_blocked",
            "count": blocked_count,
            "next_action": "Unblock or close blocked sub-agents before closing the task.",
        }
    if waiting_close_count:
        return {
            "state": ACTIVE_SUBAGENT_COMPLETED_WAITING_CLOSE,
            "reason": "active_subagents_have_completed_results_pending_close",
            "count": waiting_close_count,
            "next_action": "Recover the completed results and close the sub-agents before closing the task.",
        }
    return {
        "state": "unknown",
        "reason": "active_subagents_are_open",
        "count": int(active_subagent_summary.get("open_count") or 0),
        "next_action": "Reconcile or close active_subagents before closing the task.",
    }


def _coerce_active_subagent_state_from_status_payload(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None

    status_candidates = payload
    nested_status = payload.get("status")
    if isinstance(nested_status, dict):
        status_candidates = nested_status

    for key, state in (
        ("running", ACTIVE_SUBAGENT_RUNNING),
        ("completed", ACTIVE_SUBAGENT_COMPLETED_WAITING_CLOSE),
        ("blocked", ACTIVE_SUBAGENT_BLOCKED),
        ("shutdown", ACTIVE_SUBAGENT_CLOSED),
        ("closed", ACTIVE_SUBAGENT_CLOSED),
    ):
        if key in status_candidates and status_candidates.get(key) not in (None, ""):
            return state

    raw_state = status_candidates.get("state")
    if isinstance(raw_state, str):
        normalized = raw_state.strip()
        if normalized in ACTIVE_SUBAGENT_OPEN_STATES or normalized == ACTIVE_SUBAGENT_CLOSED:
            return normalized
    return None


def _coerce_active_subagent_identity(
    payload: Any,
    *,
    fallback_agent_id: str | None = None,
    fallback_nickname: str | None = None,
) -> tuple[str | None, str | None]:
    if not isinstance(payload, dict):
        return fallback_agent_id, fallback_nickname

    candidate_sources = [payload]
    nested_status = payload.get("status")
    if isinstance(nested_status, dict):
        candidate_sources.insert(0, nested_status)

    agent_id = fallback_agent_id
    nickname = fallback_nickname
    for source in candidate_sources:
        if agent_id is None:
            for key in ("agent_id", "agent_path"):
                value = source.get(key)
                if isinstance(value, str) and value.strip():
                    text = value.strip()
                    agent_id = Path(text).name or text
                    break
        if nickname is None:
            for key in ("nickname", "agent_name", "display_name"):
                value = source.get(key)
                if isinstance(value, str) and value.strip():
                    nickname = value.strip()
                    break

    if nickname is None:
        nickname = agent_id
    return agent_id, nickname


def normalize_active_subagent_update(
    payload: Any,
    *,
    fallback_task_id: str,
    fallback_agent_id: str | None = None,
    fallback_nickname: str | None = None,
    default_state: str | None = None,
) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None

    nested_status = payload.get("status")
    if isinstance(nested_status, dict):
        for candidate_agent_id, candidate_payload in nested_status.items():
            if not isinstance(candidate_agent_id, str) or not isinstance(
                candidate_payload, dict
            ):
                continue
            normalized = normalize_active_subagent_update(
                candidate_payload,
                fallback_task_id=fallback_task_id,
                fallback_agent_id=candidate_agent_id,
                fallback_nickname=fallback_nickname,
                default_state=default_state,
            )
            if normalized is not None:
                return normalized

    state = _coerce_active_subagent_state_from_status_payload(payload)
    if state is None and isinstance(default_state, str):
        normalized_default_state = default_state.strip()
        if normalized_default_state in ACTIVE_SUBAGENT_OPEN_STATES or normalized_default_state == ACTIVE_SUBAGENT_CLOSED:
            state = normalized_default_state
    if state is None:
        return None

    agent_id, nickname = _coerce_active_subagent_identity(
        payload,
        fallback_agent_id=fallback_agent_id,
        fallback_nickname=fallback_nickname,
    )
    if not isinstance(agent_id, str) or not agent_id:
        return None
    return {
        "agent_id": agent_id,
        "nickname": nickname if isinstance(nickname, str) and nickname else agent_id,
        "state": state,
        "task_id": fallback_task_id,
    }


def set_active_subagent_state(
    paths: TaskPaths,
    *,
    agent_id: str,
    nickname: str | None,
    state: str,
) -> list[dict[str, Any]]:
    checkpoint = load_checkpoint_payload(paths.checkpoint_path)
    if checkpoint is None:
        checkpoint = {
            "schema_version": "commander-harness-v1",
            "task_id": paths.task_id,
        }

    active_subagents = load_active_subagents(paths)
    now = utc_now()
    existing = next((item for item in active_subagents if item["agent_id"] == agent_id), None)

    if state == ACTIVE_SUBAGENT_CLOSED:
        active_subagents = [item for item in active_subagents if item["agent_id"] != agent_id]
    else:
        active_subagents = [item for item in active_subagents if item["agent_id"] != agent_id]
        active_subagents.append(
            {
                "agent_id": agent_id,
                "nickname": nickname if nickname else (existing["nickname"] if existing else agent_id),
                "state": state,
                "opened_at": existing["opened_at"] if existing else now,
                "updated_at": now,
                "task_id": paths.task_id,
            }
        )

    checkpoint["active_subagents"] = active_subagents
    checkpoint["updated_at"] = now
    write_json(paths.checkpoint_path, checkpoint)
    return active_subagents


def sync_active_subagent_state_from_payload(
    paths: TaskPaths,
    payload: Any,
    *,
    agent_id: str | None = None,
    nickname: str | None = None,
    state: str | None = None,
) -> list[dict[str, Any]]:
    normalized = normalize_active_subagent_update(
        payload,
        fallback_task_id=paths.task_id,
        fallback_agent_id=agent_id,
        fallback_nickname=nickname,
    )
    if normalized is not None:
        agent_id = normalized["agent_id"]
        nickname = normalized["nickname"]
        state = normalized["state"]

    if not isinstance(agent_id, str) or not agent_id:
        raise SchemaValidationError("Active sub-agent sync requires an agent_id")
    if not isinstance(state, str) or not state:
        raise SchemaValidationError("Active sub-agent sync requires a lifecycle state")
    return set_active_subagent_state(
        paths,
        agent_id=agent_id,
        nickname=nickname,
        state=state,
    )


def normalize_runtime_root(runtime_root: str | Path | None) -> Path:
    if runtime_root is None:
        return DEFAULT_RUNTIME_ROOT
    return Path(runtime_root).resolve()


def validate_instance(instance: Any, schema: dict[str, Any], *, path: str = "$") -> None:
    declared_type = schema.get("type")
    if declared_type is not None and not _matches_declared_type(instance, declared_type):
        raise SchemaValidationError(
            f"{path}: expected type {_describe_declared_type(declared_type)}, got {type(instance).__name__}"
        )

    if "enum" in schema and instance not in schema["enum"]:
        raise SchemaValidationError(f"{path}: value {instance!r} is not in enum {schema['enum']!r}")

    if "const" in schema and instance != schema["const"]:
        raise SchemaValidationError(f"{path}: value {instance!r} must equal {schema['const']!r}")

    if isinstance(instance, str):
        min_length = schema.get("minLength")
        if min_length is not None and len(instance) < min_length:
            raise SchemaValidationError(f"{path}: string length must be >= {min_length}")

    if isinstance(instance, list):
        min_items = schema.get("minItems")
        if min_items is not None and len(instance) < min_items:
            raise SchemaValidationError(f"{path}: array length must be >= {min_items}")
        item_schema = schema.get("items")
        if item_schema is not None:
            for index, value in enumerate(instance):
                validate_instance(value, item_schema, path=f"{path}[{index}]")

    if isinstance(instance, dict):
        required = schema.get("required", [])
        for key in required:
            if key not in instance:
                raise SchemaValidationError(f"{path}: missing required property {key!r}")

        properties = schema.get("properties", {})
        additional_properties = schema.get("additionalProperties", True)
        for key, value in instance.items():
            if key in properties:
                validate_instance(value, properties[key], path=f"{path}.{key}")
                continue
            if additional_properties is False:
                raise SchemaValidationError(f"{path}: unexpected property {key!r}")


def ensure_report_ready_for_ingest(report_payload: Any) -> None:
    if not isinstance(report_payload, dict):
        raise SchemaValidationError("Worker report root must be an object before ingest")

    if is_dispatch_draft_report(report_payload):
        raise SchemaValidationError(
            "Worker report is still marked as a dispatch draft; "
            f"set {REPORT_DRAFT_METADATA_FIELD}.{REPORT_DRAFT_METADATA_FLAG} to false "
            "or remove the metadata before ingest."
        )

    draft_paths = find_report_draft_markers(report_payload)
    if draft_paths:
        joined_paths = ", ".join(draft_paths)
        raise SchemaValidationError(
            "Worker report still contains dispatch draft placeholder content; "
            f"update the real result before ingest. Paths: {joined_paths}"
        )


def build_dispatch_governance(packet: Any) -> dict[str, Any]:
    if not isinstance(packet, dict):
        return {
            "dispatch_kind": DISPATCH_KIND_FRESH,
            "source_task_id": None,
            "parent_task_id": None,
            "task_owner": "commander",
            "closure_policy": CLOSURE_POLICY_CLOSE_WHEN_VALIDATED,
        }

    dispatch_kind = packet.get("dispatch_kind")
    if dispatch_kind not in DISPATCH_KINDS:
        dispatch_kind = DISPATCH_KIND_FRESH
    closure_policy = packet.get("closure_policy")
    if closure_policy not in CLOSURE_POLICIES:
        closure_policy = CLOSURE_POLICY_CLOSE_WHEN_VALIDATED

    source_task_id = packet.get("source_task_id")
    if not isinstance(source_task_id, str) or not source_task_id:
        source_task_id = None
    parent_task_id = packet.get("parent_task_id")
    if not isinstance(parent_task_id, str) or not parent_task_id:
        parent_task_id = None
    task_owner = packet.get("task_owner")
    if not isinstance(task_owner, str) or not task_owner:
        task_owner = "commander"

    return {
        "dispatch_kind": dispatch_kind,
        "source_task_id": source_task_id,
        "parent_task_id": parent_task_id,
        "task_owner": task_owner,
        "closure_policy": closure_policy,
    }


def normalize_split_suggestion(payload: Any) -> dict[str, Any] | None:
    if payload is None:
        return None
    if not isinstance(payload, dict):
        return None

    title = payload.get("title")
    goal = payload.get("goal")
    reason = payload.get("reason")
    if not all(isinstance(value, str) and value.strip() for value in (title, goal, reason)):
        return None

    suggested_task_id = payload.get("suggested_task_id")
    if not isinstance(suggested_task_id, str) or not suggested_task_id.strip():
        suggested_task_id = None

    return {
        "title": title.strip(),
        "goal": goal.strip(),
        "reason": reason.strip(),
        "suggested_task_id": suggested_task_id.strip() if isinstance(suggested_task_id, str) else None,
    }


def build_result_governance(report: Any) -> dict[str, Any]:
    if not isinstance(report, dict):
        return {
            "result_grade": None,
            "next_action_owner": NEXT_ACTION_OWNER_COMMANDER,
            "continuation_mode": None,
            "decision_reason": None,
            "split_suggestion": None,
        }

    worker_status = report.get("status")
    needs_commander_decision = bool(report.get("needs_commander_decision"))
    needs_user_decision = bool(report.get("needs_user_decision"))
    ready_for_user_delivery = bool(report.get("ready_for_user_delivery"))

    result_grade = report.get("result_grade")
    if result_grade not in RESULT_GRADES:
        if worker_status == "done" and not needs_commander_decision and not needs_user_decision:
            result_grade = RESULT_GRADE_CLOSED
        elif worker_status in {"blocked", "need_split"}:
            result_grade = RESULT_GRADE_BLOCKED
        else:
            result_grade = RESULT_GRADE_PARTIAL

    next_action_owner = report.get("next_action_owner")
    if next_action_owner not in NEXT_ACTION_OWNERS:
        if needs_user_decision:
            next_action_owner = NEXT_ACTION_OWNER_USER
        else:
            next_action_owner = NEXT_ACTION_OWNER_COMMANDER

    continuation_mode = report.get("continuation_mode")
    if continuation_mode not in CONTINUATION_MODES:
        if needs_user_decision:
            continuation_mode = CONTINUATION_MODE_WAIT_USER
        elif worker_status == "need_split":
            continuation_mode = CONTINUATION_MODE_SPLIT
        elif worker_status == "done" and not needs_commander_decision and not ready_for_user_delivery:
            continuation_mode = CONTINUATION_MODE_CLOSE
        elif ready_for_user_delivery and worker_status == "done":
            continuation_mode = CONTINUATION_MODE_CLOSE
        else:
            continuation_mode = CONTINUATION_MODE_FOLLOWUP

    decision_reason = report.get("decision_reason")
    if not isinstance(decision_reason, str) or not decision_reason.strip():
        if needs_user_decision:
            decision_reason = report.get("user_decision_reason")
        elif worker_status in {"blocked", "need_split"} or needs_commander_decision:
            decision_reason = report.get("recommended_next_step")
        else:
            decision_reason = None
    if isinstance(decision_reason, str):
        decision_reason = decision_reason.strip() or None

    split_suggestion = normalize_split_suggestion(report.get("split_suggestion"))
    if split_suggestion is None and continuation_mode == CONTINUATION_MODE_SPLIT:
        fallback_reason = decision_reason or "Split this work into a narrower follow-up task."
        task_id = report.get("task_id")
        split_suggestion = {
            "title": f"Follow-up split for {task_id}" if isinstance(task_id, str) and task_id else "Follow-up split",
            "goal": fallback_reason,
            "reason": fallback_reason,
            "suggested_task_id": None,
        }

    return {
        "result_grade": result_grade,
        "next_action_owner": next_action_owner,
        "continuation_mode": continuation_mode,
        "decision_reason": decision_reason,
        "split_suggestion": split_suggestion,
    }


def build_decision_gates(packet: Any, report: Any, result_governance: dict[str, Any]) -> dict[str, Any]:
    dispatch_governance = build_dispatch_governance(packet)
    needs_user_decision = bool(report.get("needs_user_decision")) if isinstance(report, dict) else False
    needs_commander_decision = bool(report.get("needs_commander_decision")) if isinstance(report, dict) else False
    worker_status = report.get("status") if isinstance(report, dict) else None
    continuation_mode = result_governance.get("continuation_mode")
    decision_reason = result_governance.get("decision_reason")

    commander_required = bool(
        needs_commander_decision
        or worker_status in {"blocked", "need_split"}
        or continuation_mode in {CONTINUATION_MODE_FOLLOWUP, CONTINUATION_MODE_SPLIT}
        or (
            dispatch_governance["closure_policy"] == CLOSURE_POLICY_REQUIRE_COMMANDER_REVIEW
            and worker_status == "done"
        )
    )
    user_required = bool(needs_user_decision or continuation_mode == CONTINUATION_MODE_WAIT_USER)

    if user_required:
        summary = "user_decision_required"
    elif commander_required:
        summary = "commander_decision_required"
    else:
        summary = "no_open_decision_gate"

    return {
        "commander_required": commander_required,
        "user_required": user_required,
        "reason": decision_reason,
        "summary": summary,
    }


def derive_base_commander_recommendation(
    *,
    packet: Any,
    worker_status: str | None,
    needs_commander_decision: bool,
    result_governance: dict[str, Any],
    decision_gates: dict[str, Any],
) -> str:
    if decision_gates["user_required"]:
        return "pending_user"
    if worker_status == "done" and result_governance.get("continuation_mode") == CONTINUATION_MODE_CLOSE:
        return "ready_to_close"
    if worker_status in {"blocked", "need_split"}:
        return "needs_commander_decision"
    if decision_gates["commander_required"]:
        return "needs_commander_decision"
    if worker_status == "done":
        return "ready_to_close"
    if packet is not None:
        return "awaiting_report"
    return "missing_packet"


def derive_closed_loop_phase(
    *,
    lifecycle_status: str,
    cleanup_eligible: bool,
    packet: Any,
    worker_status: str | None,
    needs_commander_decision: bool,
    needs_user_decision: bool,
    ready_for_user_delivery: bool,
    result_governance: dict[str, Any],
    decision_gates: dict[str, Any],
) -> tuple[str, str]:
    if lifecycle_status == TASK_LIFECYCLE_ARCHIVED:
        if cleanup_eligible:
            return "archived", "cleanup_archived_task"
        return "archived", "retain_until_cleanup_window"
    if lifecycle_status == TASK_LIFECYCLE_CLOSED:
        return "closed", "archive_task"
    if lifecycle_status == TASK_LIFECYCLE_STALE:
        return "stale", "reconcile_task"
    if lifecycle_status == TASK_LIFECYCLE_CANCELED:
        return "canceled", "review_canceled_task"
    if needs_user_decision or decision_gates["user_required"]:
        return "pending_user", "request_user_decision"
    if ready_for_user_delivery and worker_status == "done":
        return "ready_for_user_delivery", "return_final_result"
    if worker_status == "need_split" or result_governance.get("continuation_mode") == CONTINUATION_MODE_SPLIT:
        return "needs_commander_decision", "review_split_suggestion"
    if worker_status == "blocked" or result_governance.get("result_grade") == RESULT_GRADE_BLOCKED:
        return "blocked", "review_blockers"
    if worker_status == "done" and (needs_commander_decision or decision_gates["commander_required"]):
        return "needs_commander_decision", "review_report_and_decide"
    if worker_status == "done":
        return "ready_to_close", "close_task"
    if packet is not None:
        return "awaiting_report", "wait_for_worker_report"
    return "missing_packet", "recreate_dispatch_packet"


def build_compact_context_budget_summary(
    context_budget: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(context_budget, dict):
        return None
    return {
        "estimation_mode": context_budget.get("estimation_mode"),
        "round_budget_tokens": context_budget.get("round_budget_tokens"),
        "account_window_budget_tokens": context_budget.get(
            "account_window_budget_tokens"
        ),
        "open_now_estimated_tokens": context_budget.get("open_now_estimated_tokens"),
        "deferred_estimated_tokens": context_budget.get("deferred_estimated_tokens"),
        "full_expand_estimated_tokens": context_budget.get(
            "full_expand_estimated_tokens"
        ),
        "open_now_percent_of_round_budget": context_budget.get(
            "open_now_percent_of_round_budget"
        ),
        "full_expand_percent_of_round_budget": context_budget.get(
            "full_expand_percent_of_round_budget"
        ),
        "open_now_percent_of_account_window_budget": context_budget.get(
            "open_now_percent_of_account_window_budget"
        ),
        "full_expand_percent_of_account_window_budget": context_budget.get(
            "full_expand_percent_of_account_window_budget"
        ),
        "router_open_now_estimated_tokens": context_budget.get(
            "router_open_now_estimated_tokens"
        ),
        "router_deferred_estimated_tokens": context_budget.get(
            "router_deferred_estimated_tokens"
        ),
        "router_budget_overflow": context_budget.get("router_budget_overflow"),
        "entries_deferred_by_budget": context_budget.get("entries_deferred_by_budget"),
    }


def build_task_context_budget(
    paths: TaskPaths,
    *,
    packet: Any,
    context_bundle: Any,
    checkpoint: dict[str, Any],
    resume_anchor: dict[str, Any],
) -> dict[str, Any] | None:
    if not isinstance(packet, dict) and not isinstance(context_bundle, dict):
        return None

    open_now_artifacts: list[dict[str, Any]] = []
    deferred_artifacts: list[dict[str, Any]] = []
    read_policy: dict[str, Any] | None = None
    counted_paths = {
        str(paths.worker_brief_path),
        str(paths.packet_path),
        str(paths.context_bundle_path),
        str(paths.resume_anchor_path),
        str(paths.checkpoint_path),
    }

    if paths.worker_brief_path.exists():
        open_now_artifacts.append(
            describe_token_artifact_from_path(
                paths.worker_brief_path,
                label="worker_brief.md",
                kind="runtime_artifact_open_now",
            )
        )
    if paths.packet_path.exists():
        open_now_artifacts.append(
            describe_token_artifact_from_path(
                paths.packet_path,
                label="packet.json",
                kind="runtime_artifact_open_now",
            )
        )
    if paths.context_bundle_path.exists():
        open_now_artifacts.append(
            describe_token_artifact_from_path(
                paths.context_bundle_path,
                label="context_bundle.json",
                kind="runtime_artifact_open_now",
            )
        )

    open_now_artifacts.append(
        describe_token_artifact_from_text(
            artifact_key=str(paths.resume_anchor_path),
            label="resume_anchor.json",
            kind="runtime_artifact_open_now",
            path=paths.resume_anchor_path,
            text=json.dumps(resume_anchor, ensure_ascii=False, indent=2) + "\n",
        )
    )
    deferred_artifacts.append(
        describe_token_artifact_from_text(
            artifact_key=str(paths.checkpoint_path),
            label="checkpoint.json",
            kind="runtime_artifact_deferred",
            path=paths.checkpoint_path,
            text=json.dumps(checkpoint, ensure_ascii=False, indent=2) + "\n",
        )
    )

    if isinstance(context_bundle, dict):
        read_policy = (
            context_bundle.get("read_policy")
            if isinstance(context_bundle.get("read_policy"), dict)
            else {}
        )
        entries = context_bundle.get("entries")
        if isinstance(entries, list):
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                context_id = str(entry.get("context_id") or "context")
                immediate_paths = entry.get("paths")
                if isinstance(immediate_paths, list):
                    for raw_path in immediate_paths:
                        if not isinstance(raw_path, str) or not raw_path.strip():
                            continue
                        normalized_path = raw_path.strip()
                        if normalized_path in counted_paths:
                            continue
                        open_now_artifacts.append(
                            describe_token_artifact_from_path(
                                normalized_path,
                                label=f"{context_id}: {Path(normalized_path).name}",
                                kind="context_path_open_now",
                            )
                        )
                deferred_paths = entry.get("deferred_paths")
                if isinstance(deferred_paths, list):
                    for raw_path in deferred_paths:
                        if not isinstance(raw_path, str) or not raw_path.strip():
                            continue
                        normalized_path = raw_path.strip()
                        if normalized_path in counted_paths:
                            continue
                        deferred_artifacts.append(
                            describe_token_artifact_from_path(
                                normalized_path,
                                label=f"{context_id}: {Path(normalized_path).name}",
                                kind="context_path_deferred",
                            )
                        )

    budget_estimate = build_token_budget_estimate(
        scope="task_round_context",
        open_now_artifacts=open_now_artifacts,
        deferred_artifacts=deferred_artifacts,
    )
    if isinstance(read_policy, dict):
        budget_estimate["router_open_now_estimated_tokens"] = read_policy.get(
            "router_open_now_estimated_tokens"
        )
        budget_estimate["router_deferred_estimated_tokens"] = read_policy.get(
            "router_deferred_estimated_tokens"
        )
        budget_estimate["router_budget_overflow"] = read_policy.get(
            "router_budget_overflow"
        )
        deferred_by_budget = read_policy.get("deferred_by_budget_context_ids")
        if isinstance(deferred_by_budget, list):
            budget_estimate["entries_deferred_by_budget"] = [
                str(item)
                for item in deferred_by_budget
                if isinstance(item, str) and item.strip()
            ]
    return budget_estimate


def refresh_status(
    paths: TaskPaths, *, intent_binding_update: dict[str, Any] | None = None
) -> dict[str, Any]:
    packet = load_json(paths.packet_path) if paths.packet_path.exists() else None
    report = load_json(paths.report_path) if paths.report_path.exists() else None
    events = load_events(paths.events_path)
    latest_event = events[-1] if events else None
    lifecycle = ensure_task_lifecycle(paths, packet=packet, events=events)
    lifecycle_summary = build_lifecycle_summary(lifecycle)
    worker_binding = build_task_worker_binding_summary(paths.runtime_root, paths.task_id)
    host_session_summary = build_task_host_session_summary(
        paths.runtime_root, paths.task_id
    )
    host_wait_summary = build_task_host_wait_summary(paths.runtime_root, paths.task_id)
    catalog_refresh = build_catalog_refresh_summary(paths)
    intent_binding = build_intent_binding_state(
        existing=_load_existing_intent_binding(paths),
        update=intent_binding_update,
    )
    updated_at = utc_now()

    worker_status = report.get("status") if isinstance(report, dict) else None
    needs_commander_decision = bool(report.get("needs_commander_decision")) if isinstance(report, dict) else False
    needs_user_decision = bool(report.get("needs_user_decision")) if isinstance(report, dict) else False
    ready_for_user_delivery = bool(report.get("ready_for_user_delivery")) if isinstance(report, dict) else False
    dispatch_governance = build_dispatch_governance(packet)
    result_governance = build_result_governance(report)
    decision_gates = build_decision_gates(packet, report, result_governance)
    lifecycle_status = lifecycle_summary["lifecycle_status"]
    base_recommendation = derive_base_commander_recommendation(
        packet=packet,
        worker_status=worker_status,
        needs_commander_decision=needs_commander_decision,
        result_governance=result_governance,
        decision_gates=decision_gates,
    )
    if lifecycle_status == TASK_LIFECYCLE_ARCHIVED:
        commander_recommendation = "archived"
    elif lifecycle_status == TASK_LIFECYCLE_CLOSED:
        commander_recommendation = "closed"
    elif lifecycle_status == TASK_LIFECYCLE_STALE:
        commander_recommendation = "stale"
    elif lifecycle_status == TASK_LIFECYCLE_CANCELED:
        commander_recommendation = "canceled"
    else:
        commander_recommendation = base_recommendation

    if lifecycle_status in {
        TASK_LIFECYCLE_ARCHIVED,
        TASK_LIFECYCLE_CLOSED,
        TASK_LIFECYCLE_STALE,
        TASK_LIFECYCLE_CANCELED,
    }:
        controller_handoff = CONTROLLER_HANDOFF_CONTINUE
        conversation_stop_required = False
        conversation_stop_reason = None
    elif needs_user_decision:
        controller_handoff = CONTROLLER_HANDOFF_REQUEST_USER_DECISION
        conversation_stop_required = True
        conversation_stop_reason = "explicit_user_decision_required"
    elif ready_for_user_delivery and worker_status == "done":
        controller_handoff = CONTROLLER_HANDOFF_RETURN_FINAL_RESULT
        conversation_stop_required = True
        conversation_stop_reason = "deliverable_ready_for_user"
    elif commander_recommendation == "awaiting_report":
        controller_handoff = CONTROLLER_HANDOFF_WAIT_EXTERNAL_RESULT
        conversation_stop_required = False
        conversation_stop_reason = None
    else:
        controller_handoff = CONTROLLER_HANDOFF_CONTINUE
        conversation_stop_required = False
        conversation_stop_reason = None

    snapshot = {
        "task_id": paths.task_id,
        "title": packet.get("title") if isinstance(packet, dict) else None,
        "has_packet": packet is not None,
        "has_report": report is not None,
        "packet_status": packet.get("status") if isinstance(packet, dict) else None,
        "worker_profile": packet.get("worker_profile") if isinstance(packet, dict) else None,
        "preferred_worker_profile": packet.get("preferred_worker_profile") if isinstance(packet, dict) else None,
        "reuse_allowed": packet.get("reuse_allowed") if isinstance(packet, dict) else None,
        "tool_profile": packet.get("tool_profile") if isinstance(packet, dict) else None,
        "allowed_tools": packet.get("allowed_tools") if isinstance(packet, dict) else None,
        "worker_status": worker_status,
        "needs_commander_decision": needs_commander_decision,
        "needs_user_decision": needs_user_decision,
        "ready_for_user_delivery": ready_for_user_delivery,
        "dispatch_kind": dispatch_governance["dispatch_kind"],
        "source_task_id": dispatch_governance["source_task_id"],
        "parent_task_id": dispatch_governance["parent_task_id"],
        "task_owner": dispatch_governance["task_owner"],
        "closure_policy": dispatch_governance["closure_policy"],
        "result_grade": result_governance["result_grade"],
        "next_action_owner": result_governance["next_action_owner"],
        "continuation_mode": result_governance["continuation_mode"],
        "decision_reason": result_governance["decision_reason"],
        "split_suggestion": result_governance["split_suggestion"],
        "dispatch_governance": dispatch_governance,
        "result_governance": result_governance,
        "decision_gates": decision_gates,
        "commander_recommendation": commander_recommendation,
        "controller_handoff": controller_handoff,
        "conversation_stop_required": conversation_stop_required,
        "conversation_stop_reason": conversation_stop_reason,
        "lifecycle_status": lifecycle_summary["lifecycle_status"],
        "cleanup_eligible": lifecycle_summary["cleanup_eligible"],
        "closed_at": lifecycle_summary["closed_at"],
        "closed_reason": lifecycle_summary["closed_reason"],
        "archived_at": lifecycle_summary["archived_at"],
        "archive_reason": lifecycle_summary["archive_reason"],
        "stale_at": lifecycle_summary["stale_at"],
        "stale_reason": lifecycle_summary["stale_reason"],
        "canceled_at": lifecycle_summary["canceled_at"],
        "cancel_reason": lifecycle_summary["cancel_reason"],
        "last_reconciled_at": lifecycle_summary["last_reconciled_at"],
        "lifecycle": lifecycle_summary,
        "catalog_refresh": catalog_refresh,
        "worker_binding": worker_binding,
        "host_session": host_session_summary,
        "host_wait": host_wait_summary,
        "intent_binding": intent_binding,
        "last_open_offer": intent_binding.get("last_open_offer"),
        "pending_user_reply_target": intent_binding.get(
            "pending_user_reply_target"
        ),
        "offer_confirmed": bool(intent_binding.get("offer_confirmed")),
        "latest_user_reply_text": intent_binding.get("latest_user_reply_text"),
        "latest_user_reply_kind": intent_binding.get("latest_user_reply_kind"),
        "resolved_reply_target": intent_binding.get("resolved_reply_target"),
        "binding_reason": intent_binding.get("binding_reason"),
        "summary": report.get("summary") if isinstance(report, dict) else None,
        "recommended_next_step": report.get("recommended_next_step") if isinstance(report, dict) else None,
        "event_count": len(events),
        "last_event_type": latest_event.get("event_type") if latest_event else None,
        "last_event_at": latest_event.get("timestamp") if latest_event else None,
        "lifecycle_path": str(paths.lifecycle_path),
        "packet_path": str(paths.packet_path),
        "report_path": str(paths.report_path) if paths.report_path.exists() else None,
        "improvement_candidate_path": str(paths.improvement_candidate_path),
        "checkpoint_path": str(paths.checkpoint_path),
        "status_path": str(paths.status_path),
        "updated_at": updated_at,
    }
    checkpoint = build_checkpoint(paths, snapshot, packet, report, events, latest_event, lifecycle, worker_binding)
    snapshot["current_phase"] = checkpoint["current_phase"]
    snapshot["recommended_action"] = checkpoint["recommended_action"]
    snapshot["next_minimal_action"] = checkpoint["next_minimal_action"]
    snapshot["controller_handoff"] = checkpoint["controller_handoff"]
    snapshot["conversation_stop_required"] = checkpoint["conversation_stop_required"]
    snapshot["conversation_stop_reason"] = checkpoint["conversation_stop_reason"]
    snapshot["recent_trusted_completion"] = checkpoint["recent_trusted_completion"]
    snapshot["improvement_candidate"] = checkpoint["improvement_candidate"]
    snapshot["pending_close_worker_attention"] = checkpoint["pending_close_worker_attention"]
    snapshot["active_subagents"] = checkpoint["active_subagents"]
    snapshot["active_subagents_summary"] = checkpoint["active_subagents_summary"]
    snapshot["host_session"] = checkpoint["host_session"]
    snapshot["host_wait"] = checkpoint["host_wait"]
    snapshot["intent_binding"] = checkpoint["intent_binding"]
    checkpoint["compaction_event"] = build_compaction_event_summary(paths)
    snapshot["compaction_event"] = checkpoint["compaction_event"]
    snapshot["compaction_event_path"] = str(paths.compaction_event_path)
    snapshot["resume_anchor_path"] = str(paths.resume_anchor_path)
    resume_anchor = build_resume_anchor(paths, checkpoint)
    context_bundle = (
        load_json(paths.context_bundle_path) if paths.context_bundle_path.exists() else None
    )
    context_budget = build_task_context_budget(
        paths,
        packet=packet,
        context_bundle=context_bundle,
        checkpoint=checkpoint,
        resume_anchor=resume_anchor,
    )
    snapshot["context_budget"] = context_budget
    checkpoint["context_budget"] = context_budget
    resume_anchor["context_budget"] = build_compact_context_budget_summary(
        context_budget
    )
    write_json(paths.status_path, snapshot)
    write_json(paths.checkpoint_path, checkpoint)
    write_json(paths.resume_anchor_path, resume_anchor)
    return snapshot


def build_checkpoint(
    paths: TaskPaths,
    snapshot: dict[str, Any],
    packet: Any,
    report: Any,
    events: list[dict[str, Any]],
    latest_event: dict[str, Any] | None,
    lifecycle: dict[str, Any],
    worker_binding: dict[str, Any],
) -> dict[str, Any]:
    worker_status = snapshot.get("worker_status")
    needs_commander_decision = bool(snapshot.get("needs_commander_decision"))
    needs_user_decision = bool(snapshot.get("needs_user_decision"))
    ready_for_user_delivery = bool(snapshot.get("ready_for_user_delivery"))
    result_governance = snapshot.get("result_governance", {})
    decision_gates = snapshot.get("decision_gates", {})
    lifecycle_summary = build_lifecycle_summary(lifecycle)
    catalog_refresh = build_catalog_refresh_summary(paths)
    host_session_summary = build_task_host_session_summary(
        paths.runtime_root, paths.task_id
    )
    host_wait_summary = build_task_host_wait_summary(paths.runtime_root, paths.task_id)
    intent_binding = build_intent_binding_state(
        existing=snapshot.get("intent_binding")
    )
    current_phase, recommended_action = derive_closed_loop_phase(
        lifecycle_status=lifecycle_summary["lifecycle_status"],
        cleanup_eligible=lifecycle_summary["cleanup_eligible"],
        packet=packet,
        worker_status=worker_status,
        needs_commander_decision=needs_commander_decision,
        needs_user_decision=needs_user_decision,
        ready_for_user_delivery=ready_for_user_delivery,
        result_governance=result_governance,
        decision_gates=decision_gates,
    )

    recent_trusted_completion: dict[str, Any] | None = None
    blockers: list[str] = []
    pending_decisions: list[str] = []
    active_subagents = load_active_subagents(paths)
    active_subagent_summary = build_active_subagent_summary(active_subagents)
    recent_trusted_completion = build_recent_trusted_completion(paths, report)
    improvement_candidate = build_improvement_candidate_anchor(paths, load_improvement_candidate(paths))
    if isinstance(report, dict):
        if worker_status in {"blocked", "need_split"}:
            blockers = [item for item in report.get("risks", []) if isinstance(item, str)]
        if needs_user_decision:
            next_step = result_governance.get("decision_reason") or report.get("user_decision_reason")
            if isinstance(next_step, str) and next_step:
                pending_decisions.append(next_step)
            else:
                pending_decisions.append("Ask the user for the missing decision before continuing")
        elif worker_status in {"blocked", "need_split"} or decision_gates.get("commander_required"):
            next_step = result_governance.get("decision_reason") or report.get("recommended_next_step")
            if isinstance(next_step, str) and next_step:
                pending_decisions.append(next_step)
            elif needs_commander_decision:
                pending_decisions.append("Review the report and decide the next commander action")
        split_suggestion = result_governance.get("split_suggestion")
        if isinstance(split_suggestion, dict):
            pending_decisions.append(str(split_suggestion.get("reason") or split_suggestion.get("goal") or "Review split suggestion"))
    else:
        split_suggestion = None

    if active_subagent_summary["has_open_subagents"]:
        recommended_action = ACTIVE_SUBAGENT_WARNING_ACTION

    next_minimal_action = pending_decisions[0] if pending_decisions else recommended_action
    if current_phase == "archived":
        if lifecycle_summary["cleanup_eligible"]:
            next_minimal_action = "Run runtime cleanup for archived commander tasks"
        else:
            next_minimal_action = "Retain the archived task until the cleanup window opens"
    if current_phase == "closed":
        next_minimal_action = "Archive the task into runtime history"
    if current_phase == "stale":
        next_minimal_action = "Reconcile the stale task before continuing new work"
    if current_phase == "canceled":
        next_minimal_action = "Review the canceled task and decide whether to reopen it"
    if current_phase == "pending_user":
        next_minimal_action = pending_decisions[0] if pending_decisions else "Ask the user for the missing decision"
    if current_phase == "ready_for_user_delivery":
        next_minimal_action = "Return the final result to the user"
    if current_phase == "ready_to_close" and not pending_decisions:
        next_minimal_action = "Review the report and close the task"
    if current_phase == "needs_commander_decision" and recommended_action == "review_split_suggestion":
        next_minimal_action = pending_decisions[0] if pending_decisions else "Review the split suggestion and decide whether to dispatch follow-up work"
    if current_phase == "awaiting_report":
        next_minimal_action = (
            host_wait_summary.get("next_action")
            if isinstance(host_wait_summary, dict)
            and isinstance(host_wait_summary.get("next_action"), str)
            and host_wait_summary.get("next_action")
            else "Wait for the worker report"
        )
    if current_phase == "missing_packet":
        next_minimal_action = "Recreate the dispatch packet"
    if worker_binding.get("binding_health") == "lease_expired":
        next_minimal_action = "Reconcile expired worker lease before continuing"
    if worker_binding.get("binding_health") == "multiple_leased_workers":
        next_minimal_action = "Reconcile duplicate worker bindings before continuing"
    if catalog_refresh.get("status") == CATALOG_REFRESH_STATUS_FAILED:
        next_minimal_action = "Inspect catalog refresh failure before trusting catalog views"
    active_subagent_blocker = describe_active_subagent_blocker(active_subagent_summary)
    if active_subagent_blocker is not None:
        next_minimal_action = active_subagent_blocker["next_action"]

    if current_phase == "pending_user":
        controller_handoff = CONTROLLER_HANDOFF_REQUEST_USER_DECISION
        conversation_stop_required = True
        conversation_stop_reason = "explicit_user_decision_required"
    elif current_phase == "ready_for_user_delivery":
        controller_handoff = CONTROLLER_HANDOFF_RETURN_FINAL_RESULT
        conversation_stop_required = True
        conversation_stop_reason = "deliverable_ready_for_user"
    elif current_phase == "awaiting_report":
        controller_handoff = CONTROLLER_HANDOFF_WAIT_EXTERNAL_RESULT
        conversation_stop_required = False
        conversation_stop_reason = None
    else:
        controller_handoff = CONTROLLER_HANDOFF_CONTINUE
        conversation_stop_required = False
        conversation_stop_reason = None

    pending_close_worker_attention = build_pending_close_worker_attention(
        controller_handoff=controller_handoff,
        next_minimal_action=next_minimal_action,
        recent_trusted_completion=recent_trusted_completion,
        improvement_candidate=improvement_candidate,
        catalog_refresh=catalog_refresh,
        worker_binding=worker_binding,
        active_subagent_summary=active_subagent_summary,
        decision_gates=decision_gates,
        split_suggestion=split_suggestion,
    )

    return {
        "schema_version": "commander-harness-v1",
        "task_id": paths.task_id,
        "title": snapshot.get("title"),
        "current_phase": current_phase,
        "recommended_action": recommended_action,
        "lifecycle_status": lifecycle_summary["lifecycle_status"],
        "cleanup_eligible": lifecycle_summary["cleanup_eligible"],
        "closed_at": lifecycle_summary["closed_at"],
        "closed_reason": lifecycle_summary["closed_reason"],
        "archived_at": lifecycle_summary["archived_at"],
        "archive_reason": lifecycle_summary["archive_reason"],
        "stale_at": lifecycle_summary["stale_at"],
        "stale_reason": lifecycle_summary["stale_reason"],
        "canceled_at": lifecycle_summary["canceled_at"],
        "cancel_reason": lifecycle_summary["cancel_reason"],
        "last_reconciled_at": lifecycle_summary["last_reconciled_at"],
        "lifecycle": lifecycle_summary,
        "catalog_refresh": catalog_refresh,
        "worker_binding": worker_binding,
        "host_session": host_session_summary,
        "host_wait": host_wait_summary,
        "intent_binding": intent_binding,
        "last_open_offer": intent_binding.get("last_open_offer"),
        "pending_user_reply_target": intent_binding.get(
            "pending_user_reply_target"
        ),
        "offer_confirmed": bool(intent_binding.get("offer_confirmed")),
        "latest_user_reply_text": intent_binding.get("latest_user_reply_text"),
        "latest_user_reply_kind": intent_binding.get("latest_user_reply_kind"),
        "resolved_reply_target": intent_binding.get("resolved_reply_target"),
        "binding_reason": intent_binding.get("binding_reason"),
        "recent_trusted_completion": recent_trusted_completion,
        "next_minimal_action": next_minimal_action,
        "worker_profile": snapshot.get("worker_profile"),
        "preferred_worker_profile": snapshot.get("preferred_worker_profile"),
        "reuse_allowed": snapshot.get("reuse_allowed"),
        "tool_profile": snapshot.get("tool_profile"),
        "allowed_tools": snapshot.get("allowed_tools"),
        "dispatch_kind": snapshot.get("dispatch_kind"),
        "source_task_id": snapshot.get("source_task_id"),
        "parent_task_id": snapshot.get("parent_task_id"),
        "task_owner": snapshot.get("task_owner"),
        "closure_policy": snapshot.get("closure_policy"),
        "dispatch_governance": snapshot.get("dispatch_governance"),
        "result_grade": snapshot.get("result_grade"),
        "next_action_owner": snapshot.get("next_action_owner"),
        "continuation_mode": snapshot.get("continuation_mode"),
        "decision_reason": snapshot.get("decision_reason"),
        "split_suggestion": snapshot.get("split_suggestion"),
        "result_governance": result_governance,
        "decision_gates": decision_gates,
        "controller_handoff": controller_handoff,
        "conversation_stop_required": conversation_stop_required,
        "conversation_stop_reason": conversation_stop_reason,
        "blockers": blockers,
        "pending_decisions": pending_decisions,
        "improvement_candidate_path": str(paths.improvement_candidate_path),
        "improvement_candidate": improvement_candidate,
        "pending_close_worker_attention": pending_close_worker_attention,
        "active_subagents": active_subagents,
        "active_subagents_summary": active_subagent_summary,
        "key_paths": {
            "packet": str(paths.packet_path),
            "context_bundle": str(paths.context_bundle_path),
            "worker_brief": str(paths.worker_brief_path),
            "worker_report": str(paths.worker_report_path),
            "report": str(paths.report_path),
            "anchor": str(paths.resume_anchor_path),
            "compaction_event": str(paths.compaction_event_path),
            "compactions_dir": str(paths.compactions_dir),
            "improvement_candidate": str(paths.improvement_candidate_path),
            "catalog_refresh": str(paths.catalog_refresh_path),
            "lifecycle": str(paths.lifecycle_path),
            "checkpoint": str(paths.checkpoint_path),
            "status": str(paths.status_path),
            "events": str(paths.events_path),
            "reports_dir": str(paths.reports_dir),
        },
        "event_count": len(events),
        "worker_status": snapshot.get("worker_status"),
        "commander_recommendation": snapshot.get("commander_recommendation"),
        "needs_commander_decision": needs_commander_decision,
        "needs_user_decision": needs_user_decision,
        "ready_for_user_delivery": ready_for_user_delivery,
        "last_event_type": snapshot.get("last_event_type"),
        "last_event_at": snapshot.get("last_event_at"),
        "updated_at": snapshot.get("updated_at"),
    }


def build_worker_brief(
    packet: dict[str, Any],
    *,
    context_bundle_path: Path | None = None,
    context_bundle: dict[str, Any] | None = None,
    resume_anchor_path: Path | None = None,
    checkpoint_path: Path | None = None,
) -> str:
    dispatch_governance = build_dispatch_governance(packet)
    sections = [
        "# Commander Task Brief",
        "",
        f"- Task ID: {packet['task_id']}",
        f"- Title: {packet['title']}",
        f"- Goal: {packet['goal']}",
        f"- Status: {packet['status']}",
        "",
        "## Must Read",
    ]
    sections.extend(_render_bullets(packet["must_read"]))
    sections.extend(["", "## Bounds"])
    sections.extend(_render_bullets(packet["bounds"]))
    sections.extend(["", "## Validation"])
    sections.extend(_render_bullets(packet["validation"]))
    sections.extend(["", "## Forbidden Paths"])
    sections.extend(_render_bullets(packet["forbidden_paths"]))
    spec_refs = packet.get("spec_refs")
    if isinstance(spec_refs, list) and spec_refs:
        sections.extend(["", "## Spec References"])
        sections.extend(_render_spec_refs(spec_refs))
    sections.extend(["", "## Worker Execution"])
    sections.append(f"- Worker profile: {packet['worker_profile']}")
    sections.append(f"- Preferred warm worker profile: {packet.get('preferred_worker_profile') or '(none)'}")
    sections.append(f"- Reuse allowed: {packet['reuse_allowed']}")
    sections.extend(["", "## Tool Boundary"])
    sections.append(f"- Tool profile: {packet['tool_profile']}")
    sections.append("- Allowed tools:")
    sections.extend(_render_bullets(packet["allowed_tools"]))
    sections.extend(["", "## Dispatch Governance"])
    sections.append(f"- Dispatch kind: {dispatch_governance['dispatch_kind']}")
    sections.append(f"- Source task ID: {dispatch_governance['source_task_id'] or '(none)'}")
    sections.append(f"- Parent task ID: {dispatch_governance['parent_task_id'] or '(none)'}")
    sections.append(f"- Task owner: {dispatch_governance['task_owner']}")
    sections.append(f"- Closure policy: {dispatch_governance['closure_policy']}")
    if context_bundle_path is not None:
        sections.extend(["", "## Context Route"])
        sections.append(f"- Context bundle: {context_bundle_path}")
        sections.append("- Read this routed bundle after packet.json instead of scanning the whole repo.")
        if isinstance(context_bundle, dict):
            read_policy = (
                context_bundle.get("read_policy")
                if isinstance(context_bundle.get("read_policy"), dict)
                else {}
            )
            if read_policy:
                sections.append(
                    f"- Read policy: {read_policy.get('mode', 'progressive_disclosure')}"
                )
                default_behavior = str(read_policy.get("default_behavior") or "").strip()
                if default_behavior:
                    sections.append(f"- Default behavior: {default_behavior}")
                round_budget_tokens = read_policy.get("round_budget_tokens")
                router_open_now_estimated_tokens = read_policy.get(
                    "router_open_now_estimated_tokens"
                )
                router_deferred_estimated_tokens = read_policy.get(
                    "router_deferred_estimated_tokens"
                )
                if isinstance(round_budget_tokens, int):
                    sections.append(f"- Router round budget: {round_budget_tokens} tokens")
                if isinstance(router_open_now_estimated_tokens, int):
                    sections.append(
                        f"- Router open-now estimate: {router_open_now_estimated_tokens} tokens"
                    )
                if isinstance(router_deferred_estimated_tokens, int):
                    sections.append(
                        f"- Router deferred estimate: {router_deferred_estimated_tokens} tokens"
                    )
                deferred_by_budget = read_policy.get("deferred_by_budget_context_ids")
                if isinstance(deferred_by_budget, list) and deferred_by_budget:
                    sections.append(
                        "- Deferred by budget: "
                        + ", ".join(
                            str(item)
                            for item in deferred_by_budget
                            if isinstance(item, str) and item.strip()
                        )
                    )
            selected_tags = context_bundle.get("selected_tags")
            if isinstance(selected_tags, list) and selected_tags:
                sections.append(
                    f"- Selected tags: {', '.join(str(item) for item in selected_tags)}"
                )
            entries = context_bundle.get("entries")
            if isinstance(entries, list) and entries:
                sections.append("- Routed entries:")
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    context_id = str(entry.get("context_id") or "unknown")
                    title = str(entry.get("title") or context_id)
                    disclosure_mode = str(
                        entry.get("disclosure_mode") or "metadata_first"
                    )
                    sections.append(
                        f"- {context_id}: {title} [{disclosure_mode}]"
                    )
                    priority = str(entry.get("priority") or "").strip()
                    if priority:
                        sections.append(f"  priority: {priority}")
                    budget_action = str(entry.get("budget_action") or "").strip()
                    if budget_action:
                        sections.append(f"  budget: {budget_action}")
                    budget_reason = str(entry.get("budget_reason") or "").strip()
                    if budget_reason:
                        sections.append(f"  budget reason: {budget_reason}")
                    summary_lines = entry.get("summary_lines")
                    if isinstance(summary_lines, list):
                        for item in summary_lines:
                            if isinstance(item, str) and item.strip():
                                sections.append(f"  summary: {item.strip()}")
                    paths = entry.get("paths")
                    if isinstance(paths, list) and paths:
                        sections.append(
                            f"  open now: {', '.join(str(item) for item in paths if isinstance(item, str) and item.strip())}"
                        )
                    deferred_paths = entry.get("deferred_paths")
                    if isinstance(deferred_paths, list) and deferred_paths:
                        sections.append(
                            "  defer until needed: "
                            + ", ".join(
                                str(item)
                                for item in deferred_paths
                                if isinstance(item, str) and item.strip()
                            )
                        )
                    when_to_open = entry.get("when_to_open")
                    if isinstance(when_to_open, list):
                        for item in when_to_open:
                            if isinstance(item, str) and item.strip():
                                sections.append(f"  trigger: {item.strip()}")
    if packet.get("notes"):
        sections.extend(["", "## Notes"])
        sections.extend(_render_bullets(packet["notes"]))
    if resume_anchor_path is not None:
        sections.extend(
            [
                "",
                "## Compact Resume Anchor",
                f"- Recovery anchor: {resume_anchor_path}",
                "- Read this file first after context compression or interruption.",
                "- Use `commander_resume.py --compact --task-id <task_id>` to load the same compact anchor.",
                "- Open checkpoint.json only if you need deeper state detail.",
            ]
        )
    if checkpoint_path is not None:
        sections.extend(
            [
                "",
                "## Checkpoint / Resume",
                f"- Recovery anchor: {checkpoint_path}",
                "- Use this checkpoint.json path only when the compact anchor is insufficient.",
            ]
        )
    sections.extend(
        [
            "",
            "## Report Contract",
            f"- Allowed statuses: {', '.join(packet['report_contract']['allowed_statuses'])}",
            "- Required fields:",
        ]
    )
    sections.extend(_render_bullets(packet["report_contract"]["required_fields"]))
    return "\n".join(sections) + "\n"


def build_worker_report_draft(task_id: str) -> dict[str, Any]:
    return {
        "schema_version": "commander-harness-v1",
        "task_id": task_id,
        "status": "blocked",
        "summary": (
            "待执行窗口填写：本文件由 harness 预生成，请在完成任务后补充真实结果，并将 "
            "harness_metadata.is_dispatch_draft 设为 false 或按约定删除该 metadata。"
        ),
        "changed_files": [],
        "verification": [
            {
                "name": "待执行窗口填写并清理 draft metadata",
                "result": "skipped",
                "details": "请替换为本轮实际执行的验证记录，并将 harness_metadata.is_dispatch_draft 设为 false 或按约定删除。",
            }
        ],
        "commit": {
            "message": "未提交：待执行窗口填写本轮实际提交情况，并清理 draft metadata。",
        },
        "risks": [
            "待执行窗口填写：如不将 harness_metadata.is_dispatch_draft 设为 false 或删除该 metadata 就直接 ingest，会把草稿状态当成真实结果。"
        ],
        "recommended_next_step": "待执行窗口填写：补充本轮真实结果，确认 harness_metadata.is_dispatch_draft 已清理后再交由指挥官 ingest。",
        "needs_commander_decision": True,
        "needs_user_decision": False,
        "user_decision_reason": None,
        "ready_for_user_delivery": False,
        "result_grade": RESULT_GRADE_PARTIAL,
        "next_action_owner": NEXT_ACTION_OWNER_COMMANDER,
        "continuation_mode": CONTINUATION_MODE_FOLLOWUP,
        "decision_reason": "Replace this draft with the real worker outcome before ingest.",
        "split_suggestion": None,
        "harness_metadata": {
            "is_dispatch_draft": True,
        },
    }


def find_report_draft_markers(payload: Any, *, path: str = "$") -> list[str]:
    matches: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            matches.extend(find_report_draft_markers(value, path=f"{path}.{key}"))
        return matches
    if isinstance(payload, list):
        for index, value in enumerate(payload):
            matches.extend(find_report_draft_markers(value, path=f"{path}[{index}]"))
        return matches
    if isinstance(payload, str) and any(marker in payload for marker in REPORT_DRAFT_MARKERS):
        matches.append(path)
    return matches


def is_dispatch_draft_report(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    metadata = payload.get(REPORT_DRAFT_METADATA_FIELD)
    if not isinstance(metadata, dict):
        return False
    return bool(metadata.get(REPORT_DRAFT_METADATA_FLAG))


def _render_bullets(items: list[str]) -> list[str]:
    if not items:
        return ["- (none)"]
    return [f"- {item}" for item in items]


def _render_spec_refs(items: list[Any]) -> list[str]:
    if not items:
        return ["- (none)"]
    lines: list[str] = []
    for item in items:
        if isinstance(item, dict):
            spec_id = str(item.get("spec_id") or "unknown").strip() or "unknown"
            path = str(item.get("path") or "").strip() or "(missing path)"
            details: list[str] = []
            for key in ("title", "section", "role", "reason", "status"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    details.append(f"{key}={value.strip()}")
            suffix = f" ({'; '.join(details)})" if details else ""
            lines.append(f"- {spec_id}: {path}{suffix}")
            continue
        lines.append(f"- {item}")
    return lines


def _matches_declared_type(instance: Any, declared_type: str | list[str]) -> bool:
    declared_types = declared_type if isinstance(declared_type, list) else [declared_type]
    return any(_matches_single_type(instance, item) for item in declared_types)


def _matches_single_type(instance: Any, declared_type: str) -> bool:
    if declared_type == "object":
        return isinstance(instance, dict)
    if declared_type == "array":
        return isinstance(instance, list)
    if declared_type == "string":
        return isinstance(instance, str)
    if declared_type == "boolean":
        return isinstance(instance, bool)
    if declared_type == "integer":
        return isinstance(instance, int) and not isinstance(instance, bool)
    if declared_type == "number":
        return isinstance(instance, (int, float)) and not isinstance(instance, bool)
    if declared_type == "null":
        return instance is None
    return True


def _describe_declared_type(declared_type: str | list[str]) -> str:
    if isinstance(declared_type, list):
        return " or ".join(declared_type)
    return declared_type
