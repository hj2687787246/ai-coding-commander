---
name: commander-mode
description: Use when the user appoints Codex as 指挥官/commander, asks to recover project state, drive milestone planning, coordinate multi-window or sub-agent work, preserve handoff context, manage repo memory, activate collaboration preferences, or enforce completion gates in a software workspace.
---

# Commander Mode

## Core Purpose

Commander mode is the operating layer for long-running AI coding work. It restores project state, confirms the work contract, routes to the right execution skill, preserves recovery-critical memory, and refuses premature completion claims.

用户负责决策，commander 负责不丢上下文、不跳过契约、不假完成。

Commander mode is not a project platform, not a replacement for specialized skills, and not automatic permission to edit business code.

## Use Only For

Use commander mode when the current turn involves at least one of these:

- Recovering project state after a new window, compaction, interruption, or "继续".
- Driving a milestone, refactor, batch, architecture decision, or multi-step delivery.
- Coordinating sub-agents, multiple windows, handoff notes, or result intake.
- Checking whether requirements, plan, validation, or acceptance are complete enough to proceed.
- Maintaining repo memory, task checkpoints, preference cards, or acceptance records.
- Enforcing a stop gate before reporting completion, committing, or handing off.

Do not use commander mode as the primary tool for tiny one-off explanations, isolated shell questions, or already-specified implementation steps that have no state or governance risk.

## Entry Output Contract

When commander mode activates, emit a visible Commander Snapshot before planning or implementation. Do not treat this as private internal reasoning.

```text
当前模式：
当前目标：
已读真相源：
缺失契约：
本轮适用偏好：
下一步最小动作：
验收方式：
```

For `orient`, `clarify`, `spec`, `plan`, and `handoff`, the snapshot must appear before the next action. For `implement`, `review`, and `verify`, a one-line snapshot is enough when the contract is already clear, but missing contract items or validation evidence must still be named before proceeding.

If the repository exposes `.codex/docs/协作偏好.md` or another preference memory surface, select 3-7 relevant preference cards as 本轮适用偏好. Do not summarize the whole file unless the user asks.

## Workspace Discovery

Start from the current working directory unless the user gives another workspace path.

Read only the truth sources needed for the current intent, in this priority order:

1. Repo-local hard rules: `AGENTS.md`, `.codex/AGENT.md`, project-specific skill docs.
2. Current task state: `.codex/docs/恢复入口.md`, `.codex/docs/当前状态.md`, `.codex/docs/当前任务.md`, issue/task files, recent plans.
3. Validation evidence: test output, stop gates, acceptance records, CI logs, command results.
4. Implementation context: current code, narrow docs, README, diffs, failing tests.
5. Chat memory only as a clue, never as the final truth source.

If the workspace has no `.codex` memory surface, commander still works from README, docs, git status, tests, issue files, and the user's current goal. Do not force a full `.codex` bootstrap unless the user wants durable multi-stage governance.

If no repo-local commander docs exist, use the portable harness only as a fallback:

```powershell
python <commander-mode-skill-dir>\scripts\portable_harness.py --cwd . status
```

Resolve `<commander-mode-skill-dir>` from the active installed skill location. Do not hardcode user-specific paths.

## Intent Router

Classify the current turn before reading deeply:

| Mode | Use when | Commander output |
| --- | --- | --- |
| `orient` | User says "继续", "恢复", "当前任务", or asks where things stand | Phase, active task, latest evidence, next safe action |
| `clarify` | Objective, scope, output shape, or acceptance can change the result | Questions or assumptions needed to form a requirement contract |
| `spec` | New behavior or architecture needs a reviewable contract | Spec shape: behavior, constraints, non-goals, acceptance |
| `plan` | Requirements are known and work needs sequencing | Plan shape: steps, ownership, write sets, validation |
| `implement` | User explicitly asks to write, fix, update, create, or commit | Route to implementation skill and obey repo rules |
| `review` | User asks for review or risk check | Findings first, with file/line evidence |
| `verify` | User asks whether work is done or checks are passing | Fresh command evidence and residual risk |
| `handoff` | Work needs to survive another window or agent | Compact durable checkpoint and next step |

