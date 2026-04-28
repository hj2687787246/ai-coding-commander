"""Synchronize structured preference memory cards in `.codex/docs/协作偏好.md`."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path


VALID_STATUSES = {"stable", "candidate"}
SECTION_BY_STATUS = {
    "stable": "Stable Preferences",
    "candidate": "Candidate Preferences",
}

DEFAULT_DOCUMENT = """# 协作偏好

## 使用方式

- 只记录长期稳定、会影响未来行为的协作偏好。
- 不记录一次性的聊天偏好、临时任务范围或聊天原文。

## Stable Preferences

## Candidate Preferences
"""


@dataclass(frozen=True)
class PreferenceSyncResult:
    updated: bool
    target: str
    memory_id: str
    status: str
    section: str
    action: str


def resolve_preference_file(repo_root: Path) -> Path:
    return repo_root.resolve() / ".codex" / "docs" / "协作偏好.md"


def read_or_create_document(target: Path) -> str:
    if not target.exists():
        return DEFAULT_DOCUMENT
    return target.read_text(encoding="utf-8")


def ensure_section(text: str, section: str) -> str:
    heading = f"## {section}"
    if heading in text:
        return text
    stripped = text.rstrip()
    return f"{stripped}\n\n{heading}\n"


def ensure_sections(text: str) -> str:
    for section in SECTION_BY_STATUS.values():
        text = ensure_section(text, section)
    return text


def yaml_list(items: list[str]) -> list[str]:
    values = items or ["无"]
    return [f"  - {item}" for item in values]


def build_card(
    *,
    memory_id: str,
    status: str,
    scope: str,
    triggers: list[str],
    rule: str,
    do_items: list[str],
    dont_items: list[str],
    evidence_items: list[str],
) -> str:
    lines = [
        f"### {memory_id}",
        "",
        "```yaml",
        "type: preference",
        f"status: {status}",
        f"scope: {scope}",
        "triggers:",
        *yaml_list(triggers),
        f"rule: {rule}",
        "do:",
        *yaml_list(do_items),
        "dont:",
        *yaml_list(dont_items),
        "evidence:",
        *yaml_list(evidence_items),
        "```",
    ]
    return "\n".join(lines)


def remove_existing_card(text: str, memory_id: str) -> tuple[str, bool]:
    lines = text.splitlines()
    output: list[str] = []
    removed = False
    index = 0
    card_heading = f"### {memory_id}"

    while index < len(lines):
        if lines[index].strip() == card_heading:
            removed = True
            index += 1
            while index < len(lines) and not lines[index].startswith(("## ", "### ")):
                index += 1
            while output and output[-1] == "":
                output.pop()
            continue
        output.append(lines[index])
        index += 1

    return "\n".join(output).rstrip() + "\n", removed


def insert_card(text: str, section: str, card: str) -> str:
    lines = text.splitlines()
    heading = f"## {section}"
    try:
        section_index = next(index for index, line in enumerate(lines) if line.strip() == heading)
    except StopIteration:
        lines.extend(["", heading])
        section_index = len(lines) - 1

    insert_index = len(lines)
    for index in range(section_index + 1, len(lines)):
        if lines[index].startswith("## "):
            insert_index = index
            break

    before = lines[:insert_index]
    after = lines[insert_index:]
    while before and before[-1] == "":
        before.pop()

    card_lines = card.splitlines()
    merged = before + [""] + card_lines + [""]
    if after:
        while after and after[0] == "":
            after.pop(0)
        merged += after
    return "\n".join(merged).rstrip() + "\n"


def sync_preference_memory(
    repo_root: Path,
    memory_id: str,
    status: str,
    scope: str,
    triggers: list[str],
    rule: str,
    do_items: list[str],
    dont_items: list[str],
    evidence_items: list[str],
) -> PreferenceSyncResult:
    if status not in VALID_STATUSES:
        raise ValueError(f"Unsupported status: {status}")
    if not memory_id.strip():
        raise ValueError("Preference id must not be empty")
    if not rule.strip():
        raise ValueError("Preference rule must not be empty")

    target = resolve_preference_file(repo_root)
    target.parent.mkdir(parents=True, exist_ok=True)

    text = ensure_sections(read_or_create_document(target))
    text_without_card, removed = remove_existing_card(text, memory_id)
    section = SECTION_BY_STATUS[status]
    card = build_card(
        memory_id=memory_id,
        status=status,
        scope=scope,
        triggers=triggers,
        rule=rule,
        do_items=do_items,
        dont_items=dont_items,
        evidence_items=evidence_items,
    )
    updated_text = insert_card(text_without_card, section, card)
    target.write_text(updated_text, encoding="utf-8")

    return PreferenceSyncResult(
        updated=True,
        target=str(target),
        memory_id=memory_id,
        status=status,
        section=section,
        action="replaced" if removed else "created",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sync structured preference memory cards.")
    parser.add_argument("--repo", default=".", help="Repository root.")
    parser.add_argument("--id", required=True, dest="memory_id", help="Stable preference card id.")
    parser.add_argument("--status", choices=sorted(VALID_STATUSES), required=True)
    parser.add_argument("--scope", default="project")
    parser.add_argument("--trigger", action="append", default=[])
    parser.add_argument("--rule", required=True)
    parser.add_argument("--do", action="append", default=[], dest="do_items")
    parser.add_argument("--dont", action="append", default=[], dest="dont_items")
    parser.add_argument("--evidence", action="append", default=[], dest="evidence_items")
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        result = sync_preference_memory(
            repo_root=Path(args.repo),
            memory_id=args.memory_id,
            status=args.status,
            scope=args.scope,
            triggers=args.trigger,
            rule=args.rule,
            do_items=args.do_items,
            dont_items=args.dont_items,
            evidence_items=args.evidence_items,
        )
    except ValueError as exc:
        print(json.dumps({"updated": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2

    print(
        json.dumps(
            {
                "updated": result.updated,
                "target": result.target,
                "memory_id": result.memory_id,
                "status": result.status,
                "section": result.section,
                "action": result.action,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
