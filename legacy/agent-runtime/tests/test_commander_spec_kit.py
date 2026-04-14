from __future__ import annotations

from pathlib import Path

from commander.transport.scripts.commander_harness import load_schema, validate_instance
from commander.transport.scripts.commander_spec_kit import (
    SPEC_SCHEMA_PATH,
    build_spec_artifact_draft,
    build_spec_ref,
    collect_spec_artifact_paths,
    load_spec_artifact,
    normalize_spec_refs,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_spec_artifact_draft_validates_against_schema() -> None:
    draft = build_spec_artifact_draft(
        "task-5-7-spec-template",
        "Spec-Kit / SDD artifact layer",
        summary="Draft spec artifact used to seed the repo-native spec layer.",
    )
    validate_instance(draft, load_schema(SPEC_SCHEMA_PATH))


def test_spec_artifact_sample_file_and_spec_refs_are_machine_readable() -> None:
    spec_path = PROJECT_ROOT / "commander" / "specs" / "task-5-7-spec-template.json"
    artifact = load_spec_artifact(spec_path)
    validate_instance(artifact, load_schema(SPEC_SCHEMA_PATH))
    assert artifact["source_task_id"] == "task-5-7-spec-template"
    assert artifact["source_phase_id"] == "phase-5-7-spec-kit-sdd"
    assert artifact["source_objective_id"] == "objective-5-6-langgraph-runtime"

    normalized = normalize_spec_refs(
        [
            {
                "spec_id": "task-5-7-spec-template",
                "path": "commander/specs/task-5-7-spec-template.json",
            }
        ]
    )
    assert normalized[0]["spec_id"] == "task-5-7-spec-template"
    assert normalized[0]["path"] == "commander/specs/task-5-7-spec-template.json"

    ref = build_spec_ref(spec_path)
    assert ref["spec_id"] == "task-5-7-spec-template"
    assert ref["title"] == "Spec-Kit / SDD artifact layer"
    assert ref["status"] == "active"

    paths = collect_spec_artifact_paths(normalized)
    assert paths == [str(spec_path.resolve())]
