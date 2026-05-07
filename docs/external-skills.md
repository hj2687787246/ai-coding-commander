# External Skills Inventory

更新时间：2026-05-07

This document tracks optional third-party skills installed for local Codex use. It is an inventory and routing note, not a mandatory startup rule.

## Source

- Repository: `https://github.com/Arcadi4/skills`
- Installed location: `$CODEX_HOME\skills\*` or the default user Codex skills directory.
- Installed standard skills: 11
- Not installed as a skill: `commands`, because it has no `SKILL.md`.

## Operating Policy

These skills are available as an optional toolbox. Do not treat the full repository as part of the default commander workflow.

Use a skill only when its trigger matches the current task. Do not add every external skill to `commander-mode` routing by default. If a skill proves repeatedly useful in real work, consider adding a narrow route later.

Do not copy large sections from these skills into project rules. Prefer referencing the installed skill by name.

## Default Recommended Toolbox

These skills are broadly useful for maintaining the commander skill system and reducing recurring agent failures.

| Skill | Use when | Commander relationship |
| --- | --- | --- |
| `identify-skill-failure` | A loaded skill did not change agent behavior, or a rule was violated despite being present. | Useful for post-mortems before editing `commander-mode` or project rules. |
| `compress-skill` | A `SKILL.md` is bloated, repetitive, or too long for frequent loading. | Useful after a skill starts behaving like a handbook. |
| `modulize-skill` | A `SKILL.md` has appendix-like details that should move to references. | Useful when keeping `commander-mode` as a router instead of a manual. |
| `generalize` | The user gives examples with "for example", "such as", "etc.", or similar wording. | Useful for avoiding literal-only interpretation of examples. |
| `atomic-git-commits` | Preparing commits or reviewing a branch where unrelated changes may be bundled. | Useful for preserving clean history around skill and governance changes. |

Recommended minimal installation:

```powershell
python "$CODEX_HOME\skills\.system\skill-installer\scripts\install-skill-from-github.py" --repo Arcadi4/skills --path identify-skill-failure compress-skill modulize-skill generalize atomic-git-commits
```

If `python` is not on PATH, run the same command with the Python executable bundled with Codex or another known working Python.

## Scenario-Triggered Toolbox

These skills are useful, but should not become default commander behavior.

| Skill | Use when | Notes |
| --- | --- | --- |
| `writing-adrs` | A real architecture decision needs a durable record of context, options, decision, and consequences. | Use for settled decisions, not brainstorming dumps. |
| `developing-agents` | Implementing or debugging agent runtimes, tool-calling loops, message conversion, provider compatibility, or replay behavior. | Relevant to Agent/RAG/MCP/runtime work. |
| `frontend-debugging` | Debugging CSS layout, DOM structure, or box-model problems that survive normal tweaks. | Use with local frontend evidence. |
| `manual-frontend-qa` | The user asks for manual UI verification or automated browser testing is not worth setting up. | Requires direct user-facing QA communication. |
| `ui-style-consistency` | Auditing duplicated UI primitives, design-system drift, or hand-rolled component variants. | Use for design-system reviews, not every frontend edit. |
| `opencode-cli-debugging` | Debugging OpenCode CLI integrations, plugins, provider wiring, or session-level behavior. | OpenCode-specific; do not route from general Codex tasks. |

Install all standard Arcadi4 skills only when you want the whole optional toolbox available locally:

```powershell
python "$CODEX_HOME\skills\.system\skill-installer\scripts\install-skill-from-github.py" --repo Arcadi4/skills --path atomic-git-commits compress-skill developing-agents frontend-debugging generalize identify-skill-failure manual-frontend-qa modulize-skill opencode-cli-debugging ui-style-consistency writing-adrs
```

## Not Installed

| Directory | Reason |
| --- | --- |
| `commands` | No `SKILL.md`; not a standard Codex skill. |

## License Notes

Several installed skills declare `CC-BY-SA-4.0` or `CC-BY-NC-4.0`. Installed local use is fine for reference, but do not copy substantial content into public project files without checking the license and attribution requirements.

## Review Rule

If an external skill is frequently used for the same commander task, review whether to:

1. Keep it as an optional installed skill.
2. Add a narrow route in `commander-mode`.
3. Extract only a small local rule if the behavior is stable and license-compatible.

Prefer the smallest option that prevents the observed failure.
