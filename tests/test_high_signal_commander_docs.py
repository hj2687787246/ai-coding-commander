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


def test_readme_documents_preference_memory_protocol() -> None:
    readme = read_text("README.md")

    assert "Preference Memory" in readme
    assert "sync_preference_memory.py" in readme
    assert "偏好" in readme
    assert "Preference Gate" in readme


def test_readme_does_not_use_stale_repository_path_examples() -> None:
    readme = read_text("README.md")

    assert r"D:\Develop\Python-Project\ai-coding-commander" not in readme


def test_commander_skill_defines_preference_memory_protocol() -> None:
    skill = read_text("skills/commander-mode/SKILL.md")

    assert "Preference Memory Protocol" in skill
    assert "本轮适用偏好" in skill
    assert "Preference Gate" in skill
    assert "候选偏好" in skill
    assert "用户纠正方向" in skill


def test_commander_skill_defines_standard_activation_contract() -> None:
    skill = read_text("skills/commander-mode/SKILL.md")

    assert "Standard Activation Contract" in skill
    assert "MUST" in skill
    assert "Entry Hook" in skill
    assert "Heartbeat Hook" in skill
    assert "Preference Write-Back Hook" in skill
    assert "Preclose Hook" in skill
    assert "Recovery Hook" in skill


def test_standard_contract_requires_automatic_preference_activation() -> None:
    skill = read_text("skills/commander-mode/SKILL.md")

    assert "before planning, implementing, reviewing, verifying, or handing off" in skill
    assert "read `.codex/docs/协作偏好.md`" in skill
    assert "select 3-7 relevant cards" in skill
    assert "without waiting for the user to ask for memory write-back" in skill


def test_knowledge_context_hook_closes_external_research_writeback_loop() -> None:
    skill = read_text("skills/commander-mode/SKILL.md")

    assert "local AI-KB search has no useful hit" in skill
    assert "web research" in skill
    assert "candidate knowledge card" in skill
    assert "crawler keywords" in skill
    assert "source-index" in skill
    assert "re-search" in skill


def test_standard_contract_requires_checkpoint_before_wait_or_interruption() -> None:
    skill = read_text("skills/commander-mode/SKILL.md")

    assert "before any long-running command, wait, interruption risk, or phase switch" in skill
    assert "sync_current_task.py --event checkpoint" in skill
    assert "current goal, phase, progress, blocker, focus files, next step, validation status" in skill


def test_readme_presents_standard_activation_contract() -> None:
    readme = read_text("README.md")

    assert "Standard Activation Contract" in readme
    assert "Entry / Heartbeat / Preference Write-Back / Preclose / Recovery" in readme
    assert "不是建议清单" in readme


def test_preference_template_uses_structured_memory_cards() -> None:
    template = read_text(
        "skills/commander-mode/references/templates/project-codex-standard/.codex/docs/协作偏好.md"
    )

    assert "Stable Preferences" in template
    assert "Candidate Preferences" in template
    assert "type: preference" in template
    assert "triggers:" in template
    assert "do:" in template
    assert "dont:" in template
    assert "evidence:" in template
