# AI Coding Commander

通用 AI coding 指挥官 skill 的独立承接仓库。

## 当前主线

当前活跃实现只认：

1. `skills/commander-mode/`
2. `skills/commander-mode/scripts/portable_harness.py`
3. `skills/commander-mode/scripts/bootstrap_codex_workspace.py`

`legacy/agent-runtime/` 仅作归档参考，不参与当前实现，不作为当前安装源、恢复入口或扩展目标。

目标：

1. 提供跨仓库可用的 `commander-mode` skill。
2. 提供最小 portable harness：状态扫描和 stop gate。
3. 不依赖 `D:\Develop\Python-Project\Agent` 仓库里的 `commander/` runtime。

另外，这个仓库也提供一套推荐的**项目内 `.codex` 工作区布局**，用于把：

1. 全局可复用 skill
2. 项目专属 Codex 规则
3. 项目正文文档
4. MCP 资源理解边界

这几层清晰分开，而不是继续把项目学习计划、AI 协作规则和业务文档混在同一层里。

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

复制到本地：

- `~/.codex/skills/commander-mode`

#### 方式 B：junction

如果你希望本地 skills 始终直接指向仓库源码，可以用 junction：

```powershell
pwsh -NoLogo -Command "cmd /c mklink /J \"$env:USERPROFILE\\.codex\\skills\\commander-mode\" \"D:\Develop\Python-Project\ai-coding-commander\skills\commander-mode\""
```

### 普通用户

适合：

- 不想理解仓库结构
- 只想把 commander-mode 装进本地 Codex skills

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
- 普通用户路径只安装 `skills/commander-mode/`，不会安装 `legacy/agent-runtime`

## 首次使用

安装完成后，先记住：

- 正式分发入口只有 `skills/commander-mode/`
- `legacy/agent-runtime/` 只是归档，不参与安装和当前使用

### portable harness

```powershell
python D:\Develop\Python-Project\ai-coding-commander\skills\commander-mode\scripts\portable_harness.py --cwd . status
python D:\Develop\Python-Project\ai-coding-commander\skills\commander-mode\scripts\portable_harness.py --cwd . stop-gate
```

这个仓库只承载通用 skill。项目自己的学习路线、任务记录和业务代码应该留在各自项目仓库。

如果你想给新项目套用统一结构，直接看：

- `skills/commander-mode/references/project-codex-layout.md`

## 初始化新项目的 `.codex` 协议

当 `commander-mode` 进入一个还没有 `.codex` 协议的仓库时，正确流程应该是：

1. 先识别当前项目为未初始化项目
2. 提议创建标准 `.codex` 骨架
3. 等用户确认后再创建
4. 创建完成后，用 `当前任务.md` 进入当前任务模式

默认骨架是**任务导向**的，不是学习导向的。学习模式只是项目里的一种任务模式，不是 commander 系统的默认模板。

### Bootstrap 新项目

```powershell
python D:\Develop\Python-Project\ai-coding-commander\skills\commander-mode\scripts\bootstrap_codex_workspace.py --repo .
```

当 `commander-mode` 识别到当前仓库还没有 `.codex` 协议时，正确行为应该是：

1. 先识别为未初始化项目
2. 提议创建标准 `.codex` 骨架
3. 等用户确认后再执行 bootstrap
4. 用 `当前任务.md` 进入当前任务模式
