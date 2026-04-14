---
name: agent-workspace
description: Project skill for D:\Develop\Python-Project\Agent, a sweeping-robot customer-service Agent workspace. Use when working inside this repository, when handling its commander harness, repo-native task/status recovery, spec vs plan separation, feature/refactor mode selection, or project-specific validation and write-boundary rules.
---

# Agent Workspace

Use this skill as the project adapter for the Agent repository. Keep this file lean: load references only when the current task needs them.

## Start Here

1. Treat `AGENTS.md` as a routing page, not as project memory.
2. Use repo evidence before chat memory: current code, task catalog, stop gate, task card, timeline.
3. Do not copy external harness skeletons such as `plans/`, `memory/`, `reports/`, or `debt` into this repo.
4. Keep `commander-mode` as the generic cockpit skill; keep this skill as the Agent repo adapter.

## References

- Read `references/workspace-routing.md` when starting work in this repo, recovering status, or choosing validation commands.
- Read `references/spec-plan-contract.md` when the task mentions spec, plan, SDD, orchestration, subagents, dispatch, or task packets.
- Read `references/work-modes.md` before choosing Feature, Refactor, Debug, Review, or Documentation mode.
- Read `references/commander-harness-boundaries.md` when deciding whether to keep, freeze, migrate, or delete commander harness components.

## Writeback Rule

Write stable project knowledge to the narrowest durable place:

1. Startup routing and hard safety constraints: `AGENTS.md`.
2. Project workflow and conventions: this skill's `references/`.
3. Current task state and completion evidence: `commander/state/`.
4. Historical design status: `commander/outer/` plus `commander/outer/指挥官outer文档状态索引.md`.
5. Machine-readable contracts: `commander/specs/` or transport schemas.
