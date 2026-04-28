# High-Signal Commander v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reframe `commander-mode` as a high-signal, automatically checkpointing skill that works with or without `.codex`.

**Architecture:** Keep the skill as the product center and keep `.codex` as an automatic memory surface plus optional kit. Lock behavior with documentation tests first, then update `SKILL.md`, README/reference docs, and finally add a small `checkpoint` event to `sync_current_task.py` for process-state recovery.

**Tech Stack:** Markdown skill/docs, Python 3 standard library scripts, pytest tests.

---

## File Structure

### New Files

- `pyproject.toml`
  - Provides a standard pytest dependency and test command surface for local development.
- `tests/test_high_signal_commander_docs.py`
  - Locks the new product contract for `SKILL.md`, README, and the design spec.

### Modified Files

- `skills/commander-mode/SKILL.md`
  - Reframe the skill around intent routing, context investment, automatic write-back, checkpoints, and optional `.codex`.
- `README.md`
  - Reframe the repository as a skill-first product, not a platform or mandatory project protocol.
- `skills/commander-mode/references/project-codex-layout.md`
  - Move `.codex` language from default protocol to optional memory kit.
- `skills/commander-mode/references/portable-harness.md`
  - Clarify harness as a sensor for the skill, not the product center.
- `skills/commander-mode/scripts/sync_current_task.py`
  - Add a `checkpoint` event and one short field for focused files.
- `skills/commander-mode/references/templates/project-codex-standard/.codex/docs/当前任务.md`
  - Add the `正在关注的文件` field so checkpoint recovery can preserve the active write set.
- `tests/test_sync_current_task.py`
  - Add checkpoint behavior tests.
- `tests/test_project_codex_bootstrap.py`
  - Update skill-document tests that currently expect first-run bootstrap prompting.
- `.codex/docs/当前任务.md`
  - Keep process checkpoints current while implementing.

### Do Not Modify

- `legacy/agent-runtime/`
  - Archive only.
- User private paths under `C:\Users\26877\.codex\skills\commander-mode`
  - Live install target; update only when the user explicitly asks to install.

---

### Task 1: Add Standard Test Metadata

**Files:**
- Create: `pyproject.toml`

- [ ] **Step 1: Create `pyproject.toml`**

Add this file exactly:

```toml
[project]
name = "ai-coding-commander"
version = "0.1.0"
description = "High-signal commander skill for AI coding workflows."
requires-python = ">=3.10"
dependencies = []

[project.optional-dependencies]
test = [
  "pytest>=8.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]

[tool.setuptools]
packages = []
```

- [ ] **Step 2: Run metadata smoke check**

Run:

```powershell
& 'C:\Users\26877\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -c "import tomllib; tomllib.load(open('pyproject.toml','rb')); print('pyproject ok')"
```

Expected:

```text
pyproject ok
```

- [ ] **Step 3: Install test dependency when pytest is missing**

Run:

```powershell
& 'C:\Users\26877\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pip install -e ".[test]"
```

Expected:

```text
Successfully installed
```

- [ ] **Step 4: Verify pytest is available**

Run:

```powershell
& 'C:\Users\26877\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest --version
```

Expected:

```text
pytest
```

- [ ] **Step 5: Commit**

```powershell
git add pyproject.toml
git commit -m "chore: add project test metadata"
```

---

### Task 2: Lock High-Signal Skill Contract With Tests

**Files:**
- Create: `tests/test_high_signal_commander_docs.py`
- Modify: `tests/test_project_codex_bootstrap.py`

- [ ] **Step 1: Add failing documentation contract tests**

Create `tests/test_high_signal_commander_docs.py` with this content:

