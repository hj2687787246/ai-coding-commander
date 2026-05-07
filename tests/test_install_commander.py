import subprocess
import shutil
from pathlib import Path

import pytest


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def install_script() -> Path:
    return repo_root() / "install" / "install-commander.ps1"


def run_install(target_home: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    pwsh = shutil.which("pwsh")
    if pwsh is None:
        pytest.skip("pwsh is not available on PATH")
    return subprocess.run(
        [
            pwsh,
            "-NoLogo",
            "-File",
            str(install_script()),
            "-CodexHome",
            str(target_home),
            *extra,
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_install_script_copies_commander_mode_into_codex_home(tmp_path: Path) -> None:
    result = run_install(tmp_path)

    assert result.returncode == 0
    installed_skill = tmp_path / "skills" / "commander-mode" / "SKILL.md"
    installed_reuse_skill = tmp_path / "skills" / "commander-reuse-upgrader" / "SKILL.md"
    assert installed_skill.exists()
    assert installed_reuse_skill.exists()
    assert "installed" in result.stdout


def test_install_script_does_not_overwrite_existing_target_without_force(tmp_path: Path) -> None:
    target = tmp_path / "skills" / "commander-mode"
    target.mkdir(parents=True)
    (target / "marker.txt").write_text("keep", encoding="utf-8")

    result = run_install(tmp_path)

    assert result.returncode != 0
    assert (target / "marker.txt").read_text(encoding="utf-8") == "keep"


def test_install_script_can_backup_existing_target(tmp_path: Path) -> None:
    target = tmp_path / "skills" / "commander-mode"
    target.mkdir(parents=True)
    (target / "marker.txt").write_text("old", encoding="utf-8")

    result = run_install(tmp_path, "-BackupExisting")

    assert result.returncode == 0
    backups = list((tmp_path / "skills").glob("commander-mode.backup-*"))
    assert backups
    assert (backups[0] / "marker.txt").read_text(encoding="utf-8") == "old"
    assert (tmp_path / "skills" / "commander-mode" / "SKILL.md").exists()


def test_install_script_uses_copy_install_not_junction(tmp_path: Path) -> None:
    result = run_install(tmp_path)

    assert result.returncode == 0
    target = tmp_path / "skills" / "commander-mode"
    reuse_target = tmp_path / "skills" / "commander-reuse-upgrader"
    assert target.exists()
    assert reuse_target.exists()
    assert not target.is_symlink()
    assert not reuse_target.is_symlink()


def test_readme_documents_developer_and_regular_user_install_paths() -> None:
    readme = (repo_root() / "README.md").read_text(encoding="utf-8-sig")

    assert "install/install-commander.ps1" in readme
    assert "开发者" in readme
    assert "普通用户" in readme
    assert "skills/commander-mode/" in readme
    assert "skills/commander-reuse-upgrader/" in readme
    assert "legacy/agent-runtime" in readme
