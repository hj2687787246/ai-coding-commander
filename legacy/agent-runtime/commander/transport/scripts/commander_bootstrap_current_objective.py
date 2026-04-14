from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from commander.transport.scripts.commander_harness import (
    SchemaValidationError,
    load_json,
    normalize_runtime_root,
)
from commander.transport.scripts.commander_objective_plan import (
    build_objective_plan_summary,
    create_objective_plan,
    reconcile_objective_plan,
    resolve_objective_plan_path,
)


COMMANDER_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TEMPLATE_PATH = (
    COMMANDER_ROOT
    / "transport"
    / "objective_templates"
    / "langgraph_runtime_5_6.json"
)


def load_objective_template(template_path: str | Path | None = None) -> dict[str, Any]:
    resolved_template_path = Path(template_path or DEFAULT_TEMPLATE_PATH).resolve()
    payload = load_json(resolved_template_path)
    if not isinstance(payload, dict):
        raise SchemaValidationError(
            f"Objective template must be a JSON object: {resolved_template_path}"
        )
    phases = payload.get("phases")
    if not isinstance(phases, list):
        raise SchemaValidationError("Objective template requires a phases array")
    return payload


def bootstrap_current_objective(
    runtime_root: str | Path | None = None,
    *,
    template_path: str | Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    resolved_runtime_root = normalize_runtime_root(runtime_root)
    resolved_template_path = Path(template_path or DEFAULT_TEMPLATE_PATH).resolve()
    template = load_objective_template(resolved_template_path)
    objective_id = str(template.get("objective_id") or "").strip()
    objective_key = str(template.get("objective_key") or "").strip()
    objective_title = str(template.get("objective_title") or "").strip()
    objective = str(template.get("objective") or "").strip()
    objective_theme = template.get("objective_theme")
    phases = template.get("phases")

    if not objective_id or not objective_key or not objective_title or not objective:
        raise SchemaValidationError(
            "Objective template requires objective_id, objective_key, objective_title, and objective"
        )
    if objective_theme is not None and not isinstance(objective_theme, str):
        raise SchemaValidationError("Objective template objective_theme must be a string or null")
    if not isinstance(phases, list):
        raise SchemaValidationError("Objective template requires a phases array")

    objective_plan_path = resolve_objective_plan_path(
        resolved_runtime_root,
        objective_id,
    )
    existed_before = objective_plan_path.exists()
    if existed_before and not force:
        existing = reconcile_objective_plan(
            resolved_runtime_root,
            objective_id=objective_id,
        )
        return {
            "status": "already_exists",
            "runtime_root": str(resolved_runtime_root),
            "template_path": str(resolved_template_path),
            "objective_plan_path": str(objective_plan_path),
            "objective_summary": build_objective_plan_summary(
                resolved_runtime_root,
                existing,
            ),
        }

    created = create_objective_plan(
        resolved_runtime_root,
        objective_id=objective_id,
        objective_key=objective_key,
        objective_title=objective_title,
        objective=objective,
        objective_theme=objective_theme,
        phases=[phase for phase in phases if isinstance(phase, dict)],
    )
    return {
        "status": "replaced" if existed_before else "created",
        "runtime_root": str(resolved_runtime_root),
        "template_path": str(resolved_template_path),
        "objective_plan_path": str(objective_plan_path),
        "objective_summary": build_objective_plan_summary(
            resolved_runtime_root,
            created,
        ),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bootstrap the current commander objective into runtime backlog."
    )
    parser.add_argument(
        "--runtime-root",
        default=None,
        help="Override runtime root. Defaults to .runtime/commander.",
    )
    parser.add_argument(
        "--template-file",
        default=str(DEFAULT_TEMPLATE_PATH),
        help="Objective template JSON file.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace the existing objective plan if it already exists.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = bootstrap_current_objective(
        args.runtime_root,
        template_path=args.template_file,
        force=args.force,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
