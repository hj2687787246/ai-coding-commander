# Workspace Routing

Use this reference when entering or recovering the Agent repository.

## Purpose

This repository is a sweeping-robot customer-service Agent project. The current goal is not to build a universal multi-agent platform. The goal is to keep a repo-native AI coding harness that makes status, write boundaries, validation, and handoff visible.

## Read Order

For commander or architecture work:

1. `AGENTS.md` for routing only.
2. `commander/core/任命.md` for commander role boundaries.
3. `.\.venv\Scripts\python.exe -m commander.transport.scripts.commander_task_catalog --summary --limit 3` for compact active-task recovery.
4. `commander/core/主文档.md` only when the task needs the stable commander-system background.
5. `commander/outer/指挥官outer文档状态索引.md` when confused about which `outer` docs are active, historical, or backlog.

For execution work:

1. `README.md`.
2. `commander/outer/agent_workbench.md`.
3. `commander/transport/prompts/execution_window_task_template.md`.
4. Task-specific files from the packet, issue, or user request.

## Context Budget

- Prefer `rg`, `Select-String -Context`, and small `Get-Content | Select-Object -First/-Skip` reads.
- Do not bulk-read `commander/core/*.md`, `commander/state/*.md`, long tests, or large `outer` documents unless the task is blocked without them.
- If the compact task catalog and stop gate already identify the current phase and next action, continue from that evidence instead of replaying history.

## Validation

Use the narrowest validation that covers the change:

- Basic local self-check: `powershell -ExecutionPolicy Bypass -File .\scripts\self_check.ps1`
- Regression self-check: `powershell -ExecutionPolicy Bypass -File .\scripts\self_check.ps1 -IncludeRegression`
- Delivery checks: `.\.venv\Scripts\python.exe scripts\run_delivery_checks.py`
- Heavy regression: `.\.venv\Scripts\python.exe scripts\run_regression_suite.py --smoke --include-multi-turn --fail-on-mismatch`
- Commander stop gate: `.\.venv\Scripts\python.exe -m commander.transport.scripts.commander_stop_gate`

## Protected Local Files

Do not touch these unless the user explicitly asks and the reason is task-critical:

- `config/auth.local.yml`
- `config/auth.yml.codex-real-integration.bak`
- `config/rag.yml`
- `web/tsconfig.node.tsbuildinfo`
- `.pytest_tmp*`
