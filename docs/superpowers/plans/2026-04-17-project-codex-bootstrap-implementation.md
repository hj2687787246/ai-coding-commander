# Project `.codex` Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `commander-mode` 能在任意仓库中区分“已初始化 / 未初始化”项目，对未初始化项目执行半自动 `.codex` 骨架初始化，并默认落到通用 `当前任务.md` 而不是学习模板。

**Architecture:** 这次实现分三块一起落地：一是增强 `portable_harness.py` 的项目初始化探测能力；二是新增 `bootstrap_codex_workspace.py` 和标准模板目录来写入最小 `.codex` 骨架；三是更新 `commander-mode` 与参考文档，使 skill 在已初始化项目走恢复、未初始化项目走确认后初始化。测试放在仓库顶层新的 `tests/` 目录，不复用 `legacy/` 的运行时测试。

**Tech Stack:** Python 3、pytest、Markdown 模板、Codex skill docs

---

## File Structure

### New / Modified Files

- Modify: `D:\Develop\Python-Project\ai-coding-commander\skills\commander-mode\SKILL.md`
  - 让 skill 按“已初始化 / 未初始化”分支工作，去掉 Agent 学习项目特例恢复逻辑。
- Modify: `D:\Develop\Python-Project\ai-coding-commander\skills\commander-mode\scripts\portable_harness.py`
  - 暴露 commander 协议初始化探测结果，供 skill 和测试复用。
- Modify: `D:\Develop\Python-Project\ai-coding-commander\skills\commander-mode\references\portable-harness.md`
  - 补 portable harness 对 commander 初始化状态的说明。
- Modify: `D:\Develop\Python-Project\ai-coding-commander\skills\commander-mode\references\project-codex-layout.md`
  - 从“学习项目结构”调整为“通用项目骨架 + 任务模式”说明。
- Create: `D:\Develop\Python-Project\ai-coding-commander\skills\commander-mode\scripts\bootstrap_codex_workspace.py`
  - 执行确认后的 `.codex` 骨架初始化。
- Create: `D:\Develop\Python-Project\ai-coding-commander\skills\commander-mode\references\templates\project-codex-standard\AGENTS.md`
- Create: `D:\Develop\Python-Project\ai-coding-commander\skills\commander-mode\references\templates\project-codex-standard\.codex\AGENT.md`
- Create: `D:\Develop\Python-Project\ai-coding-commander\skills\commander-mode\references\templates\project-codex-standard\.codex\docs\当前状态.md`
- Create: `D:\Develop\Python-Project\ai-coding-commander\skills\commander-mode\references\templates\project-codex-standard\.codex\docs\当前任务.md`
- Create: `D:\Develop\Python-Project\ai-coding-commander\skills\commander-mode\references\templates\project-codex-standard\.codex\docs\恢复入口.md`
- Create: `D:\Develop\Python-Project\ai-coding-commander\skills\commander-mode\references\templates\project-codex-standard\.codex\docs\验收记录.md`
- Create: `D:\Develop\Python-Project\ai-coding-commander\skills\commander-mode\references\templates\project-codex-standard\.codex\docs\归档索引.md`
- Create: `D:\Develop\Python-Project\ai-coding-commander\skills\commander-mode\references\templates\project-codex-standard\.codex\docs\协作偏好.md`
- Create: `D:\Develop\Python-Project\ai-coding-commander\skills\commander-mode\references\templates\project-codex-standard\.codex\docs\周总结.md`
- Create: `D:\Develop\Python-Project\ai-coding-commander\tests\test_portable_harness.py`
  - 验证已初始化/未初始化探测和 portable status 输出。
- Create: `D:\Develop\Python-Project\ai-coding-commander\tests\test_project_codex_bootstrap.py`
  - 验证 `.codex` 骨架写入、非覆盖行为和中性任务模式默认值。

---

### Task 1: 增强 portable harness 的 commander 初始化探测

**Files:**
- Modify: `D:\Develop\Python-Project\ai-coding-commander\skills\commander-mode\scripts\portable_harness.py`
- Create: `D:\Develop\Python-Project\ai-coding-commander\tests\test_portable_harness.py`
- Modify: `D:\Develop\Python-Project\ai-coding-commander\skills\commander-mode\references\portable-harness.md`

- [ ] **Step 1: 写失败测试，固定“已初始化 / 未初始化”判定规则**

