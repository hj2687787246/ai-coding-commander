# Taskmaster Capability Absorption Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `taskmaster` 中值得吸收的任务治理能力并入当前 `commander-mode` 体系，而不引入新的主任务协议。

**Architecture:** 这轮只增强 commander 文档协议、项目 `.codex` 模板和配套测试，不新增新的 runtime 或第二套任务目录。实现以 `.codex/docs/当前任务.md` 模板字段、`commander-mode` 规则表述和 `project-codex-layout` 参考文档为主，通过现有 bootstrap 复制链自然落地到新项目。

**Tech Stack:** Markdown templates, Python bootstrap script, pytest, commander-mode skill docs

---

### Task 1: 补失败测试，锁定任务形状 / 执行强度 / 验证字段

**Files:**
- Modify: `tests/test_project_codex_bootstrap.py`
- Modify: `skills/commander-mode/references/templates/project-codex-standard/.codex/docs/当前任务.md`

- [ ] **Step 1: 为当前任务模板新增失败测试**

在 `tests/test_project_codex_bootstrap.py` 中为 bootstrap 后的 `当前任务.md` 增加断言，要求模板包含：

```python
assert "当前任务形状" in current_task
assert "执行强度" in current_task
assert "验证状态" in current_task
assert "验证证据" in current_task
```

- [ ] **Step 2: 运行目标测试并确认失败**

Run:

```powershell
pwsh -NoLogo -Command "python -m pytest tests/test_project_codex_bootstrap.py -q"
```

Expected:
- 现有 `test_bootstrap_creates_standard_codex_skeleton` 或新增测试失败
- 失败原因明确指向模板中缺少新字段

- [ ] **Step 3: 最小修改当前任务模板**

将 `skills/commander-mode/references/templates/project-codex-standard/.codex/docs/当前任务.md` 改成至少包含：

```markdown
# 当前任务

- 当前任务名称：待定义
- 当前任务目标：待补充
- 当前任务模式：待确认
- 当前任务形状：single
- 执行强度：full
- 当前进度：未开始
- 当前卡点：无
- 验证状态：未验证
- 验证证据：无
- 下一步：确认当前任务模式
- 最近验证：无
```

- [ ] **Step 4: 重跑测试确认通过**

Run:

```powershell
pwsh -NoLogo -Command "python -m pytest tests/test_project_codex_bootstrap.py -q"
```

Expected:
- 相关模板字段测试通过

### Task 2: 补失败测试，锁定 commander 规则表达

**Files:**
- Modify: `tests/test_project_codex_bootstrap.py`
- Modify: `skills/commander-mode/SKILL.md`
- Modify: `skills/commander-mode/references/templates/project-codex-standard/.codex/AGENT.md`

- [ ] **Step 1: 为 commander skill 新增失败测试**

在 `tests/test_project_codex_bootstrap.py` 中新增断言，要求 `skills/commander-mode/SKILL.md` 明确体现：

```python
assert "single / epic / batch" in skill or ("single" in skill and "epic" in skill and "batch" in skill)
assert "compact / full" in skill or ("compact" in skill and "full" in skill)
assert "没有验证证据，不得标记任务完成" in skill
assert "磁盘上的当前任务真相源优先于聊天记忆" in skill
```

- [ ] **Step 2: 为项目 `.codex/AGENT.md` 模板新增失败测试**

在同一个测试文件中断言模板 `.codex/AGENT.md` 明确写出：

```python
assert "当前任务.md" in agent_doc
assert "验证证据" in agent_doc
assert "未验证不得标记任务完成" in agent_doc
```

- [ ] **Step 3: 运行目标测试并确认失败**

Run:

```powershell
pwsh -NoLogo -Command "python -m pytest tests/test_project_codex_bootstrap.py -q"
```

Expected:
- 新增的 commander / AGENT 模板断言失败

- [ ] **Step 4: 最小修改 commander skill**

在 `skills/commander-mode/SKILL.md` 的项目 bootstrap / 恢复 / 完成判定相关章节中补入：

