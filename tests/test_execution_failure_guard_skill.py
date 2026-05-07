from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def read_skill(relative_path: str) -> str:
    return (repo_root() / relative_path).read_text(encoding="utf-8")


def test_execution_failure_guard_is_discoverable_and_generic() -> None:
    skill = read_skill("skills/execution-failure-guard/SKILL.md")

    assert "name: execution-failure-guard" in skill
    assert "description: Use when a command, tool call" in skill
    assert "Windows" in skill
    assert "D:\\Develop" not in skill
    assert "C:\\Users\\26877" not in skill


def test_execution_failure_guard_requires_learned_fix_reuse() -> None:
    skill = read_skill("skills/execution-failure-guard/SKILL.md")

    assert "Preflight Check" in skill
    assert "known_failures.py --repo . check" in skill
    assert ".codex/known-failures.json" in skill
    assert "do not run the known-bad command" in skill
    assert "Read the JSON `matched` field" in skill
    assert "Learned Fix Gate" in skill
    assert "Capture the known-bad method" in skill
    assert "Capture the working method as a reusable command shape" in skill
    assert "Use the working method for the rest of the session" in skill
    assert "choose the narrowest durable surface" in skill
    assert "upgrade the durable surface instead of adding another note" in skill


def test_execution_failure_guard_records_known_bad_methods_when_retriable() -> None:
    skill = read_skill("skills/execution-failure-guard/SKILL.md")

    assert "Known-Bad Method Gate" in skill
    assert "when a reasonable future agent might choose it again" in skill
    assert '"known_bad"' in skill
    assert '"fails_because"' in skill
    assert '"use_instead"' in skill
    assert '"scope"' in skill
    assert "Saving only the working method" in skill


def test_execution_failure_guard_bundles_known_failures_script() -> None:
    script = repo_root() / "skills" / "execution-failure-guard" / "scripts" / "known_failures.py"

    assert script.exists()


def test_execution_failure_guard_defers_durable_layer_to_reuse_upgrader() -> None:
    skill = read_skill("skills/execution-failure-guard/SKILL.md")

    assert "This skill does not decide the final durable layer" in skill
    assert "Use `commander-reuse-upgrader` for that decision" in skill
    assert "This skill owns immediate reuse" in skill
    assert "`commander-reuse-upgrader` owns whether" in skill


def test_execution_failure_guard_blocks_repeating_known_bad_commands() -> None:
    skill = read_skill("skills/execution-failure-guard/SKILL.md")

    assert "Before Repeating A Similar Operation" in skill
    assert "start from that method" in skill
    assert "Do not repeat the original failing command" in skill


def test_commander_routes_repeated_execution_failures() -> None:
    commander = read_skill("skills/commander-mode/SKILL.md")

    assert "execution-failure-guard" in commander
    assert "working replacement was found" in commander
    assert ".codex/known-failures.json" in commander
    assert "known_failures.py" in commander
    assert "then `commander-reuse-upgrader`" in commander


def test_readme_documents_known_failures_checker() -> None:
    readme = read_skill("README.md")

    assert ".codex/known-failures.json" in readme
    assert "known_failures.py --repo . add" in readme
    assert "known_failures.py --repo . check" in readme