```python
import importlib.util
from pathlib import Path


def load_module(relative_path: str, module_name: str):
    root = Path(__file__).resolve().parents[1]
    target = root / relative_path
    spec = importlib.util.spec_from_file_location(module_name, target)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_status_reports_codex_initialized_when_project_has_agent_file(tmp_path: Path) -> None:
    harness = load_module("skills/commander-mode/scripts/portable_harness.py", "portable_harness")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / ".codex").mkdir()
    (repo / ".codex" / "AGENT.md").write_text("# project rules\n", encoding="utf-8")

    status = harness.build_status(repo)

    assert status["commander_protocol"]["initialized"] is True
    assert ".codex/AGENT.md" in status["commander_protocol"]["markers"]


def test_status_reports_codex_uninitialized_without_protocol_markers(tmp_path: Path) -> None:
    harness = load_module("skills/commander-mode/scripts/portable_harness.py", "portable_harness")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()

    status = harness.build_status(repo)

    assert status["commander_protocol"]["initialized"] is False
    assert status["commander_protocol"]["markers"] == []
```

- [ ] **Step 2: 运行测试，确认当前实现还没有这层输出**

Run:

```powershell
cd D:\Develop\Python-Project\ai-coding-commander
python -m pytest tests/test_portable_harness.py -q
```

Expected:

- FAIL，提示 `commander_protocol` 字段不存在，或模块导入路径还没准备好。

- [ ] **Step 3: 最小实现 portable harness 探测**

```python
def detect_commander_protocol(repo_root: Path) -> dict[str, Any]:
    markers: list[str] = []
    if (repo_root / ".codex" / "AGENT.md").exists():
        markers.append(".codex/AGENT.md")
    if (repo_root / ".codex" / "docs" / "当前状态.md").exists():
        markers.append(".codex/docs/当前状态.md")

    agents_file = repo_root / "AGENTS.md"
    if agents_file.exists():
        try:
            agents_text = agents_file.read_text(encoding="utf-8")
        except OSError:
            agents_text = ""
        if ".codex/AGENT.md" in agents_text:
            markers.append("AGENTS.md -> .codex/AGENT.md")

    deduped = list(dict.fromkeys(markers))
    return {
        "initialized": bool(deduped),
        "markers": deduped,
    }


def build_status(cwd: Path) -> dict[str, Any]:
    repo_root = resolve_git_root(cwd)
    if repo_root is None:
        return {
            "schema_version": "commander-portable-harness-v1",
            "cwd": str(cwd),
            "is_git_repo": False,
            "harness_level": "none",
            "commander_protocol": {
                "initialized": False,
                "markers": [],
            },
            "next_actions": ["Open a git workspace or initialize repo-local task tracking before relying on harness checks."],
        }
    ...
    return {
        ...
        "commander_protocol": detect_commander_protocol(repo_root),
        ...
    }
```

- [ ] **Step 4: 跑测试，确认探测行为通过**

Run:

```powershell
cd D:\Develop\Python-Project\ai-coding-commander
python -m pytest tests/test_portable_harness.py -q
```

Expected:

- PASS，至少 2 个用例通过。

- [ ] **Step 5: 更新 portable-harness 参考文档**

```md
## Commander Protocol Detection

`status` 现在会返回 `commander_protocol` 字段：

- `initialized`: 当前仓库是否已经接入项目内 commander 协议
- `markers`: 用来判定已初始化的最小证据列表

判定规则：

1. 存在 `.codex/AGENT.md`
2. 存在 `.codex/docs/当前状态.md`
3. 仓库根 `AGENTS.md` 明确把 `.codex/AGENT.md` 作为入口之一
```

- [ ] **Step 6: Commit**

```bash
git add skills/commander-mode/scripts/portable_harness.py skills/commander-mode/references/portable-harness.md tests/test_portable_harness.py
git commit -m "feat: detect codex commander protocol in portable harness"
```

---

### Task 2: 增加标准 `.codex` 模板和初始化脚本

