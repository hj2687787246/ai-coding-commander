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
    load_schema,
    utc_now,
    validate_instance,
    write_json,
)


COMMANDER_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = COMMANDER_ROOT.parent
SPEC_DIR = PROJECT_ROOT / "commander" / "specs"
SPEC_SCHEMA_PATH = COMMANDER_ROOT / "transport" / "schemas" / "commander_spec_artifact.schema.json"


def resolve_spec_dir() -> Path:
    return SPEC_DIR


def resolve_spec_path(spec_path: str | Path) -> Path:
    candidate = Path(spec_path)
    if candidate.is_absolute():
        return candidate.resolve()
    return (PROJECT_ROOT / candidate).resolve()


def resolve_spec_id_from_path(spec_path: str | Path) -> str:
    return resolve_spec_path(spec_path).stem


def _canonical_spec_path(spec_path: str | Path) -> str:
    resolved = resolve_spec_path(spec_path)
    try:
        return resolved.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def load_spec_artifact(path: str | Path) -> dict[str, Any]:
    resolved = resolve_spec_path(path)
    if not resolved.exists():
        raise SchemaValidationError(f"Spec artifact not found: {resolved}")
    payload = load_json(resolved)
    if not isinstance(payload, dict):
        raise SchemaValidationError("Spec artifact root must be an object")
    return validate_spec_artifact(payload)


def validate_spec_artifact(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    validate_instance(normalized, load_schema(SPEC_SCHEMA_PATH))
    return normalized


def build_spec_artifact_draft(
    spec_id: str,
    title: str,
    *,
    summary: str | None = None,
    owner: str = "commander",
    source_task_id: str | None = None,
    source_phase_id: str | None = None,
    source_objective_id: str | None = None,
) -> dict[str, Any]:
    now = utc_now()
    base_summary = summary or f"Draft spec artifact for {title}."
    return {
        "schema_version": "commander-spec-artifact-v1",
        "spec_id": spec_id,
        "title": title,
        "status": "draft",
        "owner": owner,
        "summary": base_summary,
        "source_task_id": source_task_id,
        "source_phase_id": source_phase_id,
        "source_objective_id": source_objective_id,
        "constitution": {
            "summary": "Define ownership, scope, and guardrails for this spec.",
            "principles": [],
            "guardrails": [],
        },
        "specification": {
            "summary": "State the artifact contract in machine-readable terms.",
            "requirements": [],
            "interfaces": [],
            "constraints": [],
        },
        "planning": {
            "summary": "Capture the rollout plan and phase checkpoints.",
            "milestones": [],
        },
        "tasking": {
            "summary": "Describe how planning turns into packets and worker tasks.",
            "dispatch_rules": [],
            "task_contracts": [],
            "packet_requirements": [],
        },
        "implementation_state": {
            "summary": "Draft scaffold awaiting repository-specific fill-in.",
            "stage": "draft",
            "status": "planned",
            "evidence": [],
            "blockers": [],
            "notes": [],
        },
        "acceptance": [],
        "non_goals": [],
        "invariants": [],
        "truth_sources": [],
        "tags": [],
        "notes": [],
        "created_at": now,
        "updated_at": now,
    }


def write_spec_artifact(path: str | Path, payload: dict[str, Any]) -> dict[str, Any]:
    validated = validate_spec_artifact(payload)
    write_json(resolve_spec_path(path), validated)
    return validated


def normalize_spec_ref(spec_ref: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(spec_ref, str):
        spec_ref = {"path": spec_ref}
    if not isinstance(spec_ref, dict):
        raise SchemaValidationError("Spec ref must be a string path or an object")

    path_value = spec_ref.get("path")
    if not isinstance(path_value, str) or not path_value.strip():
        raise SchemaValidationError("Spec ref is missing path")

    spec_id = spec_ref.get("spec_id")
    if not isinstance(spec_id, str) or not spec_id.strip():
        spec_id = resolve_spec_id_from_path(path_value)
    normalized = {
        "spec_id": spec_id.strip(),
        "path": _canonical_spec_path(path_value),
    }
    for key in ("title", "section", "reason", "role", "status", "owner"):
        value = spec_ref.get(key)
        if isinstance(value, str) and value.strip():
            normalized[key] = value.strip()
    return normalized


def normalize_spec_refs(spec_refs: Any) -> list[dict[str, Any]]:
    if not isinstance(spec_refs, list):
        return []
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str | None, str | None, str | None]] = set()
    for item in spec_refs:
        if not isinstance(item, (dict, str)):
            raise SchemaValidationError("Spec refs must contain only strings or objects")
        ref = normalize_spec_ref(item)
        key = (
            ref["spec_id"],
            ref["path"],
            ref.get("section"),
            ref.get("role"),
            ref.get("reason"),
        )
        if key in seen:
            continue
        seen.add(key)
        normalized.append(ref)
    return normalized


def merge_spec_refs(*spec_ref_groups: Any) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for group in spec_ref_groups:
        merged.extend(normalize_spec_refs(group))
    return normalize_spec_refs(merged)


def collect_spec_artifact_paths(spec_refs: Any) -> list[str]:
    paths: list[str] = []
    for ref in normalize_spec_refs(spec_refs):
        resolved = resolve_spec_path(ref["path"])
        if not resolved.exists():
            raise SchemaValidationError(f"Spec artifact not found: {resolved}")
        artifact = load_spec_artifact(resolved)
        if artifact.get("spec_id") != ref["spec_id"]:
            raise SchemaValidationError(
                f"Spec ref spec_id {ref['spec_id']!r} does not match artifact {artifact.get('spec_id')!r}"
            )
        paths.append(str(resolved))
    return sorted(dict.fromkeys(paths))


def build_spec_ref(spec_path: str | Path, *, section: str | None = None, reason: str | None = None, role: str | None = None) -> dict[str, Any]:
    artifact = load_spec_artifact(spec_path)
    ref: dict[str, Any] = {
        "spec_id": str(artifact["spec_id"]),
        "path": _canonical_spec_path(spec_path),
        "title": str(artifact["title"]),
        "status": str(artifact["status"]),
        "owner": str(artifact["owner"]),
    }
    if section is not None and str(section).strip():
        ref["section"] = str(section).strip()
    if reason is not None and str(reason).strip():
        ref["reason"] = str(reason).strip()
    if role is not None and str(role).strip():
        ref["role"] = str(role).strip()
    return ref


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create and validate commander spec artifacts.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    template_parser = subparsers.add_parser("template")
    template_parser.add_argument("--spec-id", required=True)
    template_parser.add_argument("--title", required=True)
    template_parser.add_argument("--summary", default=None)
    template_parser.add_argument("--owner", default="commander")
    template_parser.add_argument("--source-task-id", default=None)
    template_parser.add_argument("--source-phase-id", default=None)
    template_parser.add_argument("--source-objective-id", default=None)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--spec-file", required=True)

    ref_parser = subparsers.add_parser("ref")
    ref_parser.add_argument("--spec-file", required=True)
    ref_parser.add_argument("--section", default=None)
    ref_parser.add_argument("--reason", default=None)
    ref_parser.add_argument("--role", default=None)

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "template":
        payload = build_spec_artifact_draft(
            args.spec_id,
            args.title,
            summary=args.summary,
            owner=args.owner,
            source_task_id=args.source_task_id,
            source_phase_id=args.source_phase_id,
            source_objective_id=args.source_objective_id,
        )
    elif args.command == "validate":
        payload = load_spec_artifact(args.spec_file)
    else:
        payload = build_spec_ref(
            args.spec_file,
            section=args.section,
            reason=args.reason,
            role=args.role,
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