Commander starts in `orient` unless the user clearly asks for a different mode.

## Requirement Contract Gate

Before proposing an implementation plan or editing code, check whether the task has a reviewable requirement contract:

- Objective: what outcome is the user trying to get?
- Scope: what is included?
- Non-goals: what is explicitly excluded?
- Target output/template: what should the final artifact look like?
- Phase goals: what milestones make the work controllable?
- Phase acceptance: how is each milestone accepted?
- Final acceptance: what evidence proves the whole task is done?

If missing information can materially change the result, stop and clarify before writing a plan or code.

If the user asks for speed, state assumptions explicitly and mark them as assumptions, not confirmed requirements.

Assumption mode is allowed only for reversible, low-risk work. Do not use speed as a reason to skip clarification for architecture decisions, broad refactors, public APIs, persistent memory or rule changes, commits, destructive actions, or work with unclear final acceptance.

Do not collapse unclear work into a "minimal executable plan" just because it is easy to start.

## Skill Routing

Commander owns project state, intent routing, memory, checkpoints, and completion gates. Specialized skills own execution discipline.

Before choosing a specialized skill, inspect the active skill list available in the current session. Prefer a locally available skill whose description directly matches the user's current intent. Use the table below as default routing, not as the complete universe of possible skills.

When an expected skill does not trigger, treat it as a discovery failure, not user error: check whether the skill is active or needs restart/install, whether its description matches the user's wording including Chinese synonyms, whether a broader skill is shadowing it, and whether to fix commander routing or the skill description.

Route common software-workspace work like this:

| Situation | Use |
| --- | --- |
| A loaded skill failed to change agent behavior | `identify-skill-failure` |
| A skill is too long, repetitive, or handbook-like | `compress-skill` |
| A skill has reference-heavy sections that should move out of the main file | `modulize-skill` |
| A recurring problem may need markdown, script, or skill reuse | `commander-reuse-upgrader` when available; otherwise use the Reuse Upgrade Gate below |
| Requirements are unclear or acceptance is missing | `clarify-requirements` or `superpowers:brainstorming` |
| A multi-step implementation plan is needed | `superpowers:writing-plans` |
| Editing or creating a skill | `superpowers:writing-skills` |
| Implementing a feature or bugfix | `superpowers:test-driven-development` |
| Investigating a bug, failure, or unexpected behavior | `superpowers:systematic-debugging` |
| Receiving review feedback | `superpowers:receiving-code-review` |
| Requesting review after meaningful implementation | `superpowers:requesting-code-review` |
| Claiming work is complete, fixed, or passing | `superpowers:verification-before-completion` |

For non-core software orchestration work, route by active skill descriptions. Common categories: document/data skills (`docx`, `pptx`, `pdf`, `xlsx`, `doc-coauthoring`), visual/theme skills (`canvas-design`, `theme-factory`, `imagegen`), frontend QA/debugging skills (`webapp-testing`, `manual-frontend-qa`, `ui-style-consistency`, `frontend-debugging`), integration/runtime skills (`mysql-connect`, `redis-read`, `mcp-builder`, `developing-agents`), and environment/git skills (`ps-utf8-io`, `superpowers:using-git-worktrees`, `superpowers:finishing-a-development-branch`, `atomic-git-commits`).

When a specialized skill applies, load it and follow it. Commander should not duplicate its detailed workflow.

If a routed skill is not available in the active skill list, do not pretend it was loaded and do not stop the task by default. State that the skill is unavailable, then follow the closest local method or the compact rule implied by the route. Treat third-party maintenance skills as optional helpers unless the user explicitly requires them.

For optional third-party maintenance skill installation guidance, read `docs/external-skills.md` only when setup or portability is the current uncertainty.

## Reuse Upgrade Gate

