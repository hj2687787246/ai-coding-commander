import importlib.util
import json
import subprocess
import sys
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_module():
    target = repo_root() / "skills" / "commander-mode" / "scripts" / "commander_activation.py"
    spec = importlib.util.spec_from_file_location("commander_activation", target)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_status_is_inactive_when_marker_is_missing(tmp_path: Path) -> None:
    activation = load_module()

    result = activation.status(tmp_path)

    assert result["active"] is False
    assert result["marker_exists"] is False
    assert result["marker_path"].endswith(".codex/commander-active.json")


def test_activate_creates_project_marker(tmp_path: Path) -> None:
    activation = load_module()

    result = activation.activate(tmp_path, source="test", note="manual commander start")

    marker = tmp_path / ".codex" / "commander-active.json"
    payload = json.loads(marker.read_text(encoding="utf-8"))
    assert result["active"] is True
    assert result["marker_exists"] is True
    assert payload["schema_version"] == 1
    assert payload["active"] is True
    assert payload["scope"] == "repo"
    assert payload["activated_by"] == "test"
    assert payload["activation_note"] == "manual commander start"
    assert payload["activated_at"]


def test_deactivate_preserves_marker_but_turns_off_recovery(tmp_path: Path) -> None:
    activation = load_module()
    activation.activate(tmp_path, source="test")

    result = activation.deactivate(tmp_path, source="test", note="done")

    payload = json.loads((tmp_path / ".codex" / "commander-active.json").read_text(encoding="utf-8"))
    assert result["active"] is False
    assert result["marker_exists"] is True
    assert payload["active"] is False
    assert payload["deactivated_by"] == "test"
    assert payload["deactivation_note"] == "done"
    assert payload["deactivated_at"]


def test_cli_activate_and_status_emit_json(tmp_path: Path) -> None:
    script = repo_root() / "skills" / "commander-mode" / "scripts" / "commander_activation.py"

    activate_result = subprocess.run(
        [sys.executable, str(script), "--repo", str(tmp_path), "activate", "--source", "cli-test"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    status_result = subprocess.run(
        [sys.executable, str(script), "--repo", str(tmp_path), "status"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert activate_result.returncode == 0
    assert status_result.returncode == 0
    assert json.loads(activate_result.stdout)["active"] is True
    assert json.loads(status_result.stdout)["active"] is True


def test_commander_docs_reference_persistent_activation_marker() -> None:
    skill = (repo_root() / "skills" / "commander-mode" / "SKILL.md").read_text(encoding="utf-8")
    readme = (repo_root() / "README.md").read_text(encoding="utf-8")
    template_agent = (
        repo_root() / "skills" / "commander-mode" / "references" / "templates" / "project-codex-standard" / "AGENTS.md"
    ).read_text(encoding="utf-8")

    assert ".codex/commander-active.json" in skill
    assert "commander_activation.py" in skill
    assert ".codex/commander-active.json" in readme
    assert "commander_activation.py" in readme
    assert ".codex/commander-active.json" in template_agent


def test_activation_marker_is_local_runtime_state() -> None:
    gitignore = (repo_root() / ".gitignore").read_text(encoding="utf-8")

    assert ".codex/commander-active.json" in gitignore
