# Project Workspace Guide

## 最重要

- Always reply in Chinese.
- 除非用户明确要求英文，否则默认使用简体中文。
- 代码标识符、命令、日志、报错信息保持原始语言；其余解释用中文。

## 仓库入口

1. `.codex/AGENT.md`
2. `README.md`

## Commander 持久启用

- 如果 `.codex/commander-active.json` 存在且 `active=true`，恢复、继续、压缩后重开或进入长任务时先使用 `commander-mode`。
- 这个标记只代表 commander 治理处于启用态，不代表可以跳过需求、计划、验证或用户授权边界。

## 仓库边界

- 根目录 `AGENTS.md` 只保留仓库身份、第一跳入口和高风险边界。
- 项目内 commander 协议统一落在 `.codex/`。