**Files:**
- Create: `D:\Develop\Python-Project\ai-coding-commander\skills\commander-mode\scripts\bootstrap_codex_workspace.py`
- Create: `D:\Develop\Python-Project\ai-coding-commander\skills\commander-mode\references\templates\project-codex-standard\AGENTS.md`
- Create: `D:\Develop\Python-Project\ai-coding-commander\skills\commander-mode\references\templates\project-codex-standard\.codex\AGENT.md`
- Create: `D:\Develop\Python-Project\ai-coding-commander\skills\commander-mode\references\templates\project-codex-standard\.codex\docs\当前状态.md`
- Create: `D:\Develop\Python-Project\ai-coding-commander\skills\commander-mode\references\templates\project-codex-standard\.codex\docs\当前任务.md`
- Create: `D:\Develop\Python-Project\ai-coding-commander\skills\commander-mode\references\templates\project-codex-standard\.codex\docs\恢复入口.md`
- Create: `D:\Develop\Python-Project\ai-coding-commander\skills\commander-mode\references\templates\project-codex-standard\.codex\docs\验收记录.md`
- Create: `D:\Develop\Python-Project\ai-coding-commander\skills\commander-mode\references\templates\project-codex-standard\.codex\docs\归档索引.md`
- Create: `D:\Develop\Python-Project\ai-coding-commander\skills\commander-mode\references\templates\project-codex-standard\.codex\docs\协作偏好.md`
- Create: `D:\Develop\Python-Project\ai-coding-commander\skills\commander-mode\references\templates\project-codex-standard\.codex\docs\周总结.md`
- Create: `D:\Develop\Python-Project\ai-coding-commander\tests\test_project_codex_bootstrap.py`

- [ ] **Step 1: 写失败测试，固定“写入通用骨架且默认任务模式中性”**

```python
import importlib.util
from pathlib import Path


def load_module(relative_path: str, module_name: str):
    root = Path(__file__).resolve().parents[1]
    target = root / relative_path
    spec = importlib.util.spec_from_file_location(module_name, target)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_bootstrap_creates_standard_codex_skeleton(tmp_path: Path) -> None:
    bootstrap = load_module("skills/commander-mode/scripts/bootstrap_codex_workspace.py", "bootstrap_codex_workspace")
    repo = tmp_path / "repo"
    repo.mkdir()

    result = bootstrap.bootstrap_workspace(repo)

    assert result.created is True
    assert (repo / ".codex" / "AGENT.md").exists()
    assert (repo / ".codex" / "docs" / "当前任务.md").exists()
    current_task = (repo / ".codex" / "docs" / "当前任务.md").read_text(encoding="utf-8")
    assert "当前任务模式" in current_task
    assert "学习进度卡" not in current_task


def test_bootstrap_does_not_overwrite_existing_agents(tmp_path: Path) -> None:
    bootstrap = load_module("skills/commander-mode/scripts/bootstrap_codex_workspace.py", "bootstrap_codex_workspace")
    repo = tmp_path / "repo"
    repo.mkdir()
    agents = repo / "AGENTS.md"
    agents.write_text("keep me\n", encoding="utf-8")

    bootstrap.bootstrap_workspace(repo)

    assert agents.read_text(encoding="utf-8") == "keep me\n"
```

- [ ] **Step 2: 运行测试，确认脚本还不存在**

Run:

```powershell
cd D:\Develop\Python-Project\ai-coding-commander
python -m pytest tests/test_project_codex_bootstrap.py -q
```

Expected:

- FAIL，提示 `bootstrap_codex_workspace.py` 或 `bootstrap_workspace` 不存在。

- [ ] **Step 3: 写最小模板和初始化脚本**

```python
from dataclasses import dataclass
from pathlib import Path
import shutil


TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "references" / "templates" / "project-codex-standard"


@dataclass(frozen=True)
class BootstrapResult:
    created: bool
    created_paths: list[str]


def bootstrap_workspace(repo_root: Path) -> BootstrapResult:
    repo_root = repo_root.resolve()
    created_paths: list[str] = []

    for source in TEMPLATE_ROOT.rglob("*"):
        if source.is_dir():
            continue
        relative = source.relative_to(TEMPLATE_ROOT)
        target = repo_root / relative
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        created_paths.append(str(relative).replace("\\", "/"))

    return BootstrapResult(created=bool(created_paths), created_paths=created_paths)
```

模板里的 `当前任务.md` 至少包含：

```md
# 当前任务

- 当前任务名称：待定义
- 当前任务目标：待补充
- 当前任务模式：待确认
- 当前进度：未开始
- 当前卡点：无
- 下一步：确认当前任务模式
- 最近验证：无
```

- [ ] **Step 4: 跑测试，确认初始化行为通过**

Run:

```powershell
cd D:\Develop\Python-Project\ai-coding-commander
python -m pytest tests/test_project_codex_bootstrap.py -q
```

