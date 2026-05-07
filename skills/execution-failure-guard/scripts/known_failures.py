"""Manage known execution failures and learned working replacements."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


REGISTRY_RELATIVE_PATH = Path(".codex") / "known-failures.json"
VALID_MATCH_TYPES = {"exact", "substring", "regex"}


@dataclass(frozen=True)
class MatchResult:
    matched: bool
    registry: str
    record: dict[str, Any] | None = None


def registry_path(repo_root: Path) -> Path:
    return repo_root.resolve() / REGISTRY_RELATIVE_PATH


def empty_registry() -> dict[str, Any]:
    return {"version": 1, "records": []}


def load_registry(repo_root: Path) -> dict[str, Any]:
    target = registry_path(repo_root)
    if not target.exists():
        return empty_registry()
    data = json.loads(target.read_text(encoding="utf-8"))
    if data.get("version") != 1 or not isinstance(data.get("records"), list):
        raise ValueError(f"Unsupported known-failures registry format: {target}")
    return data


def save_registry(repo_root: Path, registry: dict[str, Any]) -> Path:
    target = registry_path(repo_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def is_expired(record: dict[str, Any], today: date | None = None) -> bool:
    expires_at = record.get("expires_at")
    if not expires_at:
        return False
    current_date = today or date.today()
    return date.fromisoformat(expires_at) < current_date


def record_matches(record: dict[str, Any], command: str) -> bool:
    match = record.get("match")
    match_type = record.get("match_type", "substring")
    if not isinstance(match, str) or match_type not in VALID_MATCH_TYPES:
        return False
    if match_type == "exact":
        return command == match
    if match_type == "regex":
        return re.search(match, command) is not None
    return match in command


def check_command(repo_root: Path, command: str, include_expired: bool = False) -> MatchResult:
    registry = load_registry(repo_root)
    target = registry_path(repo_root)
    for record in registry["records"]:
        if not include_expired and is_expired(record):
            continue
        if record_matches(record, command):
            return MatchResult(matched=True, registry=str(target), record=record)
    return MatchResult(matched=False, registry=str(target), record=None)


def add_record(
    repo_root: Path,
    record_id: str,
    match: str,
    known_bad: str,
    fails_because: str,
    use_instead: str,
    scope: str,
    match_type: str = "substring",
    last_verified: str | None = None,
    expires_at: str | None = None,
) -> dict[str, Any]:
    if match_type not in VALID_MATCH_TYPES:
        raise ValueError(f"Unsupported match type: {match_type}")

    registry = load_registry(repo_root)
    record = {
        "id": record_id,
        "match": match,
        "match_type": match_type,
        "known_bad": known_bad,
        "fails_because": fails_because,
        "use_instead": use_instead,
        "scope": scope,
    }
    if last_verified:
        record["last_verified"] = last_verified
    if expires_at:
        date.fromisoformat(expires_at)
        record["expires_at"] = expires_at

    registry["records"] = [existing for existing in registry["records"] if existing.get("id") != record_id]
    registry["records"].append(record)
    save_registry(repo_root, registry)
    return record


def emit_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage known execution failures.")
    parser.add_argument("--repo", default=".", help="Repository root.")
    subparsers = parser.add_subparsers(dest="command_name", required=True)

    subparsers.add_parser("init", help="Create an empty known-failures registry.")

    add_parser = subparsers.add_parser("add", help="Add or replace a known failure record.")
    add_parser.add_argument("--id", required=True)
    add_parser.add_argument("--match", required=True)
    add_parser.add_argument("--match-type", default="substring", choices=sorted(VALID_MATCH_TYPES))
    add_parser.add_argument("--known-bad", required=True)
    add_parser.add_argument("--fails-because", required=True)
    add_parser.add_argument("--use-instead", required=True)
    add_parser.add_argument("--scope", required=True)
    add_parser.add_argument("--last-verified")
    add_parser.add_argument("--expires-at")

    check_parser = subparsers.add_parser("check", help="Check a command against known failures.")
    check_parser.add_argument("--command", required=True)
    check_parser.add_argument("--include-expired", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    parser = build_parser()
    args = parser.parse_args(argv)
    repo_root = Path(args.repo)

    try:
        if args.command_name == "init":
            target = save_registry(repo_root, empty_registry())
            emit_json({"ok": True, "registry": str(target), "records": 0})
            return 0
        if args.command_name == "add":
            record = add_record(
                repo_root=repo_root,
                record_id=args.id,
                match=args.match,
                match_type=args.match_type,
                known_bad=args.known_bad,
                fails_because=args.fails_because,
                use_instead=args.use_instead,
                scope=args.scope,
                last_verified=args.last_verified,
                expires_at=args.expires_at,
            )
            emit_json({"ok": True, "registry": str(registry_path(repo_root)), "record": record})
            return 0
        if args.command_name == "check":
            result = check_command(repo_root, args.command, include_expired=args.include_expired)
            payload: dict[str, Any] = {"matched": result.matched, "registry": result.registry}
            if result.record is not None:
                payload["record"] = result.record
                payload["use_instead"] = result.record.get("use_instead")
            emit_json(payload)
            return 0
    except (ValueError, json.JSONDecodeError) as exc:
        emit_json({"ok": False, "error": str(exc)})
        return 1

    parser.error("unreachable command")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
