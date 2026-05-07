from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def read_reuse_skill() -> str:
    return (repo_root() / "skills" / "commander-reuse-upgrader" / "SKILL.md").read_text(encoding="utf-8")


def test_reuse_upgrader_is_generic_and_discoverable() -> None:
    skill = read_reuse_skill()

    assert "description: Use when" in skill
    assert "Agent workspace" not in skill
    assert "D:\\Develop" not in skill
    assert "active workspace truth sources" in skill


def test_reuse_upgrader_routes_to_lightest_reuse_layer() -> None:
    skill = read_reuse_skill()

    assert "project markdown" in skill
    assert "script, test, checker" in skill
    assert "Use a skill only when" in skill
    assert "repeated" in skill
    assert "stable" in skill
    assert "Validation evidence" in skill


def test_reuse_upgrader_proactively_captures_reuse_value() -> None:
    skill = read_reuse_skill()

    assert "This workflow is proactive" in skill
    assert "Do not wait for the user to request reuse" in skill
    assert "Auto Capture Gate" in skill
    assert "Never make the user responsible" in skill


def test_reuse_upgrader_requires_skill_document_tdd() -> None:
    skill = read_reuse_skill()

    assert "skill-document TDD" in skill
    assert "Capture the failing behavior" in skill
    assert "pressure scenario" in skill
    assert "Discovery Failure Gate" in skill
