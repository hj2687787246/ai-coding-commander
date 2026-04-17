"""Bootstrap a standard project-local `.codex` workspace."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
import shutil


TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "references" / "templates" / "project-codex-standard"


@dataclass(frozen=True)
class BootstrapResult:
    created: bool
    created_paths: list[str]


def bootstrap_workspace(repo_root: Path) -> BootstrapResult:
    repo_root = repo_root.resolve()
    created_paths: list[str] = []

    for source in TEMPLATE_ROOT.rglob("*"):
        if source.is_dir():
            continue
        relative = source.relative_to(TEMPLATE_ROOT)
        target = repo_root / relative
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        created_paths.append(str(relative).replace("\\", "/"))

    return BootstrapResult(created=bool(created_paths), created_paths=created_paths)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Bootstrap a standard project-local .codex workspace.")
    parser.add_argument("--repo", default=".", help="Repository path to initialize.")
    args = parser.parse_args(argv)

    result = bootstrap_workspace(Path(args.repo))
    print(
        json.dumps(
            {
                "created": result.created,
                "created_paths": result.created_paths,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
