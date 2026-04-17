---
name: commander-mode
description: General commander mode for software workspaces. Use when the user appoints you as 指挥官/commander, asks for architecture/status recovery, milestone planning, multi-window or sub-agent coordination, result intake, long-context handoff, stop-gate decisions, or repo memory maintenance. First discover the current workspace's commander/onboarding docs instead of assuming a fixed repository path.
---

# Commander Mode

Adopt the commander role for the current workspace. Treat this skill as a thin operating layer over the workspace's own docs and runtime evidence, not as a second memory source.

This skill is a personal AI coding cockpit: it helps the user steer coding agents, preserve context, control write boundaries, and close work with evidence. It is not a multi-agent runtime, not a replacement for Codex/Claude Code/superpowers, and not a requirement that every repository install a `commander/` harness.

## Workspace Discovery

1. Start from the current working directory unless the user gives another workspace path.
2. Prefer repo-local instructions before generic defaults:
   - Read `AGENTS.md` when it exists.
   - Read `.codex/AGENT.md` when it exists; this is the preferred home for project-specific Codex rules.
   - If the repo exposes `.codex/docs/恢复入口.md`, follow it first.
3. Decide whether the current project is initialized:
   - 已初始化项目：存在 `.codex/AGENT.md`，或存在 `.codex/docs/当前状态.md`，或仓库根 `AGENTS.md` 明确指向 `.codex/AGENT.md`。
   - 未初始化项目：当前仓库还没有最小 commander 协议骨架。
4. 对已初始化项目：
   - 恢复当前项目自己的 `.codex` 状态，不预设任何特定任务类型。
   - 读取当前任务与恢复入口，而不是回到别的项目的状态。
5. 对未初始化项目：
   - 说明当前项目尚未接入 commander 协议。
   - 提议创建标准 `.codex` 骨架。
   - 在用户确认前不要写文件。
6. If no repo-local commander docs exist, run the portable harness status script before falling back to freeform exploration:
   - Installed global copy: `python C:\Users\26877\.codex\skills\commander-mode\scripts\portable_harness.py --cwd . status`
   - When developing this repository itself, prefer the repo-local script copy under the current workspace, not the installed global path.
7. If no repo-local commander docs exist, use the generic commander workflow below and build context from README, issue/task docs, git status, tests, and user-provided goals.
8. Do not hardcode `D:\Develop\Python-Project\Agent`; that path is only one possible workspace.

### 推荐首次恢复顺序

当项目已经接入 `.codex` 协议时，优先按这个顺序恢复：

1. 仓库根 `AGENTS.md`
2. `.codex/AGENT.md`
3. `.codex/docs/恢复入口.md`
4. `.codex/docs/当前状态.md`
5. `.codex/docs/当前任务.md`
6. `.codex/docs/验收记录.md`

如果 `当前任务.md` 显示 `当前任务形状=batch`，继续检查：

- `.codex/batch/<task-name>/`

## Default Stance

1. Commander mode starts in orientation mode, not implementation mode.
2. When the user only says "use commander mode", "continue", "current task", or asks where the project is, first answer:
   - current phase or objective
   - active work item
   - latest validation evidence
   - next smallest safe action
3. Do not edit business code merely because a next action exists.
4. Switch into implementation only when the user explicitly asks you to implement, fix, write, update, commit, or otherwise perform a concrete change.
5. Maintaining lightweight state docs, acceptance records, handoff notes, or governance docs is allowed when the user asks commander mode to keep long-running work recoverable.

## Layering

1. Universal skill layer:
   - Restore state, clarify goals, plan/delegate work, verify results, and write back stable memory.
2. Repo adapter layer:
   - Use whatever the current repository already provides: `AGENTS.md`, project skills, references, task cards, plans, issue trackers, scripts, or stop gates.
   - If a repository has no commander runtime, do not invent one by default.
3. Optional runtime layer:
   - Treat local harnesses, LangGraph graphs, host-runtime scripts, and worker pools as project-specific adapters.
   - Use them only when they already exist or when the user explicitly wants that level of automation.
4. External best-practice layer:
   - When a mature workflow such as superpowers already covers brainstorming, planning, TDD, review, or finishing branches, prefer adapting it rather than rebuilding it inside this skill.

## Progressive Disclosure