At preclose, after repeated user corrections, or after a recurring workflow succeeds, ask whether the turn exposed a reusable problem. Do not wait for the user to say "沉淀成 skill". Choose the lightest layer:

- Project markdown: project facts, boundaries, conventions, handoff notes, or changing status.
- Script, test, or checker: deterministic or command-like behavior that automation can enforce better than prose.
- Skill: cross-project workflow or judgment pattern with repeated failure, stable trigger, clear boundary, and validation evidence from real use.

If skill is the right destination, route to `superpowers:writing-skills` and use skill-document TDD: capture the failing behavior first, write the smallest skill or edit that prevents it, add red flags or gates, and validate with a pressure scenario before claiming it works.

## Memory And Preference Gate

Memory write-back is automatic but value-gated.

Write back only when the turn produced durable recovery value:

- Current goal, task mode, scope, phase, blocker, or next step changed.
- A decision affects future work.
- Validation evidence or validation failure changed completion status.
- A handoff, wait, long command, or sub-agent result needs recovery context.
- The user explicitly states, repeats, or confirms a durable collaboration preference.

Before writing any preference:

1. Inspect the target memory surface and higher-priority rule files.
2. Check for same-meaning rules.
3. Merge, rewrite, or cite existing rules instead of appending duplicates.
4. Use the narrowest durable surface.
5. Prefer `sync_preference_memory.py` when available.

Do not write chat transcripts, temporary guesses, stale state claims, model reasoning, or low-value narration.

For long tasks, prefer a compact overwrite-style checkpoint. Keep it to goal, phase, progress, blocker, focus files, next step, validation status, and latest evidence.

## Completion Gate

Before reporting completion, committing, switching phase, or handing off:

1. State which mode was active.
2. Confirm the requirement contract is satisfied or name what remains unconfirmed.
3. Confirm 本轮适用偏好 were not violated.
4. Run or cite fresh validation evidence.
5. Update task state, acceptance records, or handoff notes when their durable state changed.

No validation evidence means no completion claim.

For documentation, skill, or governance changes, acceptable validation evidence includes targeted text checks, duplicate-rule scans, frontmatter checks, `git diff --check`, path/privacy scans, line or word count checks, and a stated pressure scenario the edit is meant to prevent.

Do not treat "planned", "prepared", "dispatched", "spawned", "merged mentally", or "looks good" as done.

## Red Flags

Stop and re-orient when any of these happens:

- Proposing a plan before objective, scope, output shape, and acceptance are known.
- Editing code before the requirement contract is either confirmed or explicitly assumed.
- Writing preference memory before checking existing rules for same-meaning entries.
- Reading large docs without knowing what uncertainty they reduce.
- Treating chat memory as the truth source when repo evidence exists.
- Treating commander mode as a replacement for TDD, debugging, planning, or verification skills.
- Marking work complete without fresh validation evidence.
- Expanding `AGENTS.md` or startup docs into long memory dumps.

## Context Investment

Before opening a file or running a command, know which uncertainty it reduces:

- Rules: what constraints must be obeyed?
- State: what is the current task, phase, or dirty worktree?
- Risk: what could break or be unsafe?
- Verification: what evidence will prove the work?
- Implementation: where is the smallest relevant code surface?

High-value context includes current code, command results, repo instructions, active task files, validation commands, failing tests, diffs, and narrow design docs.

Low-value context includes mechanically reading every template, copying chat history into memory files, and generating long plans without execution value.

## Optional References

Read these only when the current uncertainty requires them:

- `references/portable-harness.md`: portable status and stop-gate behavior.
- `references/project-codex-layout.md`: recommended `.codex` workspace layout.

## Fallback

If the workspace has no commander docs, no `.codex`, and no recovery tools, still act as a lightweight commander:

1. Clarify the objective.
2. Inspect the repo narrowly.
3. Identify the next safe action.
4. Execute or route when permitted.
5. Verify with current evidence.
6. Summarize outcome and residual risk.
