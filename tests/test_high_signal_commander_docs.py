from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def read_text(relative_path: str) -> str:
    return (repo_root() / relative_path).read_text(encoding="utf-8")


def test_commander_skill_is_operating_layer_not_platform() -> None:
    skill = read_text("skills/commander-mode/SKILL.md")

    assert "operating layer" in skill
    assert "用户负责决策" in skill
    assert "not a project platform" in skill
    assert "not automatic permission to edit business code" in skill


def test_commander_skill_uses_context_investment_language() -> None:
    skill = read_text("skills/commander-mode/SKILL.md")

    assert "Context Investment" in skill
    assert "Before opening a file or running a command" in skill
    assert "High-value context" in skill
    assert "Low-value context" in skill


def test_commander_skill_auto_writeback_is_value_gated() -> None:
    skill = read_text("skills/commander-mode/SKILL.md")

    assert "Memory And Preference Gate" in skill
    assert "value-gated" in skill
    assert "durable recovery value" in skill
    assert "Do not write chat transcripts" in skill
    assert "model reasoning" in skill


def test_commander_skill_uses_process_checkpoints_for_long_tasks() -> None:
    skill = read_text("skills/commander-mode/SKILL.md")

    assert "compact overwrite-style checkpoint" in skill
    assert "goal, phase, progress, blocker" in skill
    assert "focus files" in skill
    assert "latest evidence" in skill


def test_commander_skill_works_without_codex() -> None:
    skill = read_text("skills/commander-mode/SKILL.md")

    assert "no `.codex` memory surface" in skill
    assert "commander still works" in skill
    assert "Do not force a full `.codex` bootstrap" in skill


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


def test_commander_skill_defines_preference_memory_gate() -> None:
    skill = read_text("skills/commander-mode/SKILL.md")

    assert "Memory And Preference Gate" in skill
    assert "本轮适用偏好" in skill
    assert "3-7 relevant preference cards" in skill
    assert "same-meaning rules" in skill
    assert "narrowest durable surface" in skill


def test_commander_skill_defines_runtime_gates() -> None:
    skill = read_text("skills/commander-mode/SKILL.md")

    assert "Entry Output Contract" in skill
    assert "Requirement Contract Gate" in skill
    assert "Skill Routing" in skill
    assert "Reuse Upgrade Gate" in skill
    assert "Completion Gate" in skill


def test_standard_contract_requires_automatic_preference_activation() -> None:
    skill = read_text("skills/commander-mode/SKILL.md")

    assert ".codex/docs/协作偏好.md" in skill
    assert "select 3-7 relevant preference cards" in skill
    assert "Do not summarize the whole file unless the user asks" in skill


def test_skill_routing_audits_discovery_failures() -> None:
    skill = read_text("skills/commander-mode/SKILL.md")

    assert "discovery failure" in skill
    assert "restart/install" in skill
    assert "Chinese synonyms" in skill
    assert "broader skill is shadowing" in skill


def test_commander_routes_skill_self_debug_to_failure_and_writing_skills() -> None:
    skill = read_text("skills/commander-mode/SKILL.md")

    assert "debugging commander mode itself" in skill
    assert "identify-skill-failure plus superpowers:writing-skills" in skill
    assert "skill-trigger-matrix.md" in skill


def test_commander_distinguishes_loaded_skill_failure_from_discovery_failure() -> None:
    skill = read_text("skills/commander-mode/SKILL.md")

    assert "Use `identify-skill-failure` only when the skill was loaded" in skill
    assert "For missed triggers or unloaded skills, use the Discovery Failure Gate" in skill
    assert "do not classify unloaded-skill discovery misses as loaded-skill violations" in skill


def test_reuse_upgrade_gate_routes_to_lightest_layer() -> None:
    skill = read_text("skills/commander-mode/SKILL.md")

    assert "Do not wait for the user to say" in skill
    assert "Project markdown" in skill
    assert "Script, test, or checker" in skill
    assert "skill-document TDD" in skill


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
