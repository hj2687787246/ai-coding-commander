# Commander 分享与安装 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `ai-coding-commander` 同时支持开发者路径和普通用户路径的对外分享与安装，并提供可执行的安装脚本。

**Architecture:** 保持 `skills/commander-mode/` 为唯一正式分发入口；通过 `install/install-commander.ps1` 为普通用户执行默认复制安装；通过 README 同时说明开发者安装与普通用户安装；用测试覆盖安装脚本的核心行为和 README 的关键对外边界。

**Tech Stack:** PowerShell 7 (`pwsh`), Python pytest, repository-local templates and scripts

---

### Task 1: 为安装脚本定义测试约束

**Files:**
- Create: `tests/test_install_commander.py`

- [ ] **Step 1: 写安装脚本测试文件**

```python
import subprocess
import sys
from pathlib import Path


def test_placeholder():
    assert True
```

- [ ] **Step 2: 把占位测试替换成真实安装约束**

测试至少覆盖：

1. 运行脚本后，目标目录出现 `skills/commander-mode/SKILL.md`
2. 默认复制安装，不创建 junction
3. 已存在目标时，未加 `-Force` 返回非零
4. `-BackupExisting` 时会创建备份目录

- [ ] **Step 3: 运行新测试，确认当前失败**

Run:

```powershell
pwsh -NoLogo -Command "python -m pytest tests/test_install_commander.py -q"
```

Expected:
- FAIL，因为安装脚本还不存在

### Task 2: 实现普通用户安装脚本

**Files:**
- Create: `install/install-commander.ps1`

- [ ] **Step 1: 新建安装脚本骨架**

脚本职责：

1. 定位 repo root
2. 定位 `skills/commander-mode`
3. 定位目标 `~/.codex/skills/commander-mode`
4. 默认复制目录安装
5. 支持 `-Force`
6. 支持 `-BackupExisting`
7. 输出安装结果 JSON

- [ ] **Step 2: 先实现最小可运行版本**

最小版本要能：

1. 创建目标父目录
2. 复制整个 `skills/commander-mode` 到目标目录
3. 输出：
   - `installed`
   - `target`
   - `pythonAvailable`

- [ ] **Step 3: 补已有目标时的保护逻辑**

要求：

1. 默认不覆盖
2. `-Force` 才允许清空并重装
3. `-BackupExisting` 时先重命名旧目录，再安装

- [ ] **Step 4: 跑安装脚本测试**

Run:

```powershell
pwsh -NoLogo -Command "python -m pytest tests/test_install_commander.py -q"
```

Expected:
- PASS

### Task 3: 更新 README 的对外分享结构

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 重构 README 安装部分**

README 需要同时写清：

1. 开发者安装路径
2. 普通用户安装路径
3. 普通用户默认使用 `install/install-commander.ps1`

- [ ] **Step 2: 增加首次使用说明**

至少要包含：

1. 如何在新项目里触发 `commander-mode`
2. 如何用 `portable_harness.py --cwd . status`
3. 如何 bootstrap `.codex`

- [ ] **Step 3: 写一条 README 边界测试**

用测试断言 README 至少包含：

1. `install/install-commander.ps1`
2. `开发者`
3. `普通用户`
4. `skills/commander-mode/`
5. `legacy/agent-runtime` 不参与安装

### Task 4: 整体回归与回读

**Files:**
- Verify: `tests/test_install_commander.py`
- Verify: `tests/test_project_codex_bootstrap.py`
- Verify: `tests/test_portable_harness.py`
- Verify: `README.md`
- Verify: `install/install-commander.ps1`

- [ ] **Step 1: 跑相关测试**

Run:

```powershell
pwsh -NoLogo -Command "python -m pytest tests/test_install_commander.py tests/test_project_codex_bootstrap.py tests/test_portable_harness.py -q"
```

Expected:
- All pass

- [ ] **Step 2: 回读 README 和安装脚本**

确认：

1. README 没把 `legacy/` 暴露成安装源
2. README 明确区分开发者与普通用户路径
3. 安装脚本默认复制目录
4. 安装脚本没有误用 junction 作为普通用户默认行为

- [ ] **Step 3: Commit**

```bash
git add README.md install/install-commander.ps1 tests/test_install_commander.py docs/superpowers/specs/2026-04-17-commander-sharing-and-installation-design.md docs/superpowers/plans/2026-04-17-commander-sharing-and-installation-implementation.md
git commit -m "Add commander sharing and installation flow"
```
