# Commander 分享与安装设计

更新时间：2026-04-17

## 目标

把 `ai-coding-commander` 仓库整理成一个可分享给他人的 commander skill 发布源，同时支持两条使用路径：

1. 开发者路径
2. 普通用户路径

这两条路径都以 `skills/commander-mode/` 作为唯一正式分发入口，不再把 `legacy/agent-runtime/` 暴露给使用者。

## 非目标

- 不把整个仓库包装成独立安装器平台
- 不引入新的运行时守护进程
- 不要求用户安装旧 `Agent/commander` runtime
- 不让使用者直接理解 `legacy/` 目录

## 当前正式分发边界

当前主线只认：

1. `skills/commander-mode/`
2. `skills/commander-mode/scripts/portable_harness.py`
3. `skills/commander-mode/scripts/bootstrap_codex_workspace.py`

其余内容分工如下：

- `references/`：使用说明与标准模板
- `docs/superpowers/specs/`：设计文档
- `docs/superpowers/plans/`：实施计划
- `legacy/agent-runtime/`：只读归档，不参与当前安装与使用

## 对外使用者分层

### 1. 开发者路径

适用对象：

- 会 `git clone`
- 会运行 `pwsh` / Python
- 可以接受 junction 或本地路径调用

目标体验：

- clone 仓库
- 选择复制目录或 junction
- 直接开始使用 `commander-mode`
- 可直接修改源码并验证效果

### 2. 普通用户路径

适用对象：

- 不想理解仓库结构
- 希望一条脚本完成安装
- 只关心把 commander 技能装到本地 `~/.codex/skills`

目标体验：

- clone 仓库
- 跑一个 `pwsh` 安装脚本
- 脚本自动把正式 skill 安装到本地 Codex skills 目录
- 提示首次使用方法

## 安装策略

### 开发者路径

提供两种方式：

1. 复制目录
2. junction

推荐在 README 中明确：

- 普通开发使用可直接复制 `skills/commander-mode/`
- 想持续跟踪仓库源码时，用 junction 更方便

### 普通用户路径

默认采用：

**复制目录**

原因：

- 最稳
- 不依赖链接权限
- 不要求用户理解 junction / symlink
- 安装后与源码仓库解耦

如果检测到当前场景更像本地开发环境，可以在安装脚本输出里提示：

- 可选使用 junction，便于后续同步仓库改动

但这不是默认行为。

## 目标仓库结构

```text
ai-coding-commander/
  README.md
  install/
    install-commander.ps1
  skills/
    commander-mode/
      SKILL.md
      scripts/
      references/
  docs/
    superpowers/
      specs/
      plans/
  legacy/
    agent-runtime/
```

## README 需要承载的内容

README 需要同时服务两类用户，所以结构建议为：

1. 这是什么
2. 当前正式分发边界
3. 环境要求
4. 开发者安装方式
5. 普通用户安装方式
6. 首次使用演示
7. 已初始化 / 未初始化项目的行为
8. 常见问题

## 安装脚本职责

建议新增：

- `install/install-commander.ps1`

职责：

1. 检查 `pwsh` / PowerShell 7 环境
2. 检查 Python 是否可用
3. 检查目标 `~/.codex/skills/commander-mode` 是否已存在
4. 默认把 `skills/commander-mode/` 复制到目标目录
5. 如果目标已存在，给出：
   - 覆盖
   - 备份后覆盖
   - 取消
6. 安装完成后输出首次使用说明

## 首次使用说明

安装完成后，脚本至少应输出：

1. skill 已安装位置
2. 如何在新项目里调用 `commander-mode`
3. 如何使用 `portable_harness.py` 检查项目状态
4. 如何在未初始化项目里 bootstrap 标准 `.codex` 骨架

## 行为边界

对外必须明确：

- `commander-mode` 识别的是当前项目自己的 `.codex` 协议
- 学习模式只是某个项目里的任务模式之一
- 新项目默认初始化的是通用任务导向骨架，不是学习模板
- `legacy/agent-runtime` 不需要安装，不参与当前使用

## 推荐的对外表述

对外更适合把这个仓库描述为：

**“可安装的 commander skill 仓库，提供 portable harness 和项目内 `.codex` bootstrap 协议。”**

不建议对外描述成：

- 多 agent runtime 平台
- 通用守护进程系统
- 旧 `Agent/commander` runtime 的延续

## 验收标准

### 开发者路径通过标准

1. 使用者 clone 仓库后，可以通过复制目录或 junction 暴露 `commander-mode`
2. 可以直接运行：
   - `portable_harness.py --cwd . status`
   - `portable_harness.py --cwd . stop-gate`
3. 可以在新项目里运行 `.codex` bootstrap

### 普通用户路径通过标准

1. 使用者运行 `install/install-commander.ps1`
2. 脚本能把 `skills/commander-mode/` 安装到本地 `~/.codex/skills/commander-mode`
3. 安装后能通过新会话发现该 skill
4. README 与安装脚本输出一致，不出现双入口或旧 runtime 误导

## 后续实施建议

推荐实施顺序：

1. 先更新 README，补足对外分享结构
2. 再新增 `install/install-commander.ps1`
3. 最后补最小安装验证或演示说明

