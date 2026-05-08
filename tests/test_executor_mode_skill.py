from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def read_text(relative_path: str) -> str:
    return (repo_root() / relative_path).read_text(encoding="utf-8")


def test_executor_mode_skill_exists_with_trigger_frontmatter() -> None:
    skill = read_text("skills/executor-mode/SKILL.md")

    assert "name: executor-mode" in skill
    assert "description: Use when" in skill
    assert "执行者" in skill
    assert "task-id" in skill
    assert "current task card" in skill


def test_executor_mode_keeps_commander_boundary() -> None:
    skill = read_text("skills/executor-mode/SKILL.md")

    assert "执行者不是指挥官" in skill
    assert "Do not change requirements" in skill
    assert "Do not expand scope" in skill
    assert "hand back to commander" in skill
    assert "No self-declared final acceptance" in skill


def test_executor_mode_requires_evidence_and_isolated_task_card() -> None:
    skill = read_text("skills/executor-mode/SKILL.md")

    assert "Execution Loop" in skill
    assert "Preflight" in skill
    assert "Implement" in skill
    assert "Verify" in skill
    assert "Report" in skill
    assert ".codex/tasks/<task-id>/当前任务.md" in skill
    assert "sync_current_task.py --task-id" in skill
    assert "execution-failure-guard" in skill


def test_executor_mode_continues_until_assigned_outcome() -> None:
    skill = read_text("skills/executor-mode/SKILL.md")

    assert "User-Visible Outcome Target" in skill
    assert "Do not stop at phase completion" in skill
    assert "continue to the assigned user-visible result" in skill
    assert "checkpoint, then continue" in skill
    assert "Stop only when" in skill


def test_commander_routes_executor_mode() -> None:
    commander = read_text("skills/commander-mode/SKILL.md")
    matrix = read_text("docs/skill-trigger-matrix.md")
    readme = read_text("README.md")

    assert "executor-mode" in commander
    assert "执行者" in commander
    assert "executor-mode" in matrix
    assert "executor-mode" in readme
