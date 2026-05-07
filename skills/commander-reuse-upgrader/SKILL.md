---
name: commander-reuse-upgrader
description: Use when a repeated question, workflow, correction, or agent failure may need to be preserved as project markdown, an executable script/checker, or a lightweight skill, especially before adding new rules or creating skills from recurring AI coding problems.
---

# Commander Reuse Upgrader

## Core Purpose

Route recurring problems into the lightest reusable layer that will prevent the next failure. Do not jump straight to a skill because the rule feels important.

## Entry Contract

Before choosing a destination:

1. Rebuild the current facts from the active workspace truth sources.
2. Identify the repeated problem or correction.
3. Check whether an existing rule, script, test, or skill already covers it.
4. Choose markdown, automation, or skill based on the decision rules below.

Do not rely on chat memory as the final truth source.

## Destination Rules

Use project markdown when the reusable value is a project fact, boundary, convention, handoff note, acceptance rule, or changing status.

Use a script, test, checker, or command when the reusable value is deterministic, repeated, command-like, or better enforced by automation than prose.

Use a skill only when all of these are true:

- The problem or correction has repeated, or the failure is severe enough to justify reuse now.
- The trigger is stable and recognizable from future user wording or task context.
- The reusable part is a workflow, judgment pattern, or technique, not project facts.
- Existing skills and project rules do not already cover the behavior.
- The skill can stay lightweight and avoid becoming a second project memory layer.
- Validation evidence or a pressure scenario exists to prove the skill changes behavior.

## Skill Upgrade Gate

If skill is the right destination, route to `superpowers:writing-skills` when available.

Use skill-document TDD:

1. Capture the failing behavior or natural rationalization first.
2. Write the smallest skill or skill edit that prevents that failure.
3. Add red flags, anti-patterns, or gates for the observed loophole.
4. Validate with a pressure scenario before claiming the skill works.

If `superpowers:writing-skills` is unavailable, follow the same compact gate and say the specialized skill is unavailable.

## Discovery Failure Gate

If a skill should have handled the problem but did not trigger, treat it as a discovery failure:

- Check whether the skill is installed and active in the current session.
- Check whether its description matches the user's wording, including Chinese synonyms.
- Check whether a broader skill is shadowing it.
- Decide whether to improve the skill description, add a commander route, or leave it as an acceptable miss.

## Constraints

- Do not copy project facts into a reusable skill.
- Do not create a parallel memory system beside repo docs, task cards, timelines, or issue trackers.
- Do not write a skill for a one-off preference, temporary task choice, or unstable guess.
- Do not duplicate an existing skill; enhance or route to it instead.
- Keep new skills small enough to be loaded for their trigger without carrying unrelated history.

## Validation

Before reporting completion:

- State which destination was chosen and why lighter/heavier layers were rejected.
- For markdown, re-read changed files with UTF-8 and check for duplicate rules.
- For scripts/checkers, run the narrow command or test that proves the automation works.
- For skills, verify frontmatter, trigger description, no private paths, and at least one pressure scenario or documented failing behavior.
- Run `git diff --check` when repository files changed.
