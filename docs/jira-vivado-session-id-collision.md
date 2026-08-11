# Session ID collision across parallel MCP server processes due to second-resolution timestamp generation

| Field | Value |
|---|---|
| **Project** | _(fill in — e.g. VIVMCP / INFRA)_ |
| **Type** | Bug |
| **Priority** | High |
| **Component** | vivado-mcp-server / session management |
| **Affects Version** | v0.6.9 (`AMD-aecg-cue-ai/vivado-ai-extensions`) |

## Description

`SessionManager.GenerateSessionID()` in `vivado-mcp-server/session_manager.go:60-63` generates session IDs as:

```go
timestamp := time.Now().Format("20060102-150405")
return fmt.Sprintf("vivado-%s", timestamp)
```

This has only 1-second resolution and no per-process entropy (no PID, no random suffix). Uniqueness is enforced in `CreateSession()` (`session_manager.go:79-92`) by checking the ID against `sm.sessions`, an **in-memory map scoped to a single MCP server process**. There is no cross-process lock or coordination (e.g. via the on-disk session store).

## Impact

In our CI parallel test flow (`ip-configurator`, `--parallel 7`, 3 client/model legs), each leg spawns its own MCP server process. If two leg processes call `vivado_start` within the same wall-clock second, they independently generate the identical `vivado-<timestamp>` ID — each process's uniqueness check passes because neither can see the other's session map. This produces duplicate session IDs across concurrent Vivado instances, which then collide downstream anywhere session ID is used as a key/filename, e.g.:

- `command_store.go:1113` — `fmt.Sprintf("%s_%s.json.gz", sessionID, ...)` (history file path)
- task manager / webserver URL lookups keyed by session ID

Observed in CI logs as repeated identical `vivado-YYYYMMDD-HHMMSS` session IDs across different legs, correlated with cross-talk/flakiness under parallel execution.

## Steps to Reproduce

1. Launch 2+ separate `vivado-mcp-server` processes.
2. Call `vivado_start` on each within the same second.
3. Observe both processes generate the same `vivado-<timestamp>` session ID.

## Suggested Fix

Add per-process/random entropy to the generated ID, e.g.:

```go
fmt.Sprintf("vivado-%s-%d-%s", timestamp, os.Getpid(), randHex(4))
```

or use `time.Now().UnixMilli()` / a UUID instead of second-resolution formatting, so uniqueness doesn't depend on wall-clock second granularity or in-process-only state.

## Workaround (in place on our side)

Reducing test parallelism / staggering `vivado_start` calls to avoid same-second collisions.

## References

- Source: `AMD-aecg-cue-ai/vivado-ai-extensions` @ tag `v0.6.9`
- `vivado-mcp-server/session_manager.go:60-91`
- `vivado-mcp-server/command_store.go:1113`
