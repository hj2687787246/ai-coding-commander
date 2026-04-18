# Current Task Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 `commander-mode` 增加一个轻量的 `sync_current_task.py`，在长任务执行的关键节点按事件同步 `.codex/docs/当前任务.md`。

**Architecture:** 保持现有 `.codex` 单主协议不变，只新增一个事件驱动脚本和一组回归测试。脚本按固定字段前缀更新 `当前任务.md`，输出 UTF-8 JSON，不引入 daemon、任务图或第二套任务协议。

**Tech Stack:** Python 3、argparse、json、pathlib、pytest、UTF-8 文本读写

---

## 文件结构

### 新增

- `skills/commander-mode/scripts/sync_current_task.py`
  - 当前任务同步器；接收事件和可选字段输入，按字段更新 `.codex/docs/当前任务.md`
- `tests/test_sync_current_task.py`
  - 同步器的单元测试与 CLI 回归

### 修改

- `skills/commander-mode/SKILL.md`
  - 补充推荐调用时机与最小命令示例
- `README.md`
  - 在首次使用或长任务治理部分补同步器入口

### 参考但不改

- `skills/commander-mode/references/templates/project-codex-standard/.codex/docs/当前任务.md`
  - 作为字段格式来源
- `skills/commander-mode/scripts/bootstrap_codex_workspace.py`
  - 仅用于测试里快速生成标准 `.codex` 骨架

## Task 1: 先用测试钉住同步器行为

**Files:**
- Create: `tests/test_sync_current_task.py`
- Test: `tests/test_sync_current_task.py`
- Reference: `skills/commander-mode/scripts/bootstrap_codex_workspace.py`

- [ ] **Step 1: 写测试文件骨架和模块加载辅助**

```python
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
```

- [ ] **Step 2: 复用 bootstrap 快速创建标准 `.codex` 骨架**

```python
def make_bootstrapped_repo(tmp_path: Path) -> Path:
    bootstrap = load_module(
        "skills/commander-mode/scripts/bootstrap_codex_workspace.py",
        "bootstrap_for_sync_tests",
    )
    repo = tmp_path / "repo"
    repo.mkdir()
    bootstrap.bootstrap_workspace(repo)
    return repo
```

- [ ] **Step 3: 写 `start` 事件的失败测试**

```python
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
```

- [ ] **Step 4: 写 `phase` / `validate` / `preclose` 的失败测试**

```python
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
```

- [ ] **Step 5: 写“缺文件报错”和 CLI JSON 输出的失败测试**

```python
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
```

- [ ] **Step 6: 先运行测试，确认它们现在失败**

Run:

```powershell
pwsh -NoLogo -Command "python -m pytest tests/test_sync_current_task.py -q"
```

Expected:

- FAIL
- 报 `sync_current_task.py` 不存在或函数未定义

- [ ] **Step 7: Commit**

```bash
git add tests/test_sync_current_task.py
git commit -m "test: add current task sync coverage"
```

## Task 2: 实现同步器核心逻辑

**Files:**
- Create: `skills/commander-mode/scripts/sync_current_task.py`
- Test: `tests/test_sync_current_task.py`

- [ ] **Step 1: 建立脚本骨架、结果类型和固定字段映射**

```python
"""Synchronize `.codex/docs/当前任务.md` during long-running work."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path


FIELD_PREFIXES = {
    "progress": "当前进度：",
    "blocker": "当前卡点：",
    "validation_status": "验证状态：",
    "validation_evidence": "验证证据：",
    "next_step": "下一步：",
    "last_validation": "最近验证：",
}


@dataclass(frozen=True)
class SyncResult:
    updated: bool
    target: str
    changed_fields: list[str]
```

- [ ] **Step 2: 实现目标文件定位和文本读取**

```python
def resolve_current_task(repo_root: Path) -> Path:
    return repo_root.resolve() / ".codex" / "docs" / "当前任务.md"


def read_current_task(target: Path) -> list[str]:
    if not target.exists():
        raise FileNotFoundError(f"Current task file not found: {target}")
    return target.read_text(encoding="utf-8").splitlines()
```

- [ ] **Step 3: 实现按固定字段前缀替换行的核心函数**

```python
def replace_prefixed_line(lines: list[str], prefix: str, value: str) -> bool:
    replacement = f"{prefix}{value}"
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            lines[index] = replacement
            return True
    return False
```

- [ ] **Step 4: 实现 `sync_current_task(...)` 主函数**

```python
def sync_current_task(
    repo_root: Path,
    event: str,
    progress: str | None = None,
    blocker: str | None = None,
    validation_status: str | None = None,
    validation_evidence: str | None = None,
    next_step: str | None = None,
    last_validation: str | None = None,
) -> SyncResult:
    target = resolve_current_task(repo_root)
    lines = read_current_task(target)
    changed_fields: list[str] = []

    updates = {
        "当前进度": progress,
        "当前卡点": blocker,
        "验证状态": validation_status,
        "验证证据": validation_evidence,
        "下一步": next_step,
        "最近验证": last_validation,
    }

    for field_name, value in updates.items():
        if value is None:
            continue
        prefix = FIELD_PREFIXES[
            {
                "当前进度": "progress",
                "当前卡点": "blocker",
                "验证状态": "validation_status",
                "验证证据": "validation_evidence",
                "下一步": "next_step",
                "最近验证": "last_validation",
            }[field_name]
        ]
        if replace_prefixed_line(lines, prefix, value):
            changed_fields.append(field_name)

    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return SyncResult(updated=bool(changed_fields), target=str(target), changed_fields=changed_fields)
```

