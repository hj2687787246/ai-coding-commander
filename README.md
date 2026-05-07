# AI Coding Commander

高信号 AI coding 指挥 skill 的独立承接仓库。

这个仓库交付的是 `commander-mode`、`commander-reuse-upgrader` 和 `execution-failure-guard` 三个 skill，不是平台，也不是必须套用的项目模板。`commander-mode` 负责在任意代码仓库里选择有价值的上下文、恢复当前工作、自动沉淀关键检查点，并在收口前保护验证纪律；`commander-reuse-upgrader` 负责把重复问题分流到项目文档、自动化脚本/检查器或轻量 skill；`execution-failure-guard` 负责把一次执行失败后找到的可用方法变成后续同类操作的默认路径。

## 当前主线

当前活跃实现只认：

1. `skills/commander-mode/`
2. `skills/commander-reuse-upgrader/`
3. `skills/execution-failure-guard/`
4. `skills/commander-mode/scripts/portable_harness.py`
5. `skills/commander-mode/scripts/bootstrap_codex_workspace.py`
6. `skills/commander-mode/scripts/sync_current_task.py`
7. `skills/commander-mode/scripts/sync_preference_memory.py`

`legacy/agent-runtime/` 仅作归档参考，不参与当前实现，不作为当前安装源、恢复入口或扩展目标。

目标：

1. 提供跨仓库可用的 `commander-mode` skill。
2. 提供跨仓库可用的 `commander-reuse-upgrader` skill，负责复用沉淀分流。
3. 提供跨仓库可用的 `execution-failure-guard` skill，负责执行失败后的可用方法复用和升级沉淀，并提供 `.codex/known-failures.json` 检查器。
4. 提供最小 portable harness：状态扫描和 stop gate。
5. 不依赖旧 Agent 仓库里的 `commander/` runtime。

## High-Signal 使用原则

`commander-mode` 默认自动运行以下循环：

1. 判断用户意图。
2. 选择最有价值的上下文。
3. 给出当前判断和下一步最小动作。
4. 执行用户授权范围内的工作。
5. 在出现恢复价值节点时自动写回最小检查点。

`.codex` 是自动记忆面和可选增强包。没有 `.codex` 的仓库仍然可以直接使用 commander；完整 `.codex` 模板只用于需要长期治理、批量任务或多阶段项目记忆的场景。

### Standard Activation Contract

`commander-mode` 的自动执行不是建议清单，而是标准运行契约。skill 一旦触发，就按 Entry / Heartbeat / Preference Write-Back / Preclose / Recovery 五个 hook 执行：

1. Entry：进入任务前恢复规则、状态和本轮适用偏好。
2. Heartbeat：长命令、等待、中断风险或阶段切换前写 checkpoint。
3. Preference Write-Back：用户明确或反复表达长期习惯时写入偏好卡。
4. Preclose：完成、提交、切换阶段或交接前执行 Preference Gate 和验证 gate。
5. Recovery：中断或继续时先读磁盘真相源，再恢复下一步。

### Preference Memory

Preference Memory 是 high-signal commander 的用户习惯记忆层。它把长期稳定偏好写成结构化偏好卡，而不是只写成长篇说明。

`commander-mode` 每轮应自动选择本轮适用偏好，并在收口前执行 Preference Gate：

1. 本轮激活了哪些偏好。
2. 有没有违反已激活偏好。
3. 用户纠正方向后，是否应写入候选偏好或稳定偏好。
4. 是否需要同步当前任务检查点或验收记录。

偏好写回可以使用：

```powershell
python .\skills\commander-mode\scripts\sync_preference_memory.py --repo . --id pref-token-roi --status stable --scope project --trigger planning --rule "token 使用目标是高价值，不是单纯低消耗。"
```

## 能力成熟度

当前这套 commander 已经不是单纯提示词，而是一套**高信号工程协作 skill**，并保留轻量工程治理协议作为可选记忆面。