- 任务形状概念：`single / epic / batch`
- 执行强度概念：`compact / full`
- 完成 gate：没有验证证据，不得标记完成
- 恢复原则：磁盘上的当前任务真相源优先于聊天记忆

要求：
- 只增强现有 commander 叙述
- 不引入 `.codex-tasks/`、`TODO.csv` 等新主协议

- [ ] **Step 5: 最小修改项目 `.codex/AGENT.md` 模板**

在 `skills/commander-mode/references/templates/project-codex-standard/.codex/AGENT.md` 中补充项目内任务治理规则，例如：

```markdown
## 任务治理

- `当前任务.md` 是当前任务的主真相源。
- 当前任务至少应写清：任务模式、任务形状、执行强度、验证状态、验证证据。
- 没有验证证据，不得把当前任务标记为完成。
- 长任务恢复时，优先读取磁盘上的当前任务真相源，不依赖聊天记忆。
```

- [ ] **Step 6: 重跑测试确认通过**

Run:

```powershell
pwsh -NoLogo -Command "python -m pytest tests/test_project_codex_bootstrap.py -q"
```

Expected:
- commander 规则表述测试通过

### Task 3: 补失败测试，锁定轻量 batch 可选协议说明

**Files:**
- Modify: `tests/test_project_codex_bootstrap.py`
- Modify: `skills/commander-mode/references/project-codex-layout.md`

- [ ] **Step 1: 为布局参考文档新增失败测试**

在 `tests/test_project_codex_bootstrap.py` 中新增断言，要求 `project-codex-layout.md`：

```python
assert ".codex/batch/" in doc or "batch/" in doc
assert "可选" in doc
assert ".codex-tasks" not in doc
```

- [ ] **Step 2: 运行目标测试并确认失败**

Run:

```powershell
pwsh -NoLogo -Command "python -m pytest tests/test_project_codex_bootstrap.py -q"
```

Expected:
- 参考文档缺少 batch 可选协议说明而失败

- [ ] **Step 3: 最小修改布局参考文档**

在 `skills/commander-mode/references/project-codex-layout.md` 中补一个“可选批量任务扩展”小节，说明：

- 批量任务只在需要时启用
- 可选目录形态：

```text
.codex/
  batch/
    <task-name>/
      BATCH.md
      workers-input.csv
      workers-output.csv
```

- 这不是默认骨架
- 不引入 `.codex-tasks/`

- [ ] **Step 4: 重跑测试确认通过**

Run:

```powershell
pwsh -NoLogo -Command "python -m pytest tests/test_project_codex_bootstrap.py -q"
```

Expected:
- batch 可选协议测试通过

### Task 4: 跑回归并人工回读

**Files:**
- Verify: `tests/test_project_codex_bootstrap.py`
- Verify: `tests/test_portable_harness.py`
- Verify: `skills/commander-mode/SKILL.md`
- Verify: `skills/commander-mode/references/project-codex-layout.md`
- Verify: `skills/commander-mode/references/templates/project-codex-standard/.codex/docs/当前任务.md`
- Verify: `skills/commander-mode/references/templates/project-codex-standard/.codex/AGENT.md`

- [ ] **Step 1: 运行完整相关测试**

Run:

```powershell
pwsh -NoLogo -Command "python -m pytest tests/test_portable_harness.py tests/test_project_codex_bootstrap.py -q"
```

Expected:
- 全部通过

- [ ] **Step 2: 回读模板和 skill**

人工确认以下点：

- `当前任务.md` 新字段已经存在
- `commander-mode` 已写入任务形状 / 执行强度 / 验证 gate / 磁盘真相源优先
- `project-codex-layout.md` 只把 batch 作为可选协议
- 没有引入 `.codex-tasks/` 或 `TODO.csv` 作为新主协议

- [ ] **Step 3: 记录结果**

把完成结论收敛成：

- 改了哪些文件
- 跑了哪些测试
- 哪些 taskmaster 能力已被吸收
- 哪些仍然明确未吸收
