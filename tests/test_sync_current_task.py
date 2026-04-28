import importlib.util
import json
import subprocess
import sys
from pathlib import Path


def load_module(relative_path: str, module_name: str):
    repo_root = Path(__file__).resolve().parents[1]
    target = repo_root / relative_path
    spec = importlib.util.spec_from_file_location(module_name, target)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def make_bootstrapped_repo(tmp_path: Path) -> Path:
    bootstrap = load_module(
        "skills/commander-mode/scripts/bootstrap_codex_workspace.py",
        "bootstrap_for_sync_tests",
    )
    repo = tmp_path / "repo"
    repo.mkdir()
    bootstrap.bootstrap_workspace(repo)
    return repo


def test_start_event_updates_progress_and_next_step(tmp_path: Path) -> None:
    sync = load_module(
        "skills/commander-mode/scripts/sync_current_task.py",
        "sync_current_task_start",
    )
    repo = make_bootstrapped_repo(tmp_path)

    result = sync.sync_current_task(
        repo_root=repo,
        event="start",
        progress="进行中：开始实现当前任务同步器",
        next_step="编写 start 事件实现",
    )

    current_task = (repo / ".codex" / "docs" / "当前任务.md").read_text(encoding="utf-8")
    assert result.updated is True
    assert "当前进度：进行中：开始实现当前任务同步器" in current_task
    assert "下一步：编写 start 事件实现" in current_task


def test_phase_event_updates_progress_blocker_and_next_step(tmp_path: Path) -> None:
    sync = load_module(
        "skills/commander-mode/scripts/sync_current_task.py",
        "sync_current_task_phase",
    )
    repo = make_bootstrapped_repo(tmp_path)

    result = sync.sync_current_task(
        repo_root=repo,
        event="phase",
        progress="阶段二：补 CLI 和 JSON 输出",
        blocker="需要确认字段替换策略",
        next_step="实现字段前缀扫描",
    )

    current_task = (repo / ".codex" / "docs" / "当前任务.md").read_text(encoding="utf-8")
    assert result.updated is True
    assert "当前进度：阶段二：补 CLI 和 JSON 输出" in current_task
    assert "当前卡点：需要确认字段替换策略" in current_task
    assert "下一步：实现字段前缀扫描" in current_task


def test_validate_event_updates_validation_fields(tmp_path: Path) -> None:
    sync = load_module(
        "skills/commander-mode/scripts/sync_current_task.py",
        "sync_current_task_validate",
    )
    repo = make_bootstrapped_repo(tmp_path)

    result = sync.sync_current_task(
        repo_root=repo,
        event="validate",
        validation_status="已验证",
        validation_evidence="python -m pytest tests/test_sync_current_task.py -q",
        last_validation="2026-04-18 pytest 通过",
    )

    current_task = (repo / ".codex" / "docs" / "当前任务.md").read_text(encoding="utf-8")
    assert result.updated is True
    assert "验证状态：已验证" in current_task
    assert "验证证据：python -m pytest tests/test_sync_current_task.py -q" in current_task
    assert "最近验证：2026-04-18 pytest 通过" in current_task


def test_preclose_event_can_refresh_progress_validation_and_next_step(tmp_path: Path) -> None:
    sync = load_module(
        "skills/commander-mode/scripts/sync_current_task.py",
        "sync_current_task_preclose",
    )
    repo = make_bootstrapped_repo(tmp_path)

    result = sync.sync_current_task(
        repo_root=repo,
        event="preclose",
        progress="待收口",
        validation_status="已验证",
        validation_evidence="portable stop-gate passed",
        next_step="准备收口并更新验收记录",
    )

    current_task = (repo / ".codex" / "docs" / "当前任务.md").read_text(encoding="utf-8")
    assert result.updated is True
    assert "当前进度：待收口" in current_task
    assert "验证状态：已验证" in current_task
    assert "验证证据：portable stop-gate passed" in current_task
    assert "下一步：准备收口并更新验收记录" in current_task


def test_sync_fails_clearly_when_current_task_file_is_missing(tmp_path: Path) -> None:
    sync = load_module(
        "skills/commander-mode/scripts/sync_current_task.py",
        "sync_current_task_missing_file",
    )
    repo = tmp_path / "repo"
    repo.mkdir()

    result = sync.main(
        [
            "--repo",
            str(repo),
            "--event",
            "start",
            "--progress",
            "进行中",
        ]
    )

    assert result == 1


def test_sync_script_can_run_as_cli_and_emit_utf8_json(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "skills" / "commander-mode" / "scripts" / "sync_current_task.py"
    repo = make_bootstrapped_repo(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--repo",
            str(repo),
            "--event",
            "validate",
            "--validation-status",
            "已验证",
            "--validation-evidence",
            "pytest passed",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["updated"] is True
    assert "验证状态" in payload["changed_fields"]


def test_commander_docs_reference_current_task_sync_script() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    skill = (repo_root / "skills" / "commander-mode" / "SKILL.md").read_text(encoding="utf-8")
    readme = (repo_root / "README.md").read_text(encoding="utf-8")

    assert "sync_current_task.py" in skill
    assert "sync_current_task.py" in readme


def test_checkpoint_event_updates_recovery_fields_without_appending_history(tmp_path: Path) -> None:
    sync = load_module(
        "skills/commander-mode/scripts/sync_current_task.py",
        "sync_current_task_checkpoint",
    )
    repo = make_bootstrapped_repo(tmp_path)

    result = sync.sync_current_task(
        repo_root=repo,
        event="checkpoint",
        progress="已完成 skill 定位重写",
        blocker="无",
        focus_files="skills/commander-mode/SKILL.md, README.md",
        next_step="更新 README 并运行文档测试",
        validation_status="检查点",
        validation_evidence="pytest docs contract pending",
        last_validation="2026-04-28 checkpoint written",
    )

    current_task = (repo / ".codex" / "docs" / "当前任务.md").read_text(encoding="utf-8")
    assert result.updated is True
    assert "当前进度：已完成 skill 定位重写" in current_task
    assert "当前卡点：无" in current_task
    assert "正在关注的文件：skills/commander-mode/SKILL.md, README.md" in current_task
    assert "下一步：更新 README 并运行文档测试" in current_task
    assert "验证状态：检查点" in current_task
    assert "验证证据：pytest docs contract pending" in current_task
    assert "最近验证：2026-04-28 checkpoint written" in current_task
    assert current_task.count("当前进度：") == 1


def test_checkpoint_cli_accepts_focus_files(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "skills" / "commander-mode" / "scripts" / "sync_current_task.py"
    repo = make_bootstrapped_repo(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--repo",
            str(repo),
            "--event",
            "checkpoint",
            "--progress",
            "进行中：写 README",
            "--focus-files",
            "README.md",
            "--next-step",
            "运行 pytest",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["updated"] is True
    assert "正在关注的文件" in payload["changed_fields"]
