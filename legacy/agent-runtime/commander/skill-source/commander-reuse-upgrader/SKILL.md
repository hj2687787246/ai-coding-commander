---
name: commander-reuse-upgrader
description: Route recurring Agent workspace problems into the right reuse layer. Use when a repeated question or workflow in `D:\Develop\Python-Project\Agent` needs to be classified as repo markdown, executable script, or a lightweight local skill, and when Codex must read the repo markdown truth sources first instead of relying on chat memory.
---

# Commander Reuse Upgrader

## Overview

Adopt a thin reuse-upgrade workflow for the Agent workspace. Treat this skill as a routing shell over the repo docs and optional local tools, not as a second project memory source.

## Core workflow

1. Read the repo markdown truth sources before deciding anything:
   - `D:\Develop\Python-Project\Agent\docs\复用问题沉淀与Skill升级协议.md`
   - `D:\Develop\Python-Project\Agent\commander\core\任命.md`
   - `D:\Develop\Python-Project\Agent\commander\state\当前任务卡.md`
   - `D:\Develop\Python-Project\Agent\commander\state\问题索引.md`
   - `D:\Develop\Python-Project\Agent\commander\outer\新窗口启动指令模板.md` when the task affects future execution windows
2. Rebuild the current facts from those markdown files instead of relying on prior chat context.
3. Classify the repeated problem into one of three destinations:
   - markdown doc
   - executable script
   - lightweight local skill
4. Prefer the lightest destination that preserves truth and repeatability.
5. After changing docs, scripts, or a skill, validate the result before claiming it is complete.

## Routing rules

### Keep it in markdown when

1. The main value is preserving project facts or boundaries.
2. The answer changes with project state and must stay close to repo truth sources.
3. The issue is mainly a recurring explanation, rule, or handoff convention.

### Upgrade to a script when

1. The same commands or checks are repeated often.
2. Deterministic execution matters more than prose guidance.
3. The action is error-prone when done manually.

### Upgrade to a skill when

1. The problem appears repeatedly.
2. The trigger is stable and recognizable.
3. The reusable part is the workflow, not the project facts.
4. Validation evidence already exists from real usage.
5. The boundary is clear: the skill routes and reminds, but does not become a second memory layer.

## Constraints

1. Do not copy repo facts into this skill.
2. Do not replace `commander/core/主文档.md`, task cards, timelines, or topical docs.
3. Do not create a parallel `plans / memory / reports / debt` skeleton in the repo.
4. Do not skip markdown reading and jump straight to writing a skill.
5. Keep any new skill lightweight and repo-referential.

## Validation

1. Re-read changed markdown files with UTF-8 after edits.
2. Run `git diff --check` for repo changes when applicable.
3. Run the skill validator for any new or changed local skill.
4. Confirm no protected repo files were unintentionally modified.

## Fallback

If the repo markdown truth sources are missing or the task is actually a normal one-off implementation task, say so briefly and fall back to standard repo reasoning instead of forcing a skill-upgrade workflow.