目前大致位于：

- **L2：任务治理阶段**

已经稳定具备的能力包括：

1. 主线 / 归档分层
2. 已初始化 / 未初始化项目分流
3. 通用 `.codex` 骨架 bootstrap
4. 基于磁盘真相源的项目恢复
5. 当前任务卡作为主任务真相源
6. 验证 gate（没有验证证据，不得标记完成）
7. 任务形状与执行强度表达
8. 可安装、可分享、可测试

还未进入的平台能力主要包括：

1. 自动任务分型
2. 更强的 epic / batch 编排
3. 执行强度驱动的差异化流程
4. `.codex` 协议版本迁移
5. 跨项目审计与观测

完整路线图和 `L2 -> L3` 的建议实施顺序见：

- `docs/commander-capability-roadmap.md`

skill 触发回归矩阵见：

- `docs/skill-trigger-matrix.md`

另外，这个仓库也提供一套推荐的**项目内 `.codex` 工作区布局**，用于把：

1. 全局可复用 skill
2. 项目专属 Codex 规则
3. 项目正文文档
4. MCP 资源理解边界

这几层清晰分开，而不是继续把项目任务文档、AI 协作规则和业务文档混在同一层里。

## 安装

### 开发者

适合：

- 会 `git clone`
- 会运行 `pwsh` / Python
- 希望直接跟踪仓库源码

开发者可以选择两种方式暴露正式 skill：

#### 方式 A：复制目录

把仓库里的正式分发目录：

- `skills/commander-mode/`
- `skills/commander-reuse-upgrader/`
- `skills/execution-failure-guard/`

复制到本地：

- `~/.codex/skills/commander-mode`
- `~/.codex/skills/commander-reuse-upgrader`
- `~/.codex/skills/execution-failure-guard`

#### 方式 B：junction

如果你希望本地 skills 始终直接指向仓库源码，可以用 junction：

```powershell
$repo = (Resolve-Path ".").Path
cmd /c mklink /J "$env:USERPROFILE\.codex\skills\commander-mode" "$repo\skills\commander-mode"
cmd /c mklink /J "$env:USERPROFILE\.codex\skills\commander-reuse-upgrader" "$repo\skills\commander-reuse-upgrader"
cmd /c mklink /J "$env:USERPROFILE\.codex\skills\execution-failure-guard" "$repo\skills\execution-failure-guard"
```

### 普通用户

适合：

- 不想理解仓库结构
- 只想把 commander skills 装进本地 Codex skills

默认推荐使用安装脚本，安装脚本会采用**复制目录**的方式，而不是默认创建 junction：

- `install/install-commander.ps1`

```powershell
pwsh -NoLogo -File .\install\install-commander.ps1
```

如果目标目录已经存在，可以使用：

```powershell
pwsh -NoLogo -File .\install\install-commander.ps1 -BackupExisting
pwsh -NoLogo -File .\install\install-commander.ps1 -Force
```

说明：

- `-BackupExisting`：先备份旧目录，再安装新版本
- `-Force`：直接覆盖现有安装
- 普通用户路径只安装 `skills/commander-mode/`、`skills/commander-reuse-upgrader/` 和 `skills/execution-failure-guard/`，不会安装 `legacy/agent-runtime`

## 首次使用

安装完成后，先记住：

- 正式分发入口只有 `skills/commander-mode/`、`skills/commander-reuse-upgrader/` 和 `skills/execution-failure-guard/`
- `legacy/agent-runtime/` 只是归档，不参与安装和当前使用

可以用安装自检确认下一个窗口会读到最新 skill：

```powershell
python .\skills\commander-mode\scripts\verify_skill_install.py --repo . --codex-home "$env:USERPROFILE\.codex"
```

### 首次恢复顺序

进入一个项目后，推荐优先按这个顺序恢复：

