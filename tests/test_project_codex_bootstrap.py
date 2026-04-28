import importlib.util
import subprocess
import sys
from pathlib import Path


def load_module(relative_path: str, module_name: str):
    repo_root = Path(__file__).resolve().parents[1]
    target = repo_root / relative_path
    spec = importlib.util.spec_from_file_location(module_name, target)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True, text=True)


def test_bootstrap_creates_standard_codex_skeleton(tmp_path: Path) -> None:
    bootstrap = load_module(
        "skills/commander-mode/scripts/bootstrap_codex_workspace.py",
        "bootstrap_codex_workspace",
    )
    repo = tmp_path / "repo"
    repo.mkdir()

    result = bootstrap.bootstrap_workspace(repo)

    assert result.created is True
    assert (repo / ".codex" / "AGENT.md").exists()
    assert (repo / ".codex" / "docs" / "当前任务.md").exists()
    current_task = (repo / ".codex" / "docs" / "当前任务.md").read_text(encoding="utf-8")
    assert "当前任务模式" in current_task
    assert "当前任务形状" in current_task
    assert "执行强度" in current_task
    assert "验证状态" in current_task
    assert "验证证据" in current_task
    assert "当前任务形状：待确认" in current_task
    assert "执行强度：待确认" in current_task
    assert "学习进度卡" not in current_task


def test_bootstrap_does_not_overwrite_existing_agents(tmp_path: Path) -> None:
    bootstrap = load_module(
        "skills/commander-mode/scripts/bootstrap_codex_workspace.py",
        "bootstrap_codex_workspace",
    )
    repo = tmp_path / "repo"
    repo.mkdir()
    agents = repo / "AGENTS.md"
    agents.write_text("keep me\n", encoding="utf-8")

    bootstrap.bootstrap_workspace(repo)

    assert agents.read_text(encoding="utf-8") == "keep me\n"


def test_bootstrap_is_idempotent_and_marks_project_initialized(tmp_path: Path) -> None:
    bootstrap = load_module(
        "skills/commander-mode/scripts/bootstrap_codex_workspace.py",
        "bootstrap_codex_workspace_idempotent",
    )
    harness = load_module(
        "skills/commander-mode/scripts/portable_harness.py",
        "portable_harness_after_bootstrap",
    )
    repo = tmp_path / "repo"
    repo.mkdir()
    init_git_repo(repo)

    first = bootstrap.bootstrap_workspace(repo)
    second = bootstrap.bootstrap_workspace(repo)
    status = harness.build_status(repo)

    assert first.created is True
    assert second.created is False
    assert second.created_paths == []
    assert status["commander_protocol"]["initialized"] is True
    assert ".codex/AGENT.md" in status["commander_protocol"]["markers"]


def test_bootstrap_script_can_run_as_cli(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "skills" / "commander-mode" / "scripts" / "bootstrap_codex_workspace.py"
    repo = tmp_path / "repo"
    repo.mkdir()

    result = subprocess.run(
        [sys.executable, str(script), "--repo", str(repo)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0
    assert (repo / ".codex" / "AGENT.md").exists()
    assert "created" in result.stdout


def test_project_codex_layout_mentions_current_task_not_learning_card() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    doc = (repo_root / "skills" / "commander-mode" / "references" / "project-codex-layout.md").read_text(
        encoding="utf-8"
    )
    structure_block = doc.split("```text", 1)[1].split("```", 1)[0]
    assert "当前任务.md" in doc
    assert "学习进度卡" not in structure_block


def test_commander_skill_uses_initialized_uninitialized_flow() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    skill = (repo_root / "skills" / "commander-mode" / "SKILL.md").read_text(encoding="utf-8")

    assert "已初始化项目" in skill
    assert "未初始化项目" in skill
    assert "学习进度卡.md" not in skill
    assert "学习时间线.md" not in skill


def test_commander_skill_explains_repo_local_vs_installed_harness_paths() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    skill = (repo_root / "skills" / "commander-mode" / "SKILL.md").read_text(encoding="utf-8")

    assert "When developing this repository itself" in skill
    assert "C:\\Users\\26877\\.codex\\skills\\commander-mode\\scripts\\portable_harness.py" in skill


def test_commander_skill_does_not_force_bootstrap_for_uninitialized_projects() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    skill = (repo_root / "skills" / "commander-mode" / "SKILL.md").read_text(encoding="utf-8")

    assert "未初始化项目" in skill
    assert "没有 `.codex`" in skill
    assert "仍然正常工作" in skill
    assert "不强制创建完整 `.codex` 模板" in skill


def test_commander_skill_absorbs_taskmaster_task_governance_language() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    skill = (repo_root / "skills" / "commander-mode" / "SKILL.md").read_text(encoding="utf-8")

    assert "single" in skill and "epic" in skill and "batch" in skill
    assert "compact" in skill and "full" in skill
    assert "没有验证证据，不得标记任务完成" in skill
    assert "磁盘上的当前任务真相源优先于聊天记忆" in skill


def test_project_codex_agent_template_includes_task_governance_rules() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    agent_doc = (
        repo_root
        / "skills"
        / "commander-mode"
        / "references"
        / "templates"
        / "project-codex-standard"
        / ".codex"
        / "AGENT.md"
    ).read_text(encoding="utf-8")

    assert "当前任务.md" in agent_doc
    assert "验证证据" in agent_doc
    assert "未验证不得标记任务完成" in agent_doc


def test_project_codex_layout_mentions_optional_batch_extension_without_new_primary_protocol() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    doc = (repo_root / "skills" / "commander-mode" / "references" / "project-codex-layout.md").read_text(
        encoding="utf-8"
    )

    assert "batch/" in doc
    assert "可选" in doc
    assert ".codex-tasks" not in doc


def test_recovery_entry_mentions_batch_follow_up_for_batch_tasks() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    recovery_doc = (
        repo_root
        / "skills"
        / "commander-mode"
        / "references"
        / "templates"
        / "project-codex-standard"
        / ".codex"
        / "docs"
        / "恢复入口.md"
    ).read_text(encoding="utf-8")

    assert "当前任务形状=batch" in recovery_doc
    assert ".codex/batch/" in recovery_doc
