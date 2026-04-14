from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from commander.transport.scripts.commander_memory_search import (
    MEMORY_INDEX_SCHEMA_PATH,
    MemoryDocument,
    build_memory_index,
    collect_memory_documents,
    resolve_sources,
    resolve_layers,
    search_documents,
)
from commander.transport.scripts.commander_harness import load_schema, validate_instance
from commander.transport.scripts.commander_skill_load import build_skill_load_plan


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON_EXE = Path(sys.executable)


def run_script(script_name: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(PYTHON_EXE), "-m", f"commander.transport.scripts.{script_name.removesuffix('.py')}", *args],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_resolve_sources_expands_all_once() -> None:
    resolved = resolve_sources(["all", "task_card"])
    assert "task_card" in resolved
    assert "report" in resolved
    assert resolved.count("task_card") == 1


def test_resolve_layers_expands_all_once() -> None:
    resolved = resolve_layers(["all", "session_runtime"])
    assert resolved == [
        "session_runtime",
        "persistent_commander_docs",
        "procedural_memory",
    ]


def test_search_documents_ranks_matching_memory_document() -> None:
    documents = [
        MemoryDocument(
            source="task_card",
            source_kind="commander_doc",
            path=PROJECT_ROOT / "commander" / "state" / "当前任务卡.md",
            title="指挥官当前任务卡",
            text="项目工程化推进\n下一步最小动作：归档",
        ),
        MemoryDocument(
            source="report",
            source_kind="runtime_artifact",
            path=PROJECT_ROOT / ".runtime" / "commander" / "tasks" / "demo" / "report.json",
            title="demo",
            text='{"summary": "其他内容"}',
        ),
    ]

    hits = search_documents(documents, "项目工程化推进", limit=5)

    assert hits
    assert hits[0]["source"] == "task_card"
    assert "项目工程化推进" in hits[0]["excerpt"]


