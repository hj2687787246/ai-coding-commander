"""Synchronize `.codex/docs/当前任务.md` during long-running work."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path


FIELD_PREFIXES = {
    "progress": "当前进度：",
    "blocker": "当前卡点：",
    "focus_files": "正在关注的文件：",
    "validation_status": "验证状态：",
    "validation_evidence": "验证证据：",
    "next_step": "下一步：",
    "last_validation": "最近验证：",
}

FIELD_LABELS = {
    "progress": "当前进度",
    "blocker": "当前卡点",
    "focus_files": "正在关注的文件",
    "validation_status": "验证状态",
    "validation_evidence": "验证证据",
    "next_step": "下一步",
    "last_validation": "最近验证",
}

VALID_EVENTS = {"start", "phase", "validate", "preclose", "checkpoint"}

DEFAULT_TASK_LINES = [
    "# 当前任务",
    "",
    "- 当前任务名称：{task_name}",
    "- 当前任务目标：待补充",
    "- 当前任务模式：待确认",
    "- 当前任务形状：待确认",
    "- 执行强度：待确认",
    "- 当前进度：未开始",
    "- 当前卡点：无",
    "- 正在关注的文件：无",
    "- 验证状态：未验证",
    "- 验证证据：无",
    "- 下一步：确认当前任务模式",
    "- 最近验证：无",
]


@dataclass(frozen=True)
class SyncResult:
    updated: bool
    target: str
    changed_fields: list[str]


def slug_task_id(task_id: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", task_id.strip()).strip(".-_")
    if not slug:
        raise ValueError("task_id must contain at least one letter, digit, dot, underscore, or hyphen")
    return slug


def resolve_current_task(repo_root: Path, task_id: str | None = None) -> Path:
    repo_root = repo_root.resolve()
    if task_id is None:
        return repo_root / ".codex" / "docs" / "当前任务.md"
    return repo_root / ".codex" / "tasks" / slug_task_id(task_id) / "当前任务.md"


def ensure_isolated_task(target: Path, task_id: str | None) -> None:
    if task_id is None or target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    task_name = slug_task_id(task_id)
    lines = [line.format(task_name=task_name) for line in DEFAULT_TASK_LINES]
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


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
    task_id: str | None = None,
    progress: str | None = None,
    blocker: str | None = None,
    focus_files: str | None = None,
    validation_status: str | None = None,
    validation_evidence: str | None = None,
    next_step: str | None = None,
    last_validation: str | None = None,
) -> SyncResult:
    if event not in VALID_EVENTS:
        raise ValueError(f"Unsupported event: {event}")

    target = resolve_current_task(repo_root, task_id=task_id)
    ensure_isolated_task(target, task_id)
    lines = read_current_task(target)
    changed_fields: list[str] = []

    updates = {
        "progress": progress,
        "blocker": blocker,
        "focus_files": focus_files,
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
    parser.add_argument("--task-id", help="Write .codex/tasks/<task-id>/当前任务.md for parallel windows.")
    parser.add_argument("--progress")
    parser.add_argument("--blocker")
    parser.add_argument("--focus-files")
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
            task_id=args.task_id,
            progress=args.progress,
            blocker=args.blocker,
            focus_files=args.focus_files,
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
