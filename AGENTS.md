# Repository agent guidance

## Production-only code rule

Treat application code referenced only by tests, fixtures, E2E files, or test mocks as dead. Remove the production file/symbol and update or delete the tests instead of preserving production code for test convenience.

When auditing references, exclude ignored/generated trees such as `.venv/`, `node_modules/`, `dist/`, `build/`, `tmp/`, caches, and test artifacts. They are not production references and must not be used to justify retaining dead code.

If a production file or symbol has no runtime import/call, route registration, dynamic import, operator-script use, migration use, generated API contract, or documented external compatibility obligation, delete it and update/remove tests that referenced it. Tests alone are never evidence that production code is live. Test isolation, cache reset, fixture teardown, and assertion helpers belong in tests; do not retain application-only hooks solely to make tests reset process-wide state.

Before deleting a symbol, check all production imports/calls, registered routes, dynamic imports, generated OpenAPI contracts, documented compatibility endpoints, scripts used by operators, and persisted-data migrations. Test-only references are never evidence that production code is live. For each candidate, record the production-only search scope and result; do not use tests, fixtures, E2E files, mocks, caches, or generated artifacts as evidence that it is live. After deletion, search again and update/remove test-only references rather than adding compatibility shims.

## Maintainability and performance

For audit work, inspect every production root at least once, then repeat the scan after each change. Revisit previously reviewed hotspots instead of assuming earlier audit notes are current. Only make a change when it removes verified dead code, duplicate work, unnecessary allocation/concurrency, or a measurable lifecycle/resource risk; prefer a local consolidation or deletion over a new abstraction.

- Prefer deletion or a small local consolidation over new abstractions.
- Do not move code merely to reduce a line count.
- Preserve external API compatibility unless external usage has been ruled out.
- Keep optional ML/voice/vector dependencies lazy and out of the startup critical path.
- Avoid broad provider frameworks, state-management rewrites, and changes to compatibility-sensitive migrations without concrete evidence.
- Reduce duplicate database/API work, unnecessary allocations, and unbounded concurrency where behavior remains clear.
- Do not modify Windows launch or packaging behavior unless the task specifically requires it.

## Validation

Backend changes: `uv run ruff check src tests scripts`, `uv run python -m compileall -q src scripts`, and relevant pytest tests (full `uv run pytest -q` for broad changes).

Frontend changes: from `src/frontend`, run `npm run typecheck`, `npm run lint`, `npm test -- --run`, and `npm run build` as appropriate.

Always run `git diff --check` and inspect production references separately from tests. Never claim browser or live-server validation unless it was actually run.
