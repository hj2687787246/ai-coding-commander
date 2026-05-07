---
name: execution-failure-guard
description: Use when a command, tool call, install, test, build, git operation, script, shell command, CLI, environment lookup, or automation failed once and a working replacement was found, so future similar attempts should reuse the learned working method instead of repeating trial-and-error.
---

# Execution Failure Guard

## Core Purpose

Turn a solved execution failure into the next attempt's default path. The goal is not to recover once; it is to stop re-learning the same fix.

This skill does not decide the final durable layer. Use `commander-reuse-upgrader` for that decision. This skill owns immediate reuse of the learned working method; `commander-reuse-upgrader` owns whether the method becomes project markdown, a script/checker, a trigger-matrix row, or a skill edit.

## Preflight Check

Before running a command that resembles a previous failure, check the registry when it exists:

```powershell
python <execution-failure-guard-skill-dir>\scripts\known_failures.py --repo . check --command "<planned command>"
```

If the check returns `matched: true`, do not run the known-bad command. Use the returned `use_instead` unless the record is out of scope or you are intentionally validating that the failure is gone.

The check command exits `0` for both match and no-match. Read the JSON `matched` field; do not infer match status from the exit code.

The registry lives at `.codex/known-failures.json`. If it does not exist, continue normally; after a reusable failure is solved, create or update it with the same script.

## Learned Fix Gate

After any command/tool execution fails and a working replacement is found:

1. Name the failure pattern: shell syntax, PATH lookup, dependency invocation, auth helper, test command, build command, service startup, file encoding, tool schema, or another concrete category.
2. Capture the known-bad method when it is likely to be retried: the rejected command shape, why it failed, and the boundary where it is invalid.
3. Capture the working method as a reusable command shape, not as a chat anecdote.
4. Use the working method for the rest of the session before trying variants.
5. If the pattern can recur in another window, invoke `commander-reuse-upgrader` or its decision rules to choose the narrowest durable surface.
6. If the same pattern has recurred before, upgrade the durable surface instead of adding another note.

## Known-Bad Method Gate

Do not persist every typo or transient outage. Persist a known-bad method when a reasonable future agent might choose it again.

Record it in this shape:

```json
{
  "known_bad": "<command/tool shape that failed>",
  "fails_because": "<portable reason, not just this run's output>",
  "use_instead": "<verified working method>",
  "scope": "<repo/session/platform/tool boundary where this applies>"
}
```

If the known-bad method is dangerous, destructive, or repeatedly tempting, prefer an automated guard such as a script, test, checker, or setup command through `commander-reuse-upgrader`.

## Before Repeating A Similar Operation

Check whether the current task, repo docs, tests, or active skills already contain a learned method for this operation. If yes, start from that method.

Do not repeat the original failing command just to rediscover the same fix unless you are intentionally validating that the failure has disappeared.

## Durable Surface

| Pattern | Prefer |
| --- | --- |
| Project-specific command or path | Current task or project docs. |
| Deterministic check or setup step | Script, test, checker, or setup command. |
| Cross-project judgment pattern | Skill or skill edit. |
| Skill discovery wording failed | Trigger matrix or skill description. |
| Temporary one-off environment state | Current task only, with expiration context. |

## Common Learned Fixes

| Failure | Learned method to reuse |
| --- | --- |
| `pwsh` not found in the current tool process | Refresh Machine/User PATH in that command before resolving `pwsh`, or use the current PowerShell with explicit flags. |
| Regex/pipeline characters break in PowerShell | Quote the pattern or use `Select-String -Pattern 'a|b'`. |
| Python points to WindowsApps shim | Use the repo `.venv` executable or the resolved intended Python path. |
| Git auth helper points to a stale executable | Override the helper for that command or fix the configured helper before pushing. |
| Test command needs repo-local environment | Reuse the repo's known executable path and environment setup instead of global commands. |
| Tool schema rejects a parameter | Reuse the accepted schema shape; do not retry the rejected shape. |

## Red Flags

- "It failed, but I know the right command now" without saving or reusing it.
- Running the same failing command again after a working replacement was found.
- Saving only the working method when the failed method is likely to be tried again.
- Treating a recurring execution failure as isolated because the immediate retry succeeded.
- Writing a broad preference when a script/checker would enforce the fix better.
- Capturing the fix only in chat, where the next agent will not reliably see it.
