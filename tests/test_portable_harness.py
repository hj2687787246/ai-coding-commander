import importlib.util
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace


def load_portable_harness():
    repo_root = Path(__file__).resolve().parents[1]
    target = repo_root / "skills" / "commander-mode" / "scripts" / "portable_harness.py"
    spec = importlib.util.spec_from_file_location("portable_harness", target)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True, text=True)


def test_status_reports_codex_initialized_when_project_has_agent_file(tmp_path: Path) -> None:
    harness = load_portable_harness()
    repo = tmp_path / "repo"
    repo.mkdir()
    init_git_repo(repo)
    (repo / ".codex").mkdir()
    (repo / ".codex" / "AGENT.md").write_text("# project rules\n", encoding="utf-8")

    status = harness.build_status(repo)

    assert status["commander_protocol"]["initialized"] is True
    assert ".codex/AGENT.md" in status["commander_protocol"]["markers"]


def test_status_reports_codex_uninitialized_without_protocol_markers(tmp_path: Path) -> None:
    harness = load_portable_harness()
    repo = tmp_path / "repo"
    repo.mkdir()
    init_git_repo(repo)

    status = harness.build_status(repo)

    assert status["commander_protocol"]["initialized"] is False
    assert status["commander_protocol"]["markers"] == []


def test_status_does_not_treat_agents_reference_without_codex_file_as_initialized(tmp_path: Path) -> None:
    harness = load_portable_harness()
    repo = tmp_path / "repo"
    repo.mkdir()
    init_git_repo(repo)
    (repo / "AGENTS.md").write_text("First jump: .codex/AGENT.md\n", encoding="utf-8")

    status = harness.build_status(repo)

    assert status["commander_protocol"]["initialized"] is False
    assert status["commander_protocol"]["markers"] == []


def test_main_reconfigures_stdout_to_utf8(monkeypatch) -> None:
    harness = load_portable_harness()
    captured: dict[str, str] = {}

    def fake_reconfigure(*, encoding: str) -> None:
        captured["encoding"] = encoding

    fake_stdout = SimpleNamespace(reconfigure=fake_reconfigure, write=lambda _: None, flush=lambda: None)
    monkeypatch.setattr(harness.sys, "stdout", fake_stdout)

    exit_code = harness.main(["--cwd", ".", "status"])

    assert exit_code in (0, 1)
    assert captured["encoding"].lower() == "utf-8"
