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


def test_creates_preference_file_with_stable_card(tmp_path: Path) -> None:
    sync = load_module(
        "skills/commander-mode/scripts/sync_preference_memory.py",
        "sync_preference_memory_create",
    )
    repo = tmp_path / "repo"
    repo.mkdir()

    result = sync.sync_preference_memory(
        repo_root=repo,
        memory_id="pref-token-roi",
        status="stable",
        scope="global",
        triggers=["planning", "context_recovery"],
        rule="token 使用目标是高价值，不是单纯低消耗。",
        do_items=["读取能改变决策的真相源"],
        dont_items=["机械读取所有模板"],
        evidence_items=["2026-04-28 用户明确纠正 token 目标"],
    )

    target = repo / ".codex" / "docs" / "协作偏好.md"
    text = target.read_text(encoding="utf-8")
    assert result.updated is True
    assert result.section == "Stable Preferences"
    assert "## Stable Preferences" in text
    assert "### pref-token-roi" in text
    assert "status: stable" in text
    assert "scope: global" in text
    assert "- planning" in text
    assert "rule: token 使用目标是高价值，不是单纯低消耗。" in text
    assert "- 读取能改变决策的真相源" in text
    assert "- 机械读取所有模板" in text
    assert "- 2026-04-28 用户明确纠正 token 目标" in text


def test_writes_candidate_card_under_candidate_section(tmp_path: Path) -> None:
    sync = load_module(
        "skills/commander-mode/scripts/sync_preference_memory.py",
        "sync_preference_memory_candidate",
    )
    repo = tmp_path / "repo"
    repo.mkdir()

    result = sync.sync_preference_memory(
        repo_root=repo,
        memory_id="pref-auto-capture",
        status="candidate",
        scope="project",
        triggers=["correction"],
        rule="用户纠正方向时判断是否沉淀为偏好。",
        do_items=["写入候选偏好"],
        dont_items=["直接写成长篇聊天总结"],
        evidence_items=["用户要求不要每次重复说明习惯"],
    )

    text = (repo / ".codex" / "docs" / "协作偏好.md").read_text(encoding="utf-8")
    candidate_start = text.index("## Candidate Preferences")
    card_start = text.index("### pref-auto-capture")
    assert result.section == "Candidate Preferences"
    assert candidate_start < card_start
    assert "status: candidate" in text
    assert "scope: project" in text


def test_upserts_existing_card_by_id(tmp_path: Path) -> None:
    sync = load_module(
        "skills/commander-mode/scripts/sync_preference_memory.py",
        "sync_preference_memory_upsert",
    )
    repo = tmp_path / "repo"
    repo.mkdir()

    sync.sync_preference_memory(
        repo_root=repo,
        memory_id="pref-verify",
        status="candidate",
        scope="project",
        triggers=["completion"],
        rule="旧规则",
        do_items=["旧动作"],
        dont_items=["旧禁忌"],
        evidence_items=["旧证据"],
    )
    result = sync.sync_preference_memory(
        repo_root=repo,
        memory_id="pref-verify",
        status="stable",
        scope="global",
        triggers=["completion", "validation"],
        rule="下结论前必须绑定新鲜验证证据。",
        do_items=["运行相关测试或 stop gate"],
        dont_items=["使用基本好了代替证据"],
        evidence_items=["用户多次要求验证后再下结论"],
    )

    text = (repo / ".codex" / "docs" / "协作偏好.md").read_text(encoding="utf-8")
    assert result.action == "replaced"
    assert text.count("### pref-verify") == 1
    assert "status: stable" in text
    assert "旧规则" not in text
    assert "下结论前必须绑定新鲜验证证据。" in text


def test_preference_memory_cli_emits_utf8_json(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "skills" / "commander-mode" / "scripts" / "sync_preference_memory.py"
    repo = tmp_path / "repo"
    repo.mkdir()

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--repo",
            str(repo),
            "--id",
            "pref-checkpoint",
            "--status",
            "stable",
            "--scope",
            "global",
            "--trigger",
            "long_task",
            "--rule",
            "长任务中断前必须写检查点。",
            "--do",
            "写入当前目标和下一步",
            "--dont",
            "只在最后总结",
            "--evidence",
            "用户要求中断后不能回到开始前",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["updated"] is True
    assert payload["memory_id"] == "pref-checkpoint"
    assert "协作偏好.md" in payload["target"]
