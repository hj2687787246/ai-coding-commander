#!/usr/bin/env python3
"""Portable commander harness checks for any git workspace."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


INSTRUCTION_FILES = (
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    "README.md",
    "README.rst",
    "README.txt",
)


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


def run_command(args: list[str], *, cwd: Path, timeout: int = 10) -> CommandResult:
    safe_cwd = cwd if cwd.exists() and cwd.is_dir() else Path.cwd()
    try:
        completed = subprocess.run(
            args,
            cwd=str(safe_cwd),
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return CommandResult(returncode=127, stdout="", stderr=str(exc))
    return CommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout.strip(),
        stderr=completed.stderr.strip(),
    )


def resolve_cwd(raw_cwd: str | None) -> Path:
    candidate = Path(raw_cwd or ".").expanduser()
    if candidate.exists():
        if candidate.is_dir():
            return candidate.resolve()
        return candidate.parent.resolve()
    return candidate.resolve(strict=False)


def resolve_git_root(cwd: Path) -> Path | None:
    result = run_command(["git", "-C", str(cwd), "rev-parse", "--show-toplevel"], cwd=cwd)
    if result.returncode != 0 or not result.stdout:
        return None
    return Path(result.stdout).resolve()


def git_branch(repo_root: Path) -> str | None:
    branch = run_command(["git", "branch", "--show-current"], cwd=repo_root)
    if branch.returncode == 0 and branch.stdout:
        return branch.stdout
    head = run_command(["git", "rev-parse", "--short", "HEAD"], cwd=repo_root)
    if head.returncode == 0 and head.stdout:
        return f"detached:{head.stdout}"
    return None


def parse_git_status(repo_root: Path) -> list[dict[str, str]]:
    status = run_command(["git", "status", "--porcelain=v1"], cwd=repo_root)
    if status.returncode != 0:
        return []
    changes: list[dict[str, str]] = []
    for line in status.stdout.splitlines():
        if len(line) < 3:
            continue
        path = line[3:] if line[2:3] == " " else line[2:].lstrip()
        changes.append({"status": line[:2], "path": path})
    return changes


def existing_files(repo_root: Path, names: tuple[str, ...]) -> list[str]:
    return [name for name in names if (repo_root / name).exists()]


def detect_project_markers(repo_root: Path) -> dict[str, Any]:
    markers = {
        "python": (repo_root / "pyproject.toml").exists() or (repo_root / "requirements.txt").exists(),
        "node": (repo_root / "package.json").exists(),
        "go": (repo_root / "go.mod").exists(),
        "rust": (repo_root / "Cargo.toml").exists(),
        "make": (repo_root / "Makefile").exists() or (repo_root / "makefile").exists(),
        "tests_dir": (repo_root / "tests").is_dir() or (repo_root / "test").is_dir(),
    }
    return {key: value for key, value in markers.items() if value}


def package_json_has_test(repo_root: Path) -> bool:
    package_json = repo_root / "package.json"
    if not package_json.exists():
        return False
    try:
        payload = json.loads(package_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    scripts = payload.get("scripts")
    return isinstance(scripts, dict) and isinstance(scripts.get("test"), str)


def detect_validation_commands(repo_root: Path, markers: dict[str, Any]) -> list[str]:
    commands: list[str] = []
    if markers.get("python") and markers.get("tests_dir"):
        commands.append("python -m pytest")
    if package_json_has_test(repo_root):
        commands.append("npm test")
    if markers.get("go"):
        commands.append("go test ./...")
    if markers.get("rust"):
        commands.append("cargo test")
    if markers.get("make"):
        commands.append("make test")
    return commands


def detect_commander_assets(repo_root: Path) -> dict[str, Any]:
    return {
        "repo_commander_dir": (repo_root / "commander").is_dir(),
        "repo_stop_gate": (repo_root / "commander" / "transport" / "scripts" / "commander_stop_gate.py").exists(),
        "repo_task_catalog": (repo_root / "commander" / "transport" / "scripts" / "commander_task_catalog.py").exists(),
        "repo_skill_source": (repo_root / "commander" / "skill-source").is_dir(),
    }


def detect_commander_protocol(repo_root: Path) -> dict[str, Any]:
    markers: list[str] = []

    if (repo_root / ".codex" / "AGENT.md").exists():
        markers.append(".codex/AGENT.md")
    if (repo_root / ".codex" / "docs" / "当前状态.md").exists():
        markers.append(".codex/docs/当前状态.md")

    agents_file = repo_root / "AGENTS.md"
    if agents_file.exists():
        try:
            agents_text = agents_file.read_text(encoding="utf-8")
        except OSError:
            agents_text = ""
        if ".codex/AGENT.md" in agents_text and (repo_root / ".codex" / "AGENT.md").exists():
            markers.append("AGENTS.md -> .codex/AGENT.md")

    deduped = list(dict.fromkeys(markers))
    return {
        "initialized": bool(deduped),
        "markers": deduped,
    }


def build_status(cwd: Path) -> dict[str, Any]:
    repo_root = resolve_git_root(cwd)
    if repo_root is None:
        return {
            "schema_version": "commander-portable-harness-v1",
            "cwd": str(cwd),
            "is_git_repo": False,
            "harness_level": "none",
            "commander_protocol": {
                "initialized": False,
                "markers": [],
            },
            "next_actions": ["Open a git workspace or initialize repo-local task tracking before relying on harness checks."],
        }

    changes = parse_git_status(repo_root)
    markers = detect_project_markers(repo_root)
    instruction_files = existing_files(repo_root, INSTRUCTION_FILES)
    validation_commands = detect_validation_commands(repo_root, markers)
    commander_assets = detect_commander_assets(repo_root)
    harness_level = "repo-native" if commander_assets["repo_stop_gate"] else "portable"

    return {
        "schema_version": "commander-portable-harness-v1",
        "cwd": str(cwd),
        "repo_root": str(repo_root),
        "is_git_repo": True,
        "branch": git_branch(repo_root),
        "harness_level": harness_level,
        "instruction_files": instruction_files,
        "project_markers": markers,
        "validation_commands": validation_commands,
        "commander_protocol": detect_commander_protocol(repo_root),
        "commander_assets": commander_assets,
        "worktree": {
            "dirty": bool(changes),
            "change_count": len(changes),
            "changes": changes,
        },
    }


def build_stop_gate(cwd: Path, *, validations: list[str], allow_dirty: bool) -> dict[str, Any]:
    status = build_status(cwd)
    if not status.get("is_git_repo"):
        return {
            **status,
            "stop_allowed": False,
            "continuation_required": True,
            "reason": "not_a_git_workspace",
            "validation_evidence": validations,
            "next_actions": ["Run this from a git workspace or provide a repo-native stop gate."],
        }

    worktree = status["worktree"]
    dirty = bool(worktree["dirty"])
    if dirty and not validations and not allow_dirty:
        return {
            **status,
            "stop_allowed": False,
            "continuation_required": True,
            "reason": "dirty_worktree_without_validation_evidence",
            "validation_evidence": validations,
            "next_actions": [
                "Run the narrow validation for the changed files.",
                "Commit, stash, or explicitly report the dirty worktree before declaring the task complete.",
            ],
        }

    if dirty:
        return {
            **status,
            "stop_allowed": True,
            "continuation_required": False,
            "reason": "dirty_worktree_with_validation_or_explicit_allow_dirty",
            "validation_evidence": validations,
            "next_actions": ["Report the remaining dirty files and validation evidence."],
        }

    return {
        **status,
        "stop_allowed": True,
        "continuation_required": False,
        "reason": "clean_worktree",
        "validation_evidence": validations,
        "next_actions": [],
    }


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Run portable commander harness checks.")
    parser.add_argument("--cwd", default=".", help="Workspace path to inspect.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status", help="Inspect workspace harness status.")

    stop_gate = subparsers.add_parser("stop-gate", help="Run a portable stop gate.")
    stop_gate.add_argument(
        "--validation",
        action="append",
        default=[],
        help="Validation evidence, for example 'pytest passed'. May be repeated.",
    )
    stop_gate.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Allow stop even when the worktree is dirty and no validation evidence is provided.",
    )

    args = parser.parse_args(argv)
    cwd = resolve_cwd(args.cwd)
    if args.command == "status":
        payload = build_status(cwd)
    elif args.command == "stop-gate":
        payload = build_stop_gate(cwd, validations=args.validation, allow_dirty=args.allow_dirty)
    else:
        parser.error(f"Unknown command: {args.command}")

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("stop_allowed", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
