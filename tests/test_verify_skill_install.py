import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_module():
    target = repo_root() / "skills" / "commander-mode" / "scripts" / "verify_skill_install.py"
    spec = importlib.util.spec_from_file_location("verify_skill_install", target)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def copy_required_skills(target_home: Path) -> None:
    source_root = repo_root() / "skills"
    target_root = target_home / "skills"
    target_root.mkdir(parents=True)
    for skill_name in ("commander-mode", "commander-reuse-upgrader", "execution-failure-guard"):
        shutil.copytree(source_root / skill_name, target_root / skill_name)


def test_verify_skill_install_passes_when_required_skills_match(tmp_path: Path) -> None:
    verifier = load_module()
    copy_required_skills(tmp_path)

    result = verifier.verify_install(repo_root(), tmp_path)

    assert result["ok"] is True
    assert {skill["name"] for skill in result["skills"]} == {
        "commander-mode",
        "commander-reuse-upgrader",
        "execution-failure-guard",
    }
    assert all(skill["content_matches"] for skill in result["skills"])
    assert all(skill["files_match"] for skill in result["skills"])


def test_verify_skill_install_fails_when_installed_copy_is_stale(tmp_path: Path) -> None:
    verifier = load_module()
    copy_required_skills(tmp_path)
    stale_skill = tmp_path / "skills" / "execution-failure-guard" / "SKILL.md"
    stale_skill.write_text(stale_skill.read_text(encoding="utf-8") + "\n# stale\n", encoding="utf-8")

    result = verifier.verify_install(repo_root(), tmp_path)

    assert result["ok"] is False
    stale = next(skill for skill in result["skills"] if skill["name"] == "execution-failure-guard")
    assert stale["content_matches"] is False
    assert stale["files_match"] is False
    assert stale["changed_files"] == ["SKILL.md"]


def test_verify_skill_install_fails_when_bundled_script_is_stale(tmp_path: Path) -> None:
    verifier = load_module()
    copy_required_skills(tmp_path)
    stale_script = tmp_path / "skills" / "execution-failure-guard" / "scripts" / "known_failures.py"
    stale_script.write_text(stale_script.read_text(encoding="utf-8") + "\n# stale\n", encoding="utf-8")

    result = verifier.verify_install(repo_root(), tmp_path)

    assert result["ok"] is False
    stale = next(skill for skill in result["skills"] if skill["name"] == "execution-failure-guard")
    assert stale["content_matches"] is True
    assert stale["files_match"] is False
    assert stale["changed_files"] == ["scripts/known_failures.py"]


def test_verify_skill_install_cli_emits_json_and_exit_code(tmp_path: Path) -> None:
    copy_required_skills(tmp_path)
    script = repo_root() / "skills" / "commander-mode" / "scripts" / "verify_skill_install.py"

    result = subprocess.run(
        [sys.executable, str(script), "--repo", str(repo_root()), "--codex-home", str(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True


def test_commander_docs_reference_skill_install_verifier() -> None:
    commander = (repo_root() / "skills" / "commander-mode" / "SKILL.md").read_text(encoding="utf-8")
    readme = (repo_root() / "README.md").read_text(encoding="utf-8")

    assert "verify_skill_install.py" in commander
    assert "verify_skill_install.py" in readme