def test_collect_memory_documents_reads_runtime_artifacts(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    task_dir = runtime_root / "tasks" / "task-001"
    task_dir.mkdir(parents=True)
    (task_dir / "checkpoint.json").write_text(
        json.dumps({"task_id": "task-001", "title": "Checkpoint task"}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (task_dir / "report.json").write_text(
        json.dumps({"task_id": "task-001", "summary": "Report task"}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    documents = collect_memory_documents(runtime_root, ["checkpoint", "report"])

    assert len(documents) == 2
    assert {document.source for document in documents} == {"checkpoint", "report"}
    assert all(document.source_kind == "runtime_artifact" for document in documents)


def test_collect_memory_documents_includes_three_layers(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    task_dir = runtime_root / "tasks" / "task-001"
    task_dir.mkdir(parents=True)
    (task_dir / "checkpoint.json").write_text(
        json.dumps(
            {
                "task_id": "task-001",
                "title": "Checkpoint task",
                "summary": "memory retrieval layer",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    repo_root = tmp_path / "repo"
    task_card_path = repo_root / "commander" / "state" / "当前任务卡.md"
    task_card_path.parent.mkdir(parents=True)
    task_card_path.write_text(
        "# 当前任务卡\n\nmemory retrieval layer\n",
        encoding="utf-8",
    )
    script_path = repo_root / "scripts" / "demo_memory.py"
    script_path.parent.mkdir(parents=True)
    script_path.write_text(
        '"""memory retrieval layer"""\n',
        encoding="utf-8",
    )
    skill_root = tmp_path / "skills"
    skill_path = skill_root / "demo" / "SKILL.md"
    skill_path.parent.mkdir(parents=True)
    skill_path.write_text(
        "---\nname: demo-memory\n---\nmemory retrieval layer\n",
        encoding="utf-8",
    )

    documents = collect_memory_documents(
        runtime_root,
        ["checkpoint", "task_card", "repo_scripts", "local_skills"],
        layers=[
            "session_runtime",
            "persistent_commander_docs",
            "procedural_memory",
        ],
        repo_root=repo_root,
        local_skill_root=skill_root,
    )

    layers = {document.layer for document in documents}
    sources = {document.source for document in documents}
    assert layers == {
        "session_runtime",
        "persistent_commander_docs",
        "procedural_memory",
    }
    assert {"checkpoint", "task_card", "repo_scripts", "local_skills"} <= sources


def test_memory_index_builds_skill_source_registry_metadata_first(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    candidate_skill_path = (
        runtime_root
        / "skill_candidates"
        / "candidate-001"
        / "SKILL.candidate.md"
    )
    candidate_skill_path.parent.mkdir(parents=True)
    candidate_skill_path.write_text(
        "---\n"
        "name: demo-skill\n"
        "description: candidate skill draft\n"
        "---\n"
        "candidate-only deep body token\n",
        encoding="utf-8",
    )
    repo_root = tmp_path / "repo"
    repo_skill_path = repo_root / "commander" / "skill-source" / "demo" / "SKILL.md"
    repo_skill_path.parent.mkdir(parents=True)
    repo_skill_path.write_text(
        "---\n"
        "name: demo-skill\n"
        "description: repo truth skill\n"
        "---\n"
        "repo-only deep body token\n",
        encoding="utf-8",
    )
    local_skill_root = tmp_path / "skills"
    local_skill_path = local_skill_root / "demo-skill" / "SKILL.md"
    local_skill_path.parent.mkdir(parents=True)
    local_skill_path.write_text(
        "---\n"
        "name: demo-skill\n"
        "description: local installed skill\n"
        "---\n"
        "local-only deep body token\n",
        encoding="utf-8",
    )

    payload = build_memory_index(
        runtime_root,
        "repo truth skill",
        sources=["repo_skill_source", "local_skills", "candidate_skills"],
        layers=["procedural_memory"],
        repo_root=repo_root,
        local_skill_root=local_skill_root,
    )

    validate_instance(payload, load_schema(MEMORY_INDEX_SCHEMA_PATH))
    registry = payload["skill_source_registry"]
    assert registry["entry_count"] == 3
    assert registry["load_policy"]["default_mode"] == "metadata_first"
    effective = registry["effective_sources"][0]
    assert effective["skill_name"] == "demo-skill"
    assert effective["source"] == "repo_skill_source"
    candidate = next(
        entry for entry in registry["entries"] if entry["source"] == "candidate_skills"
    )
    assert candidate["is_effective_source"] is False
    assert candidate["candidate_can_override_live"] is False
    assert payload["results"][0]["registry_metadata"]["body_loaded"] is False
    assert payload["results"][0]["source"] == "repo_skill_source"
    assert "repo-only deep body token" not in payload["results"][0]["excerpt"]


def test_skill_load_plan_reads_body_only_on_explicit_request(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    candidate_skill_path = (
        runtime_root
        / "skill_candidates"
        / "candidate-001"
        / "SKILL.candidate.md"
    )
    candidate_skill_path.parent.mkdir(parents=True)
    candidate_skill_path.write_text(
        "---\n"
        "name: demo-skill\n"
        "description: candidate skill draft\n"
        "---\n"
        "candidate body\n",
        encoding="utf-8",
    )
    repo_root = tmp_path / "repo"
    repo_skill_path = repo_root / "commander" / "skill-source" / "demo" / "SKILL.md"
    repo_skill_path.parent.mkdir(parents=True)
    repo_skill_path.write_text(
        "---\n"
        "name: demo-skill\n"
        "description: repo truth skill\n"
        "---\n"
        "repo body\n",
        encoding="utf-8",
    )
    local_skill_root = tmp_path / "skills"
    local_skill_path = local_skill_root / "demo-skill" / "SKILL.md"
    local_skill_path.parent.mkdir(parents=True)
    local_skill_path.write_text(
        "---\n"
        "name: demo-skill\n"
        "description: local installed skill\n"
        "---\n"
        "local body\n",
        encoding="utf-8",
    )

    plan = build_skill_load_plan(
        runtime_root,
        "demo-skill",
        repo_root=repo_root,
        local_skill_root=local_skill_root,
    )
    candidate = build_skill_load_plan(
        runtime_root,
        "demo-skill",
        source="candidate_skills",
        include_body=True,
        repo_root=repo_root,
        local_skill_root=local_skill_root,
    )

    assert plan["status"] == "planned"
    assert plan["selected_source"] == "repo_skill_source"
    assert plan["body_loaded"] is False
    assert plan["body"] is None
    assert candidate["status"] == "loaded"
    assert candidate["selected_source"] == "candidate_skills"
    assert candidate["candidate_review_only"] is True
    assert candidate["candidate_can_override_live"] is False
    assert "candidate body" in candidate["body"]


def test_memory_search_cli_finds_runtime_report(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    task_dir = runtime_root / "tasks" / "task-001"
    task_dir.mkdir(parents=True)
    report_path = task_dir / "report.json"
    report_path.write_text(
        json.dumps(
            {
                "task_id": "task-001",
                "title": "Hermes-lite memory search",
                "summary": "Memory retrieval layer completed for commander resume flow.",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    result = run_script(
        "commander_memory_search.py",
        "--runtime-root",
        str(runtime_root),
        "--source",
        "report",
        "--query",
        "Memory retrieval layer",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["result_count"] == 1
    assert payload["results"][0]["source"] == "report"
    assert payload["results"][0]["path"] == str(report_path)


def test_memory_index_cli_reports_three_layers(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    task_dir = runtime_root / "tasks" / "task-001"
    task_dir.mkdir(parents=True)
    (task_dir / "checkpoint.json").write_text(
        json.dumps(
            {
                "task_id": "task-001",
                "title": "Checkpoint task",
                "summary": "memory retrieval layer",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    repo_root = tmp_path / "repo"
    task_card_path = repo_root / "commander" / "state" / "当前任务卡.md"
    task_card_path.parent.mkdir(parents=True)
    task_card_path.write_text(
        "# 当前任务卡\n\nmemory retrieval layer\n",
        encoding="utf-8",
    )
    script_path = repo_root / "scripts" / "demo_memory.py"
    script_path.parent.mkdir(parents=True)
    script_path.write_text(
        '"""memory retrieval layer"""\n',
        encoding="utf-8",
    )
    skill_root = tmp_path / "skills"
    skill_path = skill_root / "demo" / "SKILL.md"
    skill_path.parent.mkdir(parents=True)
    skill_path.write_text(
        "---\nname: demo-memory\n---\nmemory retrieval layer\n",
        encoding="utf-8",
    )

    result = run_script(
        "commander_memory_search.py",
        "--runtime-root",
        str(runtime_root),
        "--repo-root",
        str(repo_root),
        "--local-skill-root",
        str(skill_root),
        "--layer",
        "session_runtime",
        "--layer",
        "persistent_commander_docs",
        "--layer",
        "procedural_memory",
        "--source",
        "checkpoint",
        "--source",
        "task_card",
        "--source",
        "repo_scripts",
        "--source",
        "local_skills",
        "--query",
        "memory retrieval layer",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    validate_instance(payload, load_schema(MEMORY_INDEX_SCHEMA_PATH))
    assert payload["index"]["layer_count"] == 3
    assert payload["result_count"] >= 3
    assert {hit["layer"] for hit in payload["results"]} == {
        "session_runtime",
        "persistent_commander_docs",
        "procedural_memory",
    }
