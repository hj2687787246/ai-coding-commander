from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def read_text(relative_path: str) -> str:
    return (repo_root() / relative_path).read_text(encoding="utf-8")


def parse_matrix_rows() -> list[dict[str, str]]:
    doc = read_text("docs/skill-trigger-matrix.md")
    rows: list[dict[str, str]] = []
    for line in doc.splitlines():
        if not line.startswith("| "):
            continue
        if line.startswith("| ID ") or line.startswith("| ---"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 4:
            continue
        rows.append(
            {
                "id": cells[0],
                "wording": cells[1].strip("`"),
                "skill": cells[2].strip("`"),
                "why": cells[3],
            }
        )
    return rows


def available_skill_names() -> set[str]:
    names: set[str] = set()
    for skill_path in (repo_root() / "skills").glob("*/SKILL.md"):
        text = skill_path.read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.startswith("name:"):
                names.add(line.split(":", 1)[1].strip())
                break

    docs = read_text("docs/external-skills.md")
    for line in docs.splitlines():
        if line.startswith("| `"):
            names.add(line.split("`", 2)[1])

    names.update(
        {
            "canvas-design",
            "clarify-requirements",
            "docx",
            "mcp-builder",
            "mysql-connect",
            "pdf",
            "pptx",
            "ps-utf8-io",
            "redis-read",
            "theme-factory",
            "webapp-testing",
            "xlsx",
            "superpowers:brainstorming",
            "superpowers:systematic-debugging",
            "superpowers:test-driven-development",
            "superpowers:verification-before-completion",
            "superpowers:writing-plans",
        }
    )
    return names


def test_trigger_matrix_has_unique_ids_and_expected_skills_exist() -> None:
    rows = parse_matrix_rows()

    assert len(rows) >= 25
    ids = [row["id"] for row in rows]
    assert len(ids) == len(set(ids))

    known_skills = available_skill_names()
    missing = sorted({row["skill"] for row in rows} - known_skills)
    assert missing == []


def test_trigger_matrix_covers_commander_reuse_and_skill_maintenance() -> None:
    rows = parse_matrix_rows()
    skills = {row["skill"] for row in rows}

    assert "commander-mode" in skills
    assert "commander-reuse-upgrader" in skills
    assert "identify-skill-failure" in skills
    assert "compress-skill" in skills
    assert "modulize-skill" in skills

    reuse_rows = [row for row in rows if row["skill"] == "commander-reuse-upgrader"]
    assert len(reuse_rows) >= 3
    assert any("沉淀" in row["wording"] for row in reuse_rows)
    assert any("文档" in row["wording"] and "脚本" in row["wording"] for row in reuse_rows)


def test_commander_mentions_trigger_discovery_failure_matrix_concepts() -> None:
    commander = read_text("skills/commander-mode/SKILL.md")
    matrix = read_text("docs/skill-trigger-matrix.md")

    assert "discovery failure" in commander
    assert "Chinese synonyms" in commander
    assert "broader skill is shadowing" in commander
    assert "real user wording fails to trigger" in matrix
    assert "fix commander routing or the narrower skill description" in matrix
