# Commander Objective Templates

This directory stores repo-native templates for long-running commander objectives.
They are not runtime state. Runtime copies live under `.runtime/commander/objectives/`.

## Current LangGraph Runtime Objective

Bootstrap the current `5.6 LangGraph Commander Runtime Projectization` objective:

```powershell
.\.venv\Scripts\python.exe -m commander.transport.scripts.commander_bootstrap_current_objective
```

Default template:

```text
commander/transport/objective_templates/langgraph_runtime_5_6.json
```

The template contains a full objective backlog, not a single task:

- `phase-5-6-host-runtime-integration`
- `phase-5-7-spec-kit-sdd`
- `phase-5-8-hermes-memory-feedback`
- `phase-5-9-provider-tool-governance`

After bootstrap, run one visible host cycle:

```powershell
.\.venv\Scripts\python.exe -m commander.transport.scripts.commander_host_daemon run-loop --max-cycles 1
.\.venv\Scripts\python.exe -m commander.transport.scripts.commander_host_control daemon-status --log-limit 8
```

Expected behavior:

- The first goal runs through `local-script` and completes inline.
- The next goal dispatches to the external `codex` provider.
- The daemon status should become `waiting_external_result` while it waits for the external worker report.