Expected:

- PASS，验证骨架创建成功、AGENTS 不被覆盖、默认任务模式中性。

- [ ] **Step 5: Commit**

```bash
git add skills/commander-mode/scripts/bootstrap_codex_workspace.py skills/commander-mode/references/templates/project-codex-standard tests/test_project_codex_bootstrap.py
git commit -m "feat: add reusable project codex bootstrap skeleton"
```

---

### Task 3: 更新 `project-codex-layout` 参考文档，切换到通用任务骨架

**Files:**
- Modify: `D:\Develop\Python-Project\ai-coding-commander\skills\commander-mode\references\project-codex-layout.md`

- [ ] **Step 1: 写文档回归检查，固定“默认骨架不是学习模板”**

```python
from pathlib import Path


def test_project_codex_layout_mentions_current_task_not_learning_card() -> None:
    doc = Path("skills/commander-mode/references/project-codex-layout.md").read_text(encoding="utf-8")
    assert "当前任务.md" in doc
    assert "学习进度卡" not in doc.split("推荐结构：", 1)[1]
```

- [ ] **Step 2: 运行文档检查，确认当前文档还是学习结构**

Run:

```powershell
cd D:\Develop\Python-Project\ai-coding-commander
python -m pytest tests/test_project_codex_bootstrap.py -q -k layout
```

Expected:

- FAIL，当前参考文档仍然以学习项目结构为主。

- [ ] **Step 3: 改参考文档为通用项目骨架**

```md
推荐结构：

```text
<repo>/
  AGENTS.md
  .codex/
    AGENT.md
    docs/
      当前状态.md
      当前任务.md
      恢复入口.md
      验收记录.md
      归档索引.md
      协作偏好.md
      周总结.md
```

说明：

- 默认骨架使用 `当前任务.md`；
- 学习模式只是任务模式之一；
- 只有项目自己进入学习模式时，才额外长出学习进度卡、学习时间线等文档。
```

- [ ] **Step 4: 重新运行文档检查**

Run:

```powershell
cd D:\Develop\Python-Project\ai-coding-commander
python -m pytest tests/test_project_codex_bootstrap.py -q -k layout
```

Expected:

- PASS。

- [ ] **Step 5: Commit**

```bash
git add skills/commander-mode/references/project-codex-layout.md tests/test_project_codex_bootstrap.py
git commit -m "docs: switch project codex layout to task-based skeleton"
```

---

### Task 4: 更新 `commander-mode`，按“已初始化 / 未初始化”分流

**Files:**
- Modify: `D:\Develop\Python-Project\ai-coding-commander\skills\commander-mode\SKILL.md`
- Test: `D:\Develop\Python-Project\ai-coding-commander\tests\test_project_codex_bootstrap.py`

- [ ] **Step 1: 写文档行为检查，固定 skill 不再写死 Agent 学习特例**

```python
from pathlib import Path


def test_commander_skill_uses_initialized_uninitialized_flow() -> None:
    skill = Path("skills/commander-mode/SKILL.md").read_text(encoding="utf-8")
    assert "已初始化项目" in skill
    assert "未初始化项目" in skill
    assert "学习进度卡.md" not in skill
    assert "学习时间线.md" not in skill
```

- [ ] **Step 2: 运行检查，确认当前 skill 仍包含 Agent 学习特例**

Run:

```powershell
cd D:\Develop\Python-Project\ai-coding-commander
python -m pytest tests/test_project_codex_bootstrap.py -q -k commander_skill
```

Expected:

- FAIL，当前 `SKILL.md` 还包含 Agent 学习项目的专项恢复顺序。

- [ ] **Step 3: 修改 `SKILL.md` 的 Workspace Discovery 和恢复分支**

```md
## Workspace Discovery

1. Start from the current working directory unless the user gives another workspace path.
2. Prefer repo-local instructions before generic defaults:
   - Read `AGENTS.md` when it exists.
   - Read `.codex/AGENT.md` when it exists.
   - If the project exposes `.codex/docs/恢复入口.md`, follow it.
3. Decide whether the project is initialized:
   - Initialized when `.codex/AGENT.md` or `.codex/docs/当前状态.md` exists, or when `AGENTS.md` points to `.codex/AGENT.md`.
   - Otherwise treat it as uninitialized.
4. For initialized projects:
   - restore current project state
   - identify current task mode
   - continue from current project docs
5. For uninitialized projects:
   - explain that the project has no commander protocol yet
   - propose creating the standard `.codex` skeleton
   - wait for user confirmation before writing files
```