```python
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def read_text(relative_path: str) -> str:
    return (repo_root() / relative_path).read_text(encoding="utf-8")


def test_commander_skill_is_high_signal_skill_not_platform() -> None:
    skill = read_text("skills/commander-mode/SKILL.md")

    assert "高信号" in skill
    assert "skill 负责不丢上下文" in skill
    assert "不是平台" in skill
    assert "不是项目模板协议本身" in skill


def test_commander_skill_uses_context_investment_language() -> None:
    skill = read_text("skills/commander-mode/SKILL.md")

    assert "上下文投资" in skill
    assert "token 的目标是高回报" in skill
    assert "读之前先判断目的" in skill
    assert "机械读取完整模板" in skill


def test_commander_skill_auto_writeback_is_value_gated() -> None:
    skill = read_text("skills/commander-mode/SKILL.md")

    assert "自动写回" in skill
    assert "恢复价值节点" in skill
    assert "不依赖用户说" in skill
    assert "聊天原文" in skill
    assert "模型内部推理" in skill


def test_commander_skill_uses_process_checkpoints_for_long_tasks() -> None:
    skill = read_text("skills/commander-mode/SKILL.md")

    assert "覆盖式检查点" in skill
    assert "默认检查点不超过 8 行" in skill
    assert "继续下一段工作前写回" in skill
    assert "正在关注的文件" in skill


def test_commander_skill_works_without_codex() -> None:
    skill = read_text("skills/commander-mode/SKILL.md")

    assert "没有 `.codex`" in skill
    assert "仍然正常工作" in skill
    assert "不强制" in skill
    assert "完整 `.codex` 模板" in skill


def test_readme_presents_skill_first_positioning() -> None:
    readme = read_text("README.md")

    assert "高信号" in readme
    assert "skill" in readme
    assert "不是平台" in readme
    assert ".codex" in readme
    assert "可选" in readme
```

- [ ] **Step 2: Replace obsolete first-run bootstrap expectation**

In `tests/test_project_codex_bootstrap.py`, replace the function named `test_commander_skill_includes_first_run_prompt_for_uninitialized_projects` with this function:

```python
def test_commander_skill_does_not_force_bootstrap_for_uninitialized_projects() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    skill = (repo_root / "skills" / "commander-mode" / "SKILL.md").read_text(encoding="utf-8")

    assert "未初始化项目" in skill
    assert "没有 `.codex`" in skill
    assert "仍然正常工作" in skill
    assert "不强制创建完整 `.codex` 模板" in skill
```

- [ ] **Step 3: Run the new tests to verify they fail**

Run:

```powershell
& 'C:\Users\26877\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests\test_high_signal_commander_docs.py tests\test_project_codex_bootstrap.py -q
```

Expected before implementation:

```text
FAILED
```

The failure should mention missing high-signal wording or obsolete bootstrap wording.

- [ ] **Step 4: Commit failing tests**

```powershell
git add tests/test_high_signal_commander_docs.py tests/test_project_codex_bootstrap.py
git commit -m "test: lock high signal commander contract"
```

---

### Task 3: Add Checkpoint Event To Current Task Sync

**Files:**
- Modify: `skills/commander-mode/scripts/sync_current_task.py`
- Modify: `skills/commander-mode/references/templates/project-codex-standard/.codex/docs/当前任务.md`
- Modify: `tests/test_sync_current_task.py`

- [ ] **Step 1: Add failing checkpoint tests**

Append these tests to `tests/test_sync_current_task.py`:

```python
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
```

- [ ] **Step 2: Run checkpoint tests to verify they fail**

Run:

```powershell
& 'C:\Users\26877\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests\test_sync_current_task.py::test_checkpoint_event_updates_recovery_fields_without_appending_history tests\test_sync_current_task.py::test_checkpoint_cli_accepts_focus_files -q
```

Expected before implementation:

```text
FAILED
```

The failure should mention unsupported event `checkpoint` or unexpected argument `focus_files`.

- [ ] **Step 3: Update the current task template**

In `skills/commander-mode/references/templates/project-codex-standard/.codex/docs/当前任务.md`, insert this line between `当前卡点` and `验证状态`:

```markdown
- 正在关注的文件：无
```

- [ ] **Step 4: Update sync field maps**

In `skills/commander-mode/scripts/sync_current_task.py`, change the field maps to include `focus_files`:

```python
FIELD_PREFIXES = {
    "progress": "当前进度：",
    "blocker": "当前卡点：",
    "focus_files": "正在关注的文件：",
    "validation_status": "验证状态：",
    "validation_evidence": "验证证据：",
    "next_step": "下一步：",
    "last_validation": "最近验证：",
}

FIELD_LABELS = {
    "progress": "当前进度",
    "blocker": "当前卡点",
    "focus_files": "正在关注的文件",
    "validation_status": "验证状态",
    "validation_evidence": "验证证据",
    "next_step": "下一步",
    "last_validation": "最近验证",
}

VALID_EVENTS = {"start", "phase", "validate", "preclose", "checkpoint"}
```

- [ ] **Step 5: Update function signature and update map**