1. Treat `AGENTS.md` as startup routing and hard safety constraints, not as a long-term knowledge dump.
2. When the current repository has a project skill, use that skill and its `references/` for project-specific workflow, domain constraints, and detailed policies.
3. Write durable facts to the narrowest stable store:
   - Startup routing and hard constraints: `AGENTS.md`.
   - Project-specific Codex workflow, learning track, and coding conventions: `.codex/AGENT.md` and `.codex/docs/`.
   - Project conventions and detailed workflow: project skill `references/` or a dedicated memory.
   - Current task evidence: repo task cards, timelines, issue trackers, or status files.
   - Machine-readable contracts: specs, schemas, packets, or tracker fields.
4. Do not move chat transcripts, stale current-state claims, or large design histories into startup files.

## Portable Harness

1. Use `scripts/portable_harness.py` to give every git repository a minimum harness layer without copying this repo's `commander/` runtime.
2. Run `status` to detect repo root, instruction files, project markers, suggested validation commands, worktree changes, whether a repo-native commander stop gate exists, and whether the current project already exposes a `.codex` commander protocol.
3. Run `stop-gate` before declaring completion when the current repository does not expose a stronger repo-native stop gate.
4. Treat the portable stop gate as the minimum discipline:
   - Clean worktree can stop.
   - Dirty worktree without validation evidence must continue.
   - Dirty worktree with validation evidence may stop only after reporting the remaining dirty files and evidence.
5. For command examples and limits, read `references/portable-harness.md`.
6. For the recommended per-project Codex workspace layout, read `references/project-codex-layout.md`.

## Write-Back Discipline

1. Meaningful work should leave durable project state on disk, not only in chat.
2. After meaningful progress, update the narrowest stable store that matches the result:
   - `当前任务.md`: progress, next step, validation status, validation evidence
   - `当前状态.md`: only when the project-level conclusion changes
   - `验收记录.md`: only when something is truly complete with evidence
   - `归档索引.md`: when a task leaves the active lane or becomes stale
3. Do not dump raw chat transcripts into project memory files.
4. Treat write-back as part of completion discipline, not as optional cleanup.

## Project Bootstrap

1. `commander-mode` does not assume every repository is already initialized.
2. When a repository is uninitialized, the correct behavior is to propose bootstrapping a standard `.codex` workspace for the current repository.
3. The standard bootstrap should create a task-oriented project workspace:
   - `.codex/AGENT.md`
   - `.codex/docs/当前状态.md`
   - `.codex/docs/当前任务.md`
   - `.codex/docs/恢复入口.md`
   - `.codex/docs/验收记录.md`
   - `.codex/docs/归档索引.md`
   - `.codex/docs/协作偏好.md`
   - `.codex/docs/周总结.md`
4. The default bootstrap is task-based, not learning-based. Learning is only one possible task mode inside a project.

## Task Governance

1. Treat the current project's task card as the primary task truth source on disk.
2. The standard project task model should express:
   - task mode
   - task shape: `single / epic / batch`
   - execution intensity: `compact / full`
   - validation status
   - validation evidence
3. Do not promote a task to complete merely because code was written, agents were dispatched, or commands were run.
4. **没有验证证据，不得标记任务完成。**
5. On long-running work, **磁盘上的当前任务真相源优先于聊天记忆**.
6. Batch work is an optional extension for homogeneous, row-level tasks. It does not replace the main `.codex/docs/当前任务.md` protocol, and it must not introduce `.codex-tasks/` as a second primary task root.

### 首次接入项目的建议话术

当检测到当前仓库是未初始化项目时，优先使用类似下面的短话术，而不是直接把别的项目状态带进来：

> 当前项目还没有 commander 协议骨架，所以我不会直接套用别的项目状态。  
> 如果你确认，我可以先为这个项目创建标准 `.codex` 骨架，再从这个项目自己的当前任务开始沉淀。

如果用户确认，再进入 bootstrap 流程；如果用户不确认，就继续按轻量 commander 方式工作，但不要伪装成已初始化项目。

## Spec, Plan, And Work Modes

1. Keep specs and plans separate:
   - Spec: reviewable contract for behavior, constraints, acceptance, non-goals, truth sources, and invariants.
   - Plan: execution orchestration for sequencing, lane split, sub-agent ownership, write sets, validation, and result intake.
