"""Synchronize `.codex/docs/当前任务.md` during long-running work."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path


FIELD_PREFIXES = {
    "progress": "当前进度：",
    "blocker": "当前卡点：",
    "validation_status": "验证状态：",
    "validation_evidence": "验证证据：",
    "next_step": "下一步：",
    "last_validation": "最近验证：",
}

FIELD_LABELS = {
    "progress": "当前进度",
    "blocker": "当前卡点",
    "validation_status": "验证状态",
    "validation_evidence": "验证证据",
    "next_step": "下一步",
    "last_validation": "最近验证",
}

VALID_EVENTS = {"start", "phase", "validate", "preclose"}


@dataclass(frozen=True)
class SyncResult:
    updated: bool
    target: str
    changed_fields: list[str]


def resolve_current_task(repo_root: Path) -> Path:
    return repo_root.resolve() / ".codex" / "docs" / "当前任务.md"


def read_current_task(target: Path) -> list[str]:
    if not target.exists():
        raise FileNotFoundError(f"Current task file not found: {target}")
    return target.read_text(encoding="utf-8").splitlines()


def replace_prefixed_line(lines: list[str], prefix: str, value: str) -> bool:
    replacement = f"- {prefix}{value}"
    for index, line in enumerate(lines):
        if line.startswith(f"- {prefix}") or line.startswith(prefix):
            lines[index] = replacement
            return True
    return False


def sync_current_task(
    repo_root: Path,
    event: str,
    progress: str | None = None,
    blocker: str | None = None,
    validation_status: str | None = None,
    validation_evidence: str | None = None,
    next_step: str | None = None,
    last_validation: str | None = None,
) -> SyncResult:
    if event not in VALID_EVENTS:
        raise ValueError(f"Unsupported event: {event}")

    target = resolve_current_task(repo_root)
    lines = read_current_task(target)
    changed_fields: list[str] = []

    updates = {
        "progress": progress,
        "blocker": blocker,
        "validation_status": validation_status,
        "validation_evidence": validation_evidence,
        "next_step": next_step,
        "last_validation": last_validation,
    }

    for key, value in updates.items():
        if value is None:
            continue
        prefix = FIELD_PREFIXES[key]
        if replace_prefixed_line(lines, prefix, value):
            changed_fields.append(FIELD_LABELS[key])

    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return SyncResult(updated=bool(changed_fields), target=str(target), changed_fields=changed_fields)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sync .codex/docs/当前任务.md for long-running work.")
    parser.add_argument("--repo", default=".", help="Repository root.")
    parser.add_argument("--event", required=True, choices=sorted(VALID_EVENTS))
    parser.add_argument("--progress")
    parser.add_argument("--blocker")
    parser.add_argument("--validation-status")
    parser.add_argument("--validation-evidence")
    parser.add_argument("--next-step")
    parser.add_argument("--last-validation")
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        result = sync_current_task(
            repo_root=Path(args.repo),
            event=args.event,
            progress=args.progress,
            blocker=args.blocker,
            validation_status=args.validation_status,
            validation_evidence=args.validation_evidence,
            next_step=args.next_step,
            last_validation=args.last_validation,
        )
    except FileNotFoundError as exc:
        print(json.dumps({"updated": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    print(
        json.dumps(
            {
                "updated": result.updated,
                "target": result.target,
                "changed_fields": result.changed_fields,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
