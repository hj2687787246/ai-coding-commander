from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def read_text(relative_path: str) -> str:
    return (repo_root() / relative_path).read_text(encoding="utf-8")


def test_commander_skill_is_high_signal_skill_not_platform() -> None:
    skill = read_text("skills/commander-mode/SKILL.md")

    assert "高信号" in skill
    assert "skill 负责不丢上下文" in skill
    assert "不是平台" in skill
    assert "不是项目模板协议本身" in skill


def test_commander_skill_uses_context_investment_language() -> None:
    skill = read_text("skills/commander-mode/SKILL.md")

    assert "上下文投资" in skill
    assert "token 的目标是高回报" in skill
    assert "读之前先判断目的" in skill
    assert "机械读取完整模板" in skill


def test_commander_skill_auto_writeback_is_value_gated() -> None:
    skill = read_text("skills/commander-mode/SKILL.md")

    assert "自动写回" in skill
    assert "恢复价值节点" in skill
    assert "不依赖用户说" in skill
    assert "聊天原文" in skill
    assert "模型内部推理" in skill


def test_commander_skill_uses_process_checkpoints_for_long_tasks() -> None:
    skill = read_text("skills/commander-mode/SKILL.md")

    assert "覆盖式检查点" in skill
    assert "默认检查点不超过 8 行" in skill
    assert "继续下一段工作前写回" in skill
    assert "正在关注的文件" in skill


def test_commander_skill_works_without_codex() -> None:
    skill = read_text("skills/commander-mode/SKILL.md")

    assert "没有 `.codex`" in skill
    assert "仍然正常工作" in skill
    assert "不强制" in skill
    assert "完整 `.codex` 模板" in skill


def test_readme_presents_skill_first_positioning() -> None:
    readme = read_text("README.md")

    assert "高信号" in readme
    assert "skill" in readme
    assert "不是平台" in readme
    assert ".codex" in readme
    assert "可选" in readme
