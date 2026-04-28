# Portable Harness

Use this reference when a repository does not have its own commander runtime but still needs harness-like behavior.

## What It Provides

The portable harness is an on-demand script bundled with `commander-mode`. It is not a daemon and does not require copying `commander/` into the target repository.

The harness is a sensor for `commander-mode`, not the product center. Use it to quickly discover repo state, validation hints, dirty worktree status, and existing memory surfaces before deciding how much context to invest.

It provides:

1. Workspace discovery from any git repository.
2. Instruction-file detection such as `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, and README files.
3. Project marker detection for Python, Node, Go, Rust, Make, and tests.
4. Commander 协议初始化探测。
5. Validation command suggestions.
6. A generic stop gate that blocks completion when the worktree is dirty and no validation evidence is supplied.

## Commander Protocol Detection

`status` 命令现在会返回 `commander_protocol` 字段：

- `initialized`: 当前仓库是否已经接入项目内 commander 协议
- `markers`: 用来判定已初始化的最小证据列表

判定规则：

1. 存在 `.codex/AGENT.md`
2. 存在 `.codex/docs/当前状态.md`
3. 仓库根 `AGENTS.md` 明确把 `.codex/AGENT.md` 作为入口之一

这层探测只负责判断“当前项目有没有自己的 commander 协议”，不负责决定当前任务类型。

## Commands

Run from any workspace:

```powershell
python C:\Users\26877\.codex\skills\commander-mode\scripts\portable_harness.py --cwd . status
```

Run a generic stop gate:

```powershell
python C:\Users\26877\.codex\skills\commander-mode\scripts\portable_harness.py --cwd . stop-gate
```

Allow dirty completion only when validation evidence exists:

```powershell
python C:\Users\26877\.codex\skills\commander-mode\scripts\portable_harness.py --cwd . stop-gate --validation "python -m pytest passed"
```

## Limits

This does not replace a repo-native harness. It cannot know project-specific acceptance, ownership, or task state unless the repository exposes those facts through docs, issue trackers, scripts, or a project skill.

If a repository needs stricter behavior, add a project skill and repo-local scripts, then let `commander-mode` prefer those repo-native checks over the portable fallback.
