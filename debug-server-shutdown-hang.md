# Debug Session: server-shutdown-hang
- **Status**: [OPEN]
- **Issue**: Pressing Ctrl+C leaves the AAC Assistant server stuck waiting for connections to close instead of exiting promptly.
- **Debug Server**: http://127.0.0.1:7777/event
- **Log File**: .dbg/trae-debug-log-server-shutdown-hang.ndjson

## Reproduction Steps
1. Start the AAC Assistant backend locally.
2. Open the app so the server has at least one active client connection.
3. Press Ctrl+C in the server terminal.
4. Observe that the process stays in the graceful shutdown phase waiting for connections to close.

## Hypotheses & Verification
| ID | Hypothesis | Likelihood | Effort | Evidence |
|----|------------|------------|--------|----------|
| A | A background lifespan task does not handle cancellation and blocks shutdown. | High | Low | Rejected |
| B | A long-lived HTTP/SSE connection stays registered and uvicorn keeps waiting forever. | High | Medium | Rejected |
| C | Provider clients or warmup work keep the event loop alive after shutdown starts. | Medium | Medium | Rejected |
| D | Database/session cleanup blocks while waiting on resources during lifespan teardown. | Medium | Medium | Inconclusive |
| E | Shutdown handling lacks a timeout/cancellation boundary for active connections. | Medium | Medium | Partial |
| F | `start.bat`/`cmd.exe` intercepts real Ctrl+C and keeps the wrapper console alive after the backend has already shut down. | High | Medium | Confirmed |

## Log Evidence
- Reproduction 1 with a live SSE stream still shut down cleanly; debug log showed the subscriber connected and cleaned up before lifespan shutdown (`.dbg/trae-debug-log-server-shutdown-hang.ndjson` lines 7-9 in the first run).
- Reproduction 2 with a browser-like reconnecting SSE client also shut down cleanly; debug log again showed subscriber cleanup followed by lifespan shutdown.
- `uvicorn.config.Config.__init__` in the shipped version (`0.52.1`) defaults `timeout_graceful_shutdown` to `None`, which allows an indefinite graceful-shutdown wait if a connection or task does not finish.
- The launcher previously passed no explicit graceful shutdown timeout.
- Fix applied: launcher and direct `uvicorn.run(...)` now set `BACKEND_GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS=10`.
- Real console Ctrl+C attached to a separate console confirms the direct Python launchers exit normally:
  - `.venv\\Scripts\\python.exe -m scripts.start_server` -> exited `0`
  - `python -m scripts.start_server` -> exited `0`
- The same real console Ctrl+C attached to `start.bat` leaves the batch process alive:
  - `start.bat` result: `{\"pid\": 20584, \"exited\": false, \"returncode\": null}`
  - Server log for the same run still shows `src.api.main:lifespan:191 | Shutting down AAC Assistant API...`
  - Post-interrupt process inspection shows the surviving wrapper is `cmd.exe /c d:\\GitHub\\AAC_ASSISTANT\\start.bat`, not uvicorn.

## Verification Conclusion
- The server shutdown timeout was worth fixing, but it was not the root cause of the user's current Ctrl+C symptom.
- Root cause identified: `start.bat` runs under `cmd.exe`, and real Ctrl+C leaves the batch wrapper alive even after the backend has already handled shutdown.
