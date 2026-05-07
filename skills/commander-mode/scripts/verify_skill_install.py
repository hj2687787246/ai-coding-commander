"""Verify distributed commander skills are installed and in sync."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REQUIRED_SKILLS = ("commander-mode", "commander-reuse-upgrader", "execution-failure-guard")


@dataclass(frozen=True)
class SkillCheck:
    name: str
    source: str
    target: str
    installed: bool
    source_exists: bool
    frontmatter_ok: bool
    name_matches: bool
    description_present: bool
    content_matches: bool
    files_match: bool
    missing_files: list[str]
    extra_files: list[str]
    changed_files: list[str]
    source_hash: str | None = None
    target_hash: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return (
            self.installed
            and self.source_exists
            and self.frontmatter_ok
            and self.name_matches
            and self.description_present
            and self.content_matches
            and self.files_match
            and self.error is None
        )


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_frontmatter(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    result: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return result
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        result[key.strip()] = value.strip()
    return {}


def relative_file_hashes(root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            relative_path = path.relative_to(root).as_posix()
            hashes[relative_path] = file_hash(path)
    return hashes


def check_skill(repo_root: Path, codex_home: Path, skill_name: str) -> SkillCheck:
    source = repo_root / "skills" / skill_name / "SKILL.md"
    target = codex_home / "skills" / skill_name / "SKILL.md"
    source_dir = source.parent
    target_dir = target.parent
    source_exists = source.exists()
    installed = target.exists()

    if not source_exists or not installed:
        return SkillCheck(
            name=skill_name,
            source=str(source),
            target=str(target),
            installed=installed,
            source_exists=source_exists,
            frontmatter_ok=False,
            name_matches=False,
            description_present=False,
            content_matches=False,
            files_match=False,
            missing_files=[],
            extra_files=[],
            changed_files=[],
            error="source or installed SKILL.md missing",
        )

    try:
        source_text = source.read_text(encoding="utf-8")
        target_text = target.read_text(encoding="utf-8")
        frontmatter = parse_frontmatter(source_text)
        source_hash = file_hash(source)
        target_hash = file_hash(target)
        source_files = relative_file_hashes(source_dir)
        target_files = relative_file_hashes(target_dir)
        missing_files = sorted(set(source_files) - set(target_files))
        extra_files = sorted(set(target_files) - set(source_files))
        changed_files = sorted(
            relative_path
            for relative_path in set(source_files) & set(target_files)
            if source_files[relative_path] != target_files[relative_path]
        )
    except OSError as exc:
        return SkillCheck(
            name=skill_name,
            source=str(source),
            target=str(target),
            installed=installed,
            source_exists=source_exists,
            frontmatter_ok=False,
            name_matches=False,
            description_present=False,
            content_matches=False,
            files_match=False,
            missing_files=[],
            extra_files=[],
            changed_files=[],
            error=str(exc),
        )

    files_match = not missing_files and not extra_files and not changed_files
    return SkillCheck(
        name=skill_name,
        source=str(source),
        target=str(target),
        installed=installed,
        source_exists=source_exists,
        frontmatter_ok=bool(frontmatter),
        name_matches=frontmatter.get("name") == skill_name,
        description_present=bool(frontmatter.get("description")),
        content_matches=source_text == target_text,
        files_match=files_match,
        missing_files=missing_files,
        extra_files=extra_files,
        changed_files=changed_files,
        source_hash=source_hash,
        target_hash=target_hash,
    )


def verify_install(repo_root: Path, codex_home: Path, skill_names: tuple[str, ...] = REQUIRED_SKILLS) -> dict[str, Any]:
    checks = [check_skill(repo_root.resolve(), codex_home.resolve(), skill_name) for skill_name in skill_names]
    return {
        "ok": all(check.ok for check in checks),
        "repo_root": str(repo_root.resolve()),
        "codex_home": str(codex_home.resolve()),
        "skills": [check.__dict__ | {"ok": check.ok} for check in checks],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify commander skills are installed and in sync.")
    parser.add_argument("--repo", default=".", help="Repository root.")
    parser.add_argument("--codex-home", default=str(Path.home() / ".codex"), help="Codex home directory.")
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    args = build_parser().parse_args(argv)
    result = verify_install(Path(args.repo), Path(args.codex_home))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
