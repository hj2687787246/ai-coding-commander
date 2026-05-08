from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def read_text(relative_path: str) -> str:
    return (repo_root() / relative_path).read_text(encoding="utf-8")


def test_doc_reviewer_mode_skill_exists_with_clear_boundary() -> None:
    skill = read_text("skills/doc-reviewer-mode/SKILL.md")

    assert "name: doc-reviewer-mode" in skill
    assert "description: Use when" in skill
    assert "文档评审官" in skill
    assert "Doc Reviewer" in skill
    assert "Do not edit implementation code" in skill
    assert "Do not change requirements" in skill
    assert "文档评审官回报" in skill


def test_doc_reviewer_mode_reviews_contract_before_execution() -> None:
    skill = read_text("skills/doc-reviewer-mode/SKILL.md")

    assert "Requirement Contract Review" in skill
    assert "Objective" in skill
    assert "Scope" in skill
    assert "Non-goals" in skill
    assert "Final acceptance" in skill
    assert "ready for executor" in skill
    assert "return to commander" in skill


def test_acceptance_reviewer_mode_skill_exists_with_clear_boundary() -> None:
    skill = read_text("skills/acceptance-reviewer-mode/SKILL.md")

    assert "name: acceptance-reviewer-mode" in skill
    assert "description: Use when" in skill
    assert "验收官" in skill
    assert "Acceptance Reviewer" in skill
    assert "Do not implement fixes" in skill
    assert "Do not broaden acceptance criteria" in skill
    assert "验收官回报" in skill


def test_acceptance_reviewer_mode_requires_evidence_before_pass() -> None:
    skill = read_text("skills/acceptance-reviewer-mode/SKILL.md")

    assert "Acceptance Evidence Review" in skill
    assert "requirement contract" in skill
    assert "validation evidence" in skill
    assert "Pass" in skill
    assert "Fail" in skill
    assert "residual risk" in skill
    assert "return to commander" in skill


def test_commander_routes_all_four_roles() -> None:
    commander = read_text("skills/commander-mode/SKILL.md")
    matrix = read_text("docs/skill-trigger-matrix.md")
    readme = read_text("README.md")

    for skill_name in (
        "commander-mode",
        "doc-reviewer-mode",
        "executor-mode",
        "acceptance-reviewer-mode",
    ):
        assert skill_name in commander
        assert skill_name in matrix
        assert skill_name in readme

    assert "Role Dispatch Packet" in commander
    assert "required skill:" in commander
    assert "Do not dispatch role work without naming the required skill" in commander
    assert "Doc Reviewer" in commander
    assert "Executor" in commander
    assert "Acceptance Reviewer" in commander
