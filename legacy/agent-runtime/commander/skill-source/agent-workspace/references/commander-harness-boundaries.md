# Commander Harness Boundaries

Use this reference when changing or evaluating the commander harness itself.

## Core Direction

The useful product is an AI coding cockpit: restore state, clarify goals, split work, control write boundaries, verify results, and preserve durable evidence. It is not a universal multi-agent runtime.

## Keep

Keep the parts that directly support visible AI coding work:

- Generic `commander-mode` skill source.
- Project adapter skill and references.
- Task card, timeline, issue/problem index, and `outer` status index.
- Minimal packet/report/status/resume/catalog transport.
- Stop gate, audit, role guard, lane contract, tool/path governance, and provider preflight.
- Schema-backed spec refs where they make dispatch and review clearer.

## Freeze Or Treat As Adapter

Freeze or treat these as Agent-repo experiments unless a new task explicitly revives them:

- LangGraph runtime.
- Host runtime and host daemon.
- Warm worker pool and reusable session experiments.
- Objective/phase backlog automation.
- External window auto-launch beyond the existing provider adapter.

## External Harnesses

Prefer adapting mature external workflows such as superpowers for brainstorming, planning, TDD, review, and branch finishing. Do not rewrite those workflows into this repo or vendor their skeletons into `commander/`.

## Memory Placement

- `AGENTS.md`: startup routing and hard constraints only.
- Project skill `references/`: project workflow, mode selection, spec/plan conventions, harness boundaries.
- `commander/state/`: current task facts, timeline, problems, evidence.
- `commander/outer/`: historical方案, templates, and long-form design records.
- `commander/specs/`: reviewable contracts and schema-valid artifacts.
