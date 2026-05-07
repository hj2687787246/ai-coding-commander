import importlib.util
import json
import subprocess
import sys
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_module():
    target = repo_root() / "skills" / "execution-failure-guard" / "scripts" / "known_failures.py"
    spec = importlib.util.spec_from_file_location("known_failures", target)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_known_failures_adds_and_matches_known_bad_command(tmp_path: Path) -> None:
    known_failures = load_module()

    known_failures.add_record(
        repo_root=tmp_path,
        record_id="pwsh-path",
        match="pwsh -NoLogo",
        known_bad="pwsh -NoLogo -Command ...",
        fails_because="pwsh is not always on the current tool process PATH",
        use_instead="$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User'); pwsh -NoLogo -Command ...",
        scope="Windows tool process",
        last_verified="2026-05-07",
    )

    result = known_failures.check_command(tmp_path, "pwsh -NoLogo -Command Get-Date")

    assert result.matched is True
    assert result.record is not None
    assert result.record["known_bad"] == "pwsh -NoLogo -Command ..."
    assert "GetEnvironmentVariable" in result.record["use_instead"]


def test_known_failures_ignores_expired_records_by_default(tmp_path: Path) -> None:
    known_failures = load_module()

    known_failures.add_record(
        repo_root=tmp_path,
        record_id="old-fix",
        match="old-tool",
        known_bad="old-tool run",
        fails_because="old environment only",
        use_instead="new-tool run",
        scope="temporary",
        expires_at="2000-01-01",
    )

    result = known_failures.check_command(tmp_path, "old-tool run")

    assert result.matched is False


def test_known_failures_cli_returns_use_instead_on_match(tmp_path: Path) -> None:
    script = repo_root() / "skills" / "execution-failure-guard" / "scripts" / "known_failures.py"

    add_result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--repo",
            str(tmp_path),
            "add",
            "--id",
            "quoted-regex",
            "--match",
            "rg -n a|b",
            "--known-bad",
            "rg -n a|b path",
            "--fails-because",
            "PowerShell treats unquoted | as a pipeline",
            "--use-instead",
            "rg -n 'a|b' path",
            "--scope",
            "PowerShell command arguments",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert add_result.returncode == 0

    check_result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--repo",
            str(tmp_path),
            "check",
            "--command",
            "rg -n a|b path",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert check_result.returncode == 0
    payload = json.loads(check_result.stdout)
    assert payload["matched"] is True
    assert payload["use_instead"] == "rg -n 'a|b' path"
