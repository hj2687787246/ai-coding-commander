# Spec And Plan Contract

Use this reference when a task involves spec, plan, SDD, orchestration, subagents, dispatch, packets, or acceptance review.

## Separation

Spec and plan are different artifacts:

- A spec is a reviewable contract. It defines user-visible behavior, requirements, constraints, non-goals, acceptance criteria, truth sources, and invariants.
- A plan is an orchestration artifact. It defines sequencing, lane split, subagent ownership, write sets, validation steps, rollback points, and result intake.

Do not merge them into one prose blob. If a document has both, label the sections explicitly and keep the spec stable while the plan evolves.

## Where To Put Them

- Put machine-readable specs in `commander/specs/<spec_id>.json` when the existing schema is appropriate.
- Put lightweight human specs near the feature or task docs when a JSON artifact is too heavy.
- Put active orchestration into the task packet, phase/objective plan only when the runtime adapter is already in use, or the current task card when no runtime plan is needed.
- Do not create a parallel `plans/`, `memory/`, `reports/`, or `debt` skeleton in this repository.
- Do not put detailed specs or plans into `AGENTS.md`; keep `AGENTS.md` as startup routing and hard constraints.

## Spec Checklist

A useful spec answers:

1. What behavior or contract changes?
2. What is explicitly out of scope?
3. What files, APIs, or workflows are the truth sources?
4. What acceptance checks prove completion?
5. What invariants must remain true after the change?

## Plan Checklist

A useful plan answers:

1. Which mode is active: Feature, Refactor, Debug, Review, or Documentation?
2. Which lane owns each slice: Explorer, Worker, Verifier, or Scribe?
3. Which write sets are owned by which actor?
4. What order avoids double-writing and stale context?
5. What validation closes the loop?

## Subagent Rule

When platform policy allows subagents, plans may assign work to subagents. Each assignment must name ownership, write set, expected output, and validation. In environments where higher-priority tool policy requires explicit user authorization before spawning subagents, obey that platform policy.