- [ ] **Step 5: 实现 CLI 入口、事件校验和 UTF-8 JSON 输出**

```python
VALID_EVENTS = {"start", "phase", "validate", "preclose"}


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Sync .codex/docs/当前任务.md for long-running work.")
    parser.add_argument("--repo", default=".", help="Repository root.")
    parser.add_argument("--event", required=True, choices=sorted(VALID_EVENTS))
    parser.add_argument("--progress")
    parser.add_argument("--blocker")
    parser.add_argument("--validation-status")
    parser.add_argument("--validation-evidence")
    parser.add_argument("--next-step")
    parser.add_argument("--last-validation")
    args = parser.parse_args(argv)

    try:
        result = sync_current_task(
            repo_root=Path(args.repo),
            event=args.event,
            progress=args.progress,
            blocker=args.blocker,
            validation_status=args.validation_status,
            validation_evidence=args.validation_evidence,
            next_step=args.next_step,
            last_validation=args.last_validation,
        )
    except FileNotFoundError as exc:
        print(json.dumps({"updated": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    print(
        json.dumps(
            {
                "updated": result.updated,
                "target": result.target,
                "changed_fields": result.changed_fields,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0
```

- [ ] **Step 6: 运行测试，确认脚本行为通过**

Run:

```powershell
pwsh -NoLogo -Command "python -m pytest tests/test_sync_current_task.py -q"
```

Expected:

- PASS

- [ ] **Step 7: Commit**

```bash
git add skills/commander-mode/scripts/sync_current_task.py tests/test_sync_current_task.py
git commit -m "feat: add current task sync script"
```

## Task 3: 把同步器接回 commander 文档

**Files:**
- Modify: `README.md`
- Modify: `skills/commander-mode/SKILL.md`
- Test: `tests/test_sync_current_task.py`

- [ ] **Step 1: 在 `SKILL.md` 的 write-back 或 recovery 章节补调用建议**

```md
For long-running work, recommend synchronizing `.codex/docs/当前任务.md` at key checkpoints:

- task start
- phase transition
- validation complete
- pre-close / stop-gate

Example:

```powershell
python C:\Users\26877\.codex\skills\commander-mode\scripts\sync_current_task.py --repo . --event start --progress "进行中：开始执行当前任务" --next-step "实现最小代码改动"
```
```

- [ ] **Step 2: 在 `README.md` 的首次使用或长任务治理部分补同步器入口**

```md
### 同步长任务状态

当任务持续时间较长时，可以在关键节点把当前任务状态同步回 `.codex/docs/当前任务.md`：

```powershell
python D:\Develop\Python-Project\ai-coding-commander\skills\commander-mode\scripts\sync_current_task.py --repo . --event validate --validation-status "已验证" --validation-evidence "python -m pytest passed"
```
```

- [ ] **Step 3: 为文档接线增加最小回归**

```python
def test_commander_docs_reference_current_task_sync_script() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    skill = (repo_root / "skills" / "commander-mode" / "SKILL.md").read_text(encoding="utf-8")
    readme = (repo_root / "README.md").read_text(encoding="utf-8")

    assert "sync_current_task.py" in skill
    assert "sync_current_task.py" in readme
```

- [ ] **Step 4: 运行完整相关测试**

Run:

```powershell
pwsh -NoLogo -Command "python -m pytest tests/test_sync_current_task.py tests/test_project_codex_bootstrap.py tests/test_portable_harness.py tests/test_install_commander.py -q"
```

Expected:

- PASS
- 现有 bootstrap / harness / install 测试不回退

- [ ] **Step 5: Commit**

```bash
git add README.md skills/commander-mode/SKILL.md tests/test_sync_current_task.py
git commit -m "docs: wire current task sync into commander workflow"
```

## Self-Review

### Spec coverage

本计划已经覆盖 spec 中的核心要求：

1. 新增可直接调用的同步脚本
2. 支持 4 类事件：`start / phase / validate / preclose`
3. 只更新稳定字段
4. 缺文件时明确失败
5. UTF-8 JSON 输出
6. 不引入新的主任务协议
7. 不破坏现有 bootstrap / portable harness 测试

没有遗漏的主需求。

### Placeholder scan

已检查：

- 没有 `TODO / TBD / later`
- 没有“适当处理错误”这种空描述
- 每个代码步骤都附了代码块
- 每个验证步骤都有明确命令和预期

### Type consistency

本计划统一使用以下名称：

- `sync_current_task.py`
- `SyncResult`
- `sync_current_task(...)`
- `VALID_EVENTS`

输入字段名和 CLI 参数保持一致，没有前后漂移。

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-18-current-task-sync-implementation.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
