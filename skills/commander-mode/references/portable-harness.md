# Portable Harness

Use this reference when a repository does not have its own commander runtime but still needs harness-like behavior.

## What It Provides

The portable harness is an on-demand script bundled with `commander-mode`. It is not a daemon and does not require copying `commander/` into the target repository.

It provides:

1. Workspace discovery from any git repository.
2. Instruction-file detection such as `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, and README files.
3. Project marker detection for Python, Node, Go, Rust, Make, and tests.
4. Validation command suggestions.
5. A generic stop gate that blocks completion when the worktree is dirty and no validation evidence is supplied.

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
