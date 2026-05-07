"""Manage the project-local commander activation marker."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import sys
from pathlib import Path
from typing import Any


MARKER_RELATIVE_PATH = Path(".codex") / "commander-active.json"


def marker_path(repo_root: Path) -> Path:
    """Return the normalized commander activation marker path for a repo."""
    return repo_root.resolve() / MARKER_RELATIVE_PATH


def now_iso() -> str:
    """Return a stable UTC timestamp for portable JSON state."""
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def read_marker(repo_root: Path) -> dict[str, Any]:
    marker = marker_path(repo_root)
    if not marker.exists():
        return {}
    return json.loads(marker.read_text(encoding="utf-8"))


def write_marker(repo_root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    marker = marker_path(repo_root)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return status(repo_root)


def status(repo_root: Path) -> dict[str, Any]:
    marker = marker_path(repo_root)
    payload = read_marker(repo_root)
    return {
        "active": bool(payload.get("active")),
        "marker_exists": marker.exists(),
        "marker_path": marker.as_posix(),
        "payload": payload,
    }


def activate(repo_root: Path, source: str = "commander-mode", note: str = "") -> dict[str, Any]:
    existing = read_marker(repo_root)
    payload: dict[str, Any] = {
        **existing,
        "schema_version": 1,
        "active": True,
        "scope": "repo",
        "activated_at": existing.get("activated_at") or now_iso(),
        "activated_by": source,
        "last_verified_at": now_iso(),
    }
    payload.pop("deactivated_at", None)
    payload.pop("deactivated_by", None)
    payload.pop("deactivation_note", None)
    if note:
        payload["activation_note"] = note
    return write_marker(repo_root, payload)


def deactivate(repo_root: Path, source: str = "commander-mode", note: str = "") -> dict[str, Any]:
    existing = read_marker(repo_root)
    payload: dict[str, Any] = {
        **existing,
        "schema_version": existing.get("schema_version", 1),
        "active": False,
        "scope": existing.get("scope", "repo"),
        "deactivated_at": now_iso(),
        "deactivated_by": source,
    }
    if note:
        payload["deactivation_note"] = note
    return write_marker(repo_root, payload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage project-local commander activation state.")
    parser.add_argument("--repo", default=".", help="Repository root.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    activate_parser = subparsers.add_parser("activate", help="Enable commander recovery for this repo.")
    activate_parser.add_argument("--source", default="commander-mode", help="Activation source label.")
    activate_parser.add_argument("--note", default="", help="Optional activation note.")

    status_parser = subparsers.add_parser("status", help="Read commander recovery status.")
    status_parser.set_defaults(source="", note="")

    deactivate_parser = subparsers.add_parser("deactivate", help="Disable commander recovery for this repo.")
    deactivate_parser.add_argument("--source", default="commander-mode", help="Deactivation source label.")
    deactivate_parser.add_argument("--note", default="", help="Optional deactivation note.")
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    args = build_parser().parse_args(argv)
    repo_root = Path(args.repo)
    if args.command == "activate":
        result = activate(repo_root, source=args.source, note=args.note)
    elif args.command == "deactivate":
        result = deactivate(repo_root, source=args.source, note=args.note)
    else:
        result = status(repo_root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