- [ ] **Step 4: 运行文档检查，确认 skill 已切到通用协议**

Run:

```powershell
cd D:\Develop\Python-Project\ai-coding-commander
python -m pytest tests/test_project_codex_bootstrap.py -q -k commander_skill
```

Expected:

- PASS。

- [ ] **Step 5: Commit**

```bash
git add skills/commander-mode/SKILL.md tests/test_project_codex_bootstrap.py
git commit -m "feat: make commander-mode bootstrap repo-local codex protocol"
```

---

### Task 5: 端到端回归与验收矩阵落地

**Files:**
- Modify: `D:\Develop\Python-Project\ai-coding-commander\tests\test_project_codex_bootstrap.py`
- Optionally Modify: `D:\Develop\Python-Project\ai-coding-commander\README.md`

- [ ] **Step 1: 把 spec 的 5 个验收场景转成端到端测试**

```python
def test_initialized_project_restores_instead_of_bootstrapping(tmp_path: Path) -> None:
    harness = load_module("skills/commander-mode/scripts/portable_harness.py", "portable_harness")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".codex" / "AGENT.md").parent.mkdir(parents=True)
    (repo / ".codex" / "AGENT.md").write_text("# rules\n", encoding="utf-8")

    status = harness.build_status(repo)

    assert status["commander_protocol"]["initialized"] is True


def test_uninitialized_project_bootstrap_flow_stays_task_neutral(tmp_path: Path) -> None:
    bootstrap = load_module("skills/commander-mode/scripts/bootstrap_codex_workspace.py", "bootstrap_codex_workspace")
    repo = tmp_path / "repo"
    repo.mkdir()

    bootstrap.bootstrap_workspace(repo)
    task_doc = (repo / ".codex" / "docs" / "当前任务.md").read_text(encoding="utf-8")

    assert "当前任务模式：待确认" in task_doc
    assert "学习主线" not in task_doc
```

- [ ] **Step 2: 跑回归，覆盖 harness + bootstrap + skill 文档行为**

Run:

```powershell
cd D:\Develop\Python-Project\ai-coding-commander
python -m pytest tests/test_portable_harness.py tests/test_project_codex_bootstrap.py -q
```

Expected:

- PASS，覆盖：
  - 已初始化项目恢复
  - 未初始化项目首次接入
  - 二次进入不重复初始化
  - 默认任务模式中性
  - skill 文档不再回到学习特例

- [ ] **Step 3: 用 README 补一段“新项目如何首次接入 commander”**

```md
## Bootstrapping a new project

When `commander-mode` enters a repository that does not yet have a `.codex` protocol, it should:

1. detect the project as uninitialized
2. propose creating the standard `.codex` skeleton
3. wait for confirmation
4. create the task-oriented project workspace

The default skeleton is task-based, not learning-based.
```

- [ ] **Step 4: 再跑一次总回归**

Run:

```powershell
cd D:\Develop\Python-Project\ai-coding-commander
python -m pytest tests/test_portable_harness.py tests/test_project_codex_bootstrap.py -q
```

Expected:

- PASS。

- [ ] **Step 5: Commit**

```bash
git add tests/test_portable_harness.py tests/test_project_codex_bootstrap.py README.md
git commit -m "test: cover codex bootstrap recovery matrix"
```

---

## Self-Review

### Spec coverage

- 已初始化 / 未初始化判定：Task 1、Task 4
- 半自动初始化：Task 2、Task 4
- 通用 `.codex` 骨架：Task 2、Task 3
- 任务模式中性：Task 2、Task 5
- 防串台：Task 4、Task 5
- 三类产物（skill / 模板 / 脚本）：Task 2、Task 4
- 验收矩阵：Task 5

### Placeholder scan

- 本计划没有使用 TBD / TODO / “稍后实现” 之类占位描述。
- 每个代码步骤都给了最小代码块。
- 每个验证步骤都给了明确命令和预期。

### Type consistency

- 统一使用 `build_status()` 输出 `commander_protocol`
- 统一使用 `bootstrap_workspace()` 作为初始化入口
- 统一使用 `当前任务.md` 作为任务模式承载文件

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-17-project-codex-bootstrap-implementation.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
