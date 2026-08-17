# Repository agent guidance

## Production-only code rule

Treat application code referenced only by tests, fixtures, E2E files, or test mocks as dead. Remove the production file/symbol and update or delete the tests instead of preserving production code for test convenience.

When auditing references, exclude ignored/generated trees such as `.venv/`, `node_modules/`, `dist/`, `build/`, `tmp/`, caches, and test artifacts. They are not production references and must not be used to justify retaining dead code.

If a production file or symbol has no runtime import/call, route registration, dynamic import, operator-script use, migration use, generated API contract, or documented external compatibility obligation, delete it and update/remove tests that referenced it. Tests alone are never evidence that production code is live. Test isolation, cache reset, fixture teardown, and assertion helpers belong in tests; do not retain application-only hooks solely to make tests reset process-wide state.

Before deleting a symbol, check all production imports/calls, registered routes, dynamic imports, generated OpenAPI contracts, documented compatibility endpoints, scripts used by operators, and persisted-data migrations. Test-only references are never evidence that production code is live. For each candidate, record the production-only search scope and result; do not use tests, fixtures, E2E files, mocks, caches, or generated artifacts as evidence that it is live. After deletion, search again and update/remove test-only references rather than adding compatibility shims.

Every maintainability audit must inspect each production root (`src/aac_app`, `src/api`, `src/config.py`, `src/scripts`, launch/packaging files, and `src/frontend/src`) at least once, then repeat the production-only reference and hotspot scan after each cleanup pass. Record the production-only search scope and result for every deletion candidate; test-only references are never evidence of liveness. A symbol used only by tests is dead even when those tests are valuable; remove the production symbol/file and revise or remove the tests rather than adding a compatibility hook. The same applies at file granularity: a production file whose only references come from tests, fixtures, E2E files, or test mocks is dead code. Delete the file (and its imports/exports) and update or delete the tests that referenced it; do not keep the file merely because tests exercise it.

## Maintainability and performance

For audit work, inspect every production root at least once, then repeat the scan after each change. Revisit previously reviewed hotspots instead of assuming earlier audit notes are current. Only make a change when it removes verified dead code, duplicate work, unnecessary allocation/concurrency, or a measurable lifecycle/resource risk; prefer a local consolidation or deletion over a new abstraction.

- Prefer deletion or a small local consolidation over new abstractions.
- Do not move code merely to reduce a line count.
- Preserve external API compatibility unless external usage has been ruled out.
- Keep optional ML/voice/vector dependencies lazy and out of the startup critical path.
- Avoid broad provider frameworks, state-management rewrites, and changes to compatibility-sensitive migrations without concrete evidence.
- Reduce duplicate database/API work, unnecessary allocations, and unbounded concurrency where behavior remains clear.
- Do not modify Windows launch or packaging behavior unless the task specifically requires it. The 2026-08-12 release-safety task explicitly required and validated launcher/installer changes; future work must still keep those changes isolated and tested.

## Validation

**NEVER run full test suites (pytest, vitest, or Playwright E2E) unless the user explicitly asks for a full run.** Full suites are slow and the user does not have unlimited time. Default to running only the specific test files/specs affected by the current change, then the final consolidated gate (`verify_pr.py`) only when the user requests it or a broad change genuinely requires it. This is a permanent rule: do not run `uv run pytest` without paths, `npx playwright test` without a spec filter, or `npm test -- --run` without a file filter unless the user explicitly says to run everything. For GUI verification, prefer targeted API smoke checks (curl) and at most one or two specific Playwright specs over the whole E2E suite.

Backend changes: `uv run ruff check src tests scripts`, `uv run python -m compileall -q src scripts`, and the relevant pytest test files (run with explicit paths; full `uv run pytest -q` only when the user asks). Launcher/packaging changes additionally require `uv run ruff check launcher.pyw`, `uv run python -m compileall -q launcher.pyw`, packaging tests, a rebuilt PyInstaller/Inno artifact, and an isolated smoke with `AAC_ASSISTANT_NO_BROWSER=1`.

Frontend changes: from `src/frontend`, run `npm run typecheck`, `npm run lint`, `npm test -- --run`, and `npm run build` as appropriate.

Full local PR gate: `uv run python scripts/verify_pr.py` executes the consolidated backend, frontend, coverage, and documentation checks. See `docs/MAINTAINER_GUIDE.md` for release runbooks.

Always run `git diff --check` and inspect production references separately from tests. Never claim browser or live-server validation unless it was actually run.

## Task and process lifecycle

Never leave background tasks, orphaned servers, subagents, or dangling test runners running when completing a turn or validation pass. Always audit active tasks (`manage_task` list) and kill unneeded background processes immediately.