In `sync_current_task`, add `focus_files` after `blocker`:

```python
def sync_current_task(
    repo_root: Path,
    event: str,
    progress: str | None = None,
    blocker: str | None = None,
    focus_files: str | None = None,
    validation_status: str | None = None,
    validation_evidence: str | None = None,
    next_step: str | None = None,
    last_validation: str | None = None,
) -> SyncResult:
```

Then include it in `updates`:

```python
updates = {
    "progress": progress,
    "blocker": blocker,
    "focus_files": focus_files,
    "validation_status": validation_status,
    "validation_evidence": validation_evidence,
    "next_step": next_step,
    "last_validation": last_validation,
}
```

- [ ] **Step 6: Update CLI parser and main call**

Add this parser argument:

```python
parser.add_argument("--focus-files")
```

Pass it into `sync_current_task`:

```python
focus_files=args.focus_files,
```

- [ ] **Step 7: Run sync tests**

Run:

```powershell
& 'C:\Users\26877\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests\test_sync_current_task.py -q
```

Expected:

```text
9 passed
```

- [ ] **Step 8: Commit**

```powershell
git add skills/commander-mode/scripts/sync_current_task.py skills/commander-mode/references/templates/project-codex-standard/.codex/docs/当前任务.md tests/test_sync_current_task.py
git commit -m "feat: add current task checkpoint event"
```

---

### Task 4: Rewrite Commander Skill Around High-Signal Operation

**Files:**
- Modify: `skills/commander-mode/SKILL.md`
- Modify: `tests/test_project_codex_bootstrap.py`
- Test: `tests/test_high_signal_commander_docs.py`

- [ ] **Step 1: Replace the opening product definition**

At the top of `skills/commander-mode/SKILL.md`, replace the first paragraphs under `# Commander Mode` with:

```markdown
Adopt the commander role for the current workspace. Treat this skill as a high-signal operating layer over repo truth sources and runtime evidence, not as a platform and not as the project template protocol itself.

`commander-mode` helps the user steer AI coding work by investing context where it changes decisions, preserving recovery-critical facts automatically, and enforcing verification before completion. 用户负责决策，skill 负责不丢上下文。

The skill works even when a repository has no `.codex` directory. `.codex` is an automatic memory surface and optional kit for long-running work, not a prerequisite for using commander mode.
```

- [ ] **Step 2: Replace Workspace Discovery with high-signal discovery**

Replace the current `## Workspace Discovery` section with:

```markdown
## Workspace Discovery

1. Start from the current working directory unless the user gives another workspace path.
2. Read repo-local instruction files first when they exist:
   - `AGENTS.md`
   - `.codex/AGENT.md`
   - `.codex/docs/恢复入口.md`
   - README files
3. If `.codex` exists, use it as a memory surface, then read only the files needed for the user's current intent.
4. If `.codex` does not exist, commander mode still works. Build context from existing repo truth sources: README, docs, git status, tests, issue/task files, recent plans, and user-provided goals.
5. Do not force bootstrap for uninitialized projects. Offer full `.codex` bootstrap only when the user wants long-term project governance, batch work, or multi-stage memory.
6. If no repo-local commander docs exist, run the portable harness status script before falling back to freeform exploration:
   - Installed global copy: `python C:\Users\26877\.codex\skills\commander-mode\scripts\portable_harness.py --cwd . status`
   - When developing this repository itself, prefer the repo-local script copy under the current workspace.
7. Do not hardcode `D:\Develop\Python-Project\Agent`; that path is only one possible workspace.
```

- [ ] **Step 3: Add Intent Router section**

Insert this section after Workspace Discovery:

```markdown
## Intent Router

Classify the user's current intent before reading deeply:

1. `orient`: restore where the project is and identify the next smallest safe action.
2. `drive`: help the user choose, split, delegate, or sequence work.
3. `implement`: write code only when the user explicitly asks to implement, fix, update, create, or commit.
4. `review`: prioritize bugs, regressions, risks, and missing tests.
5. `verify`: run or interpret checks before claiming completion.
6. `handoff`: preserve enough state for another window or future session to continue.
7. `architecture`: spend more context on structure, tradeoffs, and long-lived design choices.

When the user only says "continue", "current task", "恢复", or "现在到哪了", start in `orient`.
```

- [ ] **Step 4: Add Context Investment section**

Insert this section after Intent Router:

```markdown
## Context Investment

Token use should be high-return, not merely low. Read before acting, but read for a reason.

Before opening a file or running a command, know which uncertainty it reduces:

1. Rules: what constraints must be obeyed?
2. State: what is the current task, phase, or dirty worktree?
3. Risk: what could break or be unsafe?
4. Verification: what evidence will prove the work?
5. Implementation: where is the smallest relevant code surface?

High-value context includes current code, command results, repo instructions, active task files, validation commands, failing tests, diffs, and narrow design docs. Low-value context includes mechanical reading of every template, copying chat history into memory files, and generating long plans without execution value.
```

- [ ] **Step 5: Replace Project Bootstrap section language**

Replace `## Project Bootstrap` with:

```markdown
## Optional Memory Kit

`.codex` is an automatic memory surface, not a prerequisite.

Use existing project memory when present. If no memory surface exists, continue using the repository's own truth sources.

When a recovery value node appears, choose the narrowest write-back surface:

1. Existing repo-native task file, issue tracker, plan, or status doc.
2. Existing `.codex/docs/当前任务.md` or equivalent `.codex` memory file.
3. A minimal single-file recovery anchor when long-running work needs continuity.
4. Full `.codex` bootstrap only when the user wants durable multi-stage project governance.

Do not force or imply full bootstrap for ordinary one-off work.
```

- [ ] **Step 6: Replace Write-Back Discipline with automatic checkpoint language**

Replace `## Write-Back Discipline` with:

```markdown
## Automatic Write-Back And Checkpoints

Write-back is automatic but value-gated. At the end of every meaningful action batch, ask whether this turn produced a recovery value node.

Write the smallest stable increment when any of these changes:

1. Current task, goal, scope, or mode.
2. Key decision that changes future work.
3. Blocker, failure, or resolved blocker.
4. Completed recoverable sub-step.
5. Validation evidence or validation failure.
6. Pending wait for a long command, user decision, or sub-agent result.
7. Stable user collaboration preference.

Do not write chat transcripts, temporary guesses, long process narration, low-value intermediate output, or model internal reasoning.

For long tasks, use覆盖式检查点 instead of append-only logs. 默认检查点不超过 8 行 and should cover: current goal, phase, recently completed work, blocker, focused files, next step, validation status, and latest validation.

Before a likely interruption or wait, write the checkpoint before continuing.
```

- [ ] **Step 7: Keep verification and boundary rules**

Ensure `SKILL.md` still includes these exact strings:

```text
没有验证证据，不得标记任务完成
legacy/agent-runtime/
~/.codex/skills/commander-mode
portable_harness.py
```

- [ ] **Step 8: Run documentation contract tests**

Run:

```powershell
& 'C:\Users\26877\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests\test_high_signal_commander_docs.py tests\test_project_codex_bootstrap.py -q
```

Expected:

```text
passed
```

- [ ] **Step 9: Commit**

```powershell
git add skills/commander-mode/SKILL.md tests/test_project_codex_bootstrap.py tests/test_high_signal_commander_docs.py
git commit -m "feat: reframe commander as high signal skill"
```

---

### Task 5: Update README And References

**Files:**
- Modify: `README.md`
- Modify: `skills/commander-mode/references/project-codex-layout.md`
- Modify: `skills/commander-mode/references/portable-harness.md`
- Test: `tests/test_high_signal_commander_docs.py`

- [ ] **Step 1: Update README opening**

Replace the first paragraph under `# AI Coding Commander` with:

```markdown
高信号 AI coding 指挥 skill 的独立承接仓库。

这个仓库交付的是 `commander-mode` skill，不是平台，也不是必须套用的项目模板。它的职责是在任意代码仓库里帮助 Codex 选择有价值的上下文、恢复当前工作、自动沉淀关键检查点，并在收口前保护验证纪律。
```

- [ ] **Step 2: Update README current mainline list**

Change the active implementation list to include `sync_current_task.py`:

```markdown
当前活跃实现只认：

1. `skills/commander-mode/`
2. `skills/commander-mode/scripts/portable_harness.py`
3. `skills/commander-mode/scripts/bootstrap_codex_workspace.py`
4. `skills/commander-mode/scripts/sync_current_task.py`
```

- [ ] **Step 3: Add High-Signal usage section**

Add this section after `## 当前主线`:

```markdown
## High-Signal 使用原则

`commander-mode` 默认自动运行以下循环：

1. 判断用户意图。
2. 选择最有价值的上下文。
3. 给出当前判断和下一步最小动作。
4. 执行用户授权范围内的工作。
5. 在出现恢复价值节点时自动写回最小检查点。

`.codex` 是自动记忆面和可选增强包。没有 `.codex` 的仓库仍然可以直接使用 commander；完整 `.codex` 模板只用于需要长期治理、批量任务或多阶段项目记忆的场景。
```

- [ ] **Step 4: Update project codex layout reference**

In `skills/commander-mode/references/project-codex-layout.md`, add this paragraph near the top:

```markdown
从 High-Signal Commander v2 开始，`.codex` 是自动记忆面和可选增强包，不是使用 `commander-mode` 的前提。普通仓库可以先依赖已有 README、docs、git、测试和任务文件；只有当工作需要跨窗口、跨阶段或长期恢复时，才启用完整 `.codex` 布局。
```

- [ ] **Step 5: Update portable harness reference**

In `skills/commander-mode/references/portable-harness.md`, add this paragraph under `## What It Provides`:

```markdown
The harness is a sensor for `commander-mode`, not the product center. Use it to quickly discover repo state, validation hints, dirty worktree status, and existing memory surfaces before deciding how much context to invest.
```

- [ ] **Step 6: Run docs tests**

Run:

```powershell
& 'C:\Users\26877\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests\test_high_signal_commander_docs.py tests\test_project_codex_bootstrap.py tests\test_sync_current_task.py -q
```

Expected:

```text
passed
```

- [ ] **Step 7: Commit**

```powershell
git add README.md skills/commander-mode/references/project-codex-layout.md skills/commander-mode/references/portable-harness.md tests/test_high_signal_commander_docs.py
git commit -m "docs: describe high signal commander workflow"
```

---

### Task 6: Final Validation And Stop Gate

**Files:**
- Modify: `.codex/docs/当前任务.md`

- [ ] **Step 1: Run full test suite**

Run:

```powershell
& 'C:\Users\26877\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -q
```

Expected:

```text
passed
```

If the bundled Python still lacks pytest, install test dependencies into an isolated environment or report the exact blocker instead of claiming tests pass.

- [ ] **Step 2: Run portable harness status**

Run:

```powershell
& 'C:\Users\26877\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' '.\skills\commander-mode\scripts\portable_harness.py' --cwd . status
```

Expected:

```text
"is_git_repo": true
"commander_protocol": {
  "initialized": true
```

- [ ] **Step 3: Update current task checkpoint**

Run:

```powershell
& 'C:\Users\26877\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' '.\skills\commander-mode\scripts\sync_current_task.py' --repo . --event checkpoint --progress '已完成 High-Signal Commander v2 实现' --focus-files 'skills/commander-mode/SKILL.md, README.md, sync_current_task.py' --validation-status '已验证' --validation-evidence 'python -m pytest -q passed' --next-step '准备收口或安装到本地 skill' --last-validation '2026-04-28 full pytest passed'
```

Expected JSON:

```json
{
  "updated": true
}
```

- [ ] **Step 4: Run stop gate with validation evidence**

Run:

```powershell
& 'C:\Users\26877\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' '.\skills\commander-mode\scripts\portable_harness.py' --cwd . stop-gate --validation 'python -m pytest -q passed'
```

Expected:

```text
"stop_allowed": true
```

- [ ] **Step 5: Commit final checkpoint if changed**

```powershell
git add .codex/docs/当前任务.md
git commit -m "docs: record high signal commander validation checkpoint"
```

---

## Self-Review

### Spec Coverage

- High-signal skill positioning is covered by Task 2, Task 4, and Task 5.
- Automatic write-back and recovery value nodes are covered by Task 2 and Task 4.
- Process checkpoints are covered by Task 3 and Task 6.
- `.codex` as automatic memory surface rather than platform prerequisite is covered by Task 4 and Task 5.
- Existing tools remain available through Task 3 and Task 6.
- README skill-first framing is covered by Task 5.

### Placeholder Scan

This plan avoids reserved placeholder markers and vague future-work language. Each code-changing task includes exact snippets, commands, and expected results.

### Type Consistency

- The new sync field is named `focus_files`.
- The CLI flag is `--focus-files`.
- The human-readable label is `正在关注的文件`.
- The new event is `checkpoint`.
