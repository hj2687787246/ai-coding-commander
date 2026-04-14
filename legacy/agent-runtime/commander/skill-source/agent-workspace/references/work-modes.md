# Work Modes

Use this reference before choosing how to execute a task.

## Feature Mode

Use Feature mode when the user asks for new behavior or a visible capability.

Default shape:

1. Clarify only if acceptance, scope, or risk is ambiguous.
2. Write or identify the spec when the change is more than trivial.
3. Prefer TDD when behavior can be tested cleanly: red, green, refactor.
4. Keep the refactor step explicit; do not stop at the first green test if the design is now worse.
5. Close with user-visible acceptance evidence.

## Refactor Mode

Use Refactor mode when the goal is behavior-preserving restructuring, cleanup, extraction, or reuse.

Default shape:

1. State the behavior-preservation contract before editing.
2. Characterize existing behavior with tests, snapshots, or narrow runtime checks.
3. Inventory call sites and hidden coupling before moving code.
4. Make small structure-first changes and keep public contracts stable unless the spec explicitly changes them.
5. Do not force red-first TDD if it would prevent the agent from seeing and improving the design. Use characterization tests and post-change equivalence checks instead.
6. Report any intentional behavior change as a spec change, not as a refactor.

## Debug Mode

Use Debug mode when there is a failing test, runtime error, or unexplained behavior.

Default shape:

1. Reproduce or identify the failure signal.
2. Localize before editing.
3. Fix the smallest proven cause.
4. Re-run the failing check, then a narrow regression check.

## Review Mode

Use Review mode when asked to review changes.

Default shape:

1. Inspect the diff against the requested base.
2. Report only discrete, actionable issues the author would likely fix.
3. Keep findings prioritized and line-specific.
4. Do not rewrite the patch unless the user asks for fixes.

## Documentation Mode

Use Documentation mode when the result is stable knowledge, onboarding, handoff, or policy.

Default shape:

1. Choose the narrowest durable target: `AGENTS.md`, project skill `references/`, `commander/state/`, `commander/outer/`, or schema/spec artifact.
2. Avoid copying chat transcripts.
3. Write dated snapshots when a statement can expire.
4. Keep startup files short and move detail behind references.