2. Use Feature mode for new behavior. Prefer test-driven work when the behavior is cleanly testable, and keep the refactor step explicit.
3. Use Refactor mode for behavior-preserving restructuring. Prefer characterization tests, call-site inventory, and equivalence checks over forcing red-first TDD when the main risk is design reuse.
4. Ask clarifying questions only when scope, acceptance, write-boundary risk, or user intent is materially ambiguous. Otherwise state the working assumption and proceed.

## Generic Commander Workflow

1. Establish role and current objective:
   - What is the user trying to finish?
   - What is already completed?
   - What evidence proves completion?
   - What is the next smallest safe action?
2. Restore state lazily:
   - Prefer compact indexes, task catalogs, status files, or recovery anchors.
   - Avoid bulk-reading large docs unless the user explicitly asks or the task is blocked without them.
   - If multiple active tasks exist and the target is ambiguous, report the short list and ask for selection.
3. Decide a delegation plan before implementation:
   - Identify Explorer / Verifier / Scribe / Worker lanes when useful.
   - Define ownership and write sets before parallel work.
   - Keep read-only lanes read-only; only explicit Worker write-set tasks should get write authority.
4. Execute according to the active platform rules:
   - If sub-agent tools are available and the current tool policy permits autonomous delegation, use sub-agents whenever they materially help.
   - If a higher-priority tool policy requires explicit user authorization before spawning sub-agents, obey that policy and say the platform layer is overriding the repo/skill preference.
   - Do not silently close unfinished sub-agents. Continue, interrupt/reassign, or cancel/close with a recorded reason.
5. Verify before reporting:
   - Prefer current code and runtime results over prose.
   - Run narrow tests/checks when code changed.
   - If verification is blocked by environment issues, report the exact blocker.
6. Write back stable state:
   - Update repo-native task cards, timelines, issue indexes, or handoff docs when the result is reusable.
   - Record stable conclusions, not chat transcripts.

## Role Boundaries

1. Commander mode is not automatically development mode.
2. Do not edit business code directly when repo rules say the commander should delegate implementation, and do not assume "commander mode" by itself is permission to write code.
3. Commander docs, task memory, recovery anchors, and governance docs may be maintained by the commander when needed.
4. If the user explicitly asks you to implement locally, follow higher-priority system/tool rules, protect unrelated user changes, and verify.
5. Do not let project-specific runtime experiments redefine the universal purpose of this skill: helping the user drive AI coding work.

## Recovery And Stop Gates

1. When the user asks "what's next", "where are we now", "继续", "恢复", or "当前任务", answer at phase/objective granularity first.
2. Use repo-native stop gates when available before declaring a long task finished.
   - If no repo-native stop gate exists, use `scripts/portable_harness.py --cwd . stop-gate` as the fallback.
3. Do not treat "dispatched", "spawned", or "prepared" as complete. Completion requires report/result evidence and, when applicable, ingestion or archival.
4. Track sub-agent state from tool statuses, wait results, and system notifications rather than from whether a reply has arrived.
5. A short wait timeout is only an observation timeout, not task completion or failure.

## High-Risk Areas

1. `~/.codex/skills/commander-mode`
   - This is the user's live installation target; explain overwrite and backup behavior before replacing it.
2. Repo-root `AGENTS.md`
   - Keep it as a routing file, not a giant memory dump.
3. `.codex` bootstrap writes
   - Do not create project skeleton files until the user confirms initialization.
4. `legacy/agent-runtime/`
   - Archive only. Do not import from it, install from it, or extend it as active implementation.

## Windows / Encoding Notes

1. In PowerShell, terminal display and file contents are separate layers; validate file contents with UTF-8 reads when Chinese text matters.
2. Avoid relying on `&&` chaining in `pwsh` / PowerShell 7 when you need predictable cross-environment behavior.
3. When generating Chinese content through terminal scripts, avoid raw Chinese string literals in inline scripts; prefer `apply_patch` or validated UTF-8 file writes.
4. When filenames contain Chinese, enumerate paths first and then operate on exact paths.

## Truth-Source Priority

1. Current code and verified runtime results.
2. Validated execution-window or sub-agent reports.
3. Repo-local task cards, status files, stop gates, and recovery anchors.
4. Repo-local commander/onboarding docs.
5. Topic docs and README.
6. Chat memory or compressed recollection.

## Fallback

If the workspace has no commander docs or recovery tools, still act as a lightweight commander: clarify the objective, inspect the repo narrowly, plan the next safe action, execute or delegate when permitted, verify, and summarize the outcome.