1. 仓库根 `AGENTS.md`
2. 项目 `.codex/AGENT.md`
3. `.codex/docs/恢复入口.md`
4. `.codex/docs/当前状态.md`
5. `.codex/docs/当前任务.md`
6. `.codex/docs/验收记录.md`

如果 `当前任务.md` 明确写了 `当前任务形状=batch`，继续检查：

- `.codex/batch/<task-name>/`

### portable harness

```powershell
python .\skills\commander-mode\scripts\portable_harness.py --cwd . status
python .\skills\commander-mode\scripts\portable_harness.py --cwd . stop-gate
```

这个仓库只承载通用 skill。项目自己的任务记录和业务代码应该留在各自项目仓库。

如果你想给新项目套用统一结构，直接看：

- `skills/commander-mode/references/project-codex-layout.md`

### 同步长任务状态

当任务持续时间较长时，可以在关键节点把当前任务状态同步回 `.codex/docs/当前任务.md`：

```powershell
python .\skills\commander-mode\scripts\sync_current_task.py --repo . --event validate --validation-status "已验证" --validation-evidence "python -m pytest passed"
```

### 执行失败检查器

当一次命令、工具、测试、构建或环境调用失败并找到可用替代方法后，可以把 known-bad 与 use-instead 写入 `.codex/known-failures.json`：

```powershell
python .\skills\execution-failure-guard\scripts\known_failures.py --repo . add --id pwsh-path --match "pwsh -NoLogo" --known-bad "pwsh -NoLogo -Command ..." --fails-because "pwsh may be missing from the current tool process PATH" --use-instead '$env:Path = [Environment]::GetEnvironmentVariable(''Path'',''Machine'') + '';'' + [Environment]::GetEnvironmentVariable(''Path'',''User''); pwsh -NoLogo -Command ...' --scope "Windows tool process"
```

执行相似命令前先检查：

```powershell
python .\skills\execution-failure-guard\scripts\known_failures.py --repo . check --command "pwsh -NoLogo -Command Get-Date"
```

## 可选启用项目 `.codex` 记忆面

当 `commander-mode` 进入一个还没有 `.codex` 的仓库时，不要求先初始化模板。它会先从仓库已有的 README、docs、git 状态、测试、任务文件和用户目标恢复上下文。

只有当工作变成长任务、跨窗口任务、批量任务或多阶段项目治理时，才启用完整 `.codex` 记忆面。

默认骨架是**通用任务骨架**。系统只关心当前任务是什么，不预设任何特定场景。

### Bootstrap 新项目

```powershell
python .\skills\commander-mode\scripts\bootstrap_codex_workspace.py --repo .
```

如果明确要为当前仓库启用完整 `.codex` 记忆面，流程是：

1. 确认这是长期治理、批量任务或多阶段项目记忆需求
2. 执行标准 `.codex` bootstrap
3. 用 `当前任务.md` 进入当前任务模式

## 写回纪律

有意义的工作完成后，不要只停留在聊天里，至少应按需回写：

1. `当前任务.md`
   - 当前进度
   - 下一步
   - 验证状态
   - 验证证据
2. `当前状态.md`
   - 当前项目整体结论发生变化时更新
3. `验收记录.md`
   - 只有正式完成并有验证证据时才写入
4. `归档索引.md`
   - 当前任务降级、过期或退出主线时更新

不要把长聊天记录直接当成持久状态；磁盘上的项目文档才是恢复真相源。

## 高风险区

以下区域需要显式谨慎处理：

1. `~/.codex/skills/commander-mode`
   - 这是用户本地正式安装入口，覆盖前要先说明和备份策略。
2. 项目根 `AGENTS.md`
   - 它是仓库门牌文件，不应该被写成大而全的长期记忆仓库。
3. `.codex/` bootstrap 写入
   - 首次接入项目时，只能在用户确认后创建骨架。
4. `legacy/agent-runtime/`
   - 这是归档参考，不应再被当作当前实现、安装源或扩展目标。
