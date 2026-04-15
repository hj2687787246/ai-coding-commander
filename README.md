# AI Coding Commander

通用 AI coding 指挥官 skill 的独立承接仓库。

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

当前本机可以用 junction 暴露到 Codex skills：

```powershell
cmd /c mklink /J "%USERPROFILE%\.codex\skills\commander-mode" "D:\Develop\Python-Project\ai-coding-commander\skills\commander-mode"
```

如果目标目录已存在，先确认它是否是旧副本，再决定是否替换。

## portable harness

```powershell
python D:\Develop\Python-Project\ai-coding-commander\skills\commander-mode\scripts\portable_harness.py --cwd . status
python D:\Develop\Python-Project\ai-coding-commander\skills\commander-mode\scripts\portable_harness.py --cwd . stop-gate
```

这个仓库只承载通用 skill。项目自己的学习路线、任务记录和业务代码应该留在各自项目仓库。

如果你想给新项目套用统一结构，直接看：

- `skills/commander-mode/references/project-codex-layout.md`
