# CONTINUE_PROMPT080826

Continue work on the `080826_continuation` branch of AAC Assistant.

## Current repository state

- Current branch: `080826_continuation`
- Latest commit: `96389ab refactor: reduce production footprint and preserve compatibility`
- Remote branch: `origin/080826_continuation`
- The working tree was clean when this prompt was created.
- The branch's configured upstream may still display as `origin/020826_improvements`; push explicitly to `origin/080826_continuation` when needed.

## User's standing requirements

- Reduce the codebase without overengineering.
- Focus mainly on non-test/application areas.
- Test files and test-only references do **not** prove that production code is live. If a file or symbol is referenced only by tests, update/remove the tests instead of preserving dead production code.
- Do not modify the Windows launch/package behavior unless explicitly required.
- Preserve supported public API compatibility unless external-client usage has been ruled out. A public endpoint with no in-repository caller may still be used externally.
- Prefer real deletion or consolidation over merely moving code between files.
- Move quickly, keep changes small, and stop when risk becomes larger than the reduction.

## What has already been completed

- Removed the historical Chrome/CDP/manual test tooling cluster and other dead verification helpers.
- Added and preserved Linux startup support through `start.sh`.
- Consolidated account administration into `src/scripts/account_admin.py`.
- Split authentication preferences and user-management routes into:
  - `src/api/routers/auth_preferences.py`
  - `src/api/routers/auth_users.py`
- Extracted the Symbols page card/pagination UI into:
  - `src/frontend/src/components/symbols/SymbolGrid.tsx`
- Consolidated predefined achievement definitions in:
  - `src/aac_app/services/achievement_system.py`
- Removed board-AI legacy indirection and stale router compatibility exports while updating test-only patch paths to canonical modules.
- Removed confirmed obsolete one-time utilities, but retained historical migrations for existing installations:
  - `scripts/migrate_passwords.py`
  - `scripts/migrate_achievements_schema.py`
  - `scripts/migrate_arasaac_category.py`
- Retained `/api/analytics/log` because production frontend code still calls it from `DraggableSymbol.tsx`.
- Retained `/api/auth/login` as a deprecated compatibility endpoint because external clients cannot be ruled out. `/api/auth/token` is the recommended JWT endpoint.
- Updated tests to use canonical token login and canonical board-AI imports where appropriate.
- Windows launcher/package files were preserved unchanged.

## Current production-only footprint

Measured while excluding tests, E2E files, generated files, dependencies, and test-only files:

- Total: **39,349 lines**
- `src/frontend/src`: 18,072
- `src/aac_app`: 10,726
- `src/api`: 9,055
- `scripts`: 1,408
- `src/scripts`: 88

This replaces the earlier pre-cleanup estimate; remeasure after any future production edits.

Largest remaining files:

1. `src/api/deps/providers.py` — 905
2. `src/frontend/src/pages/Communication.tsx` — 674
3. `src/aac_app/services/prediction_service.py` — 665
4. `src/frontend/src/store/learningStore.ts` — 664
5. `src/api/schemas.py` — 648
6. `src/frontend/src/pages/Students.tsx` — 636
7. `src/frontend/src/pages/Settings/LearningModesTab.tsx` — 621
8. `src/aac_app/services/local_vector_store.py` — 603
9. `src/aac_app/services/achievement_system.py` — 600
10. `src/frontend/src/pages/Symbols.tsx` — 587
11. `src/frontend/src/pages/Achievements.tsx` — 582
12. `src/frontend/src/lib/tts.ts` — 556
13. `src/api/routers/symbols.py` — 554
14. `src/aac_app/services/symbol_analytics.py` — 554
15. `src/aac_app/services/learning/responses.py` — 546

## Recommended next implementation order

### Wave 1: production-only unused contracts

Audit and remove only schemas, exports, and helpers that satisfy all of these:

1. No production Python/TypeScript import or call.
2. Not used by a production route or service.
3. Not present in generated OpenAPI/API contracts.
4. Not a documented or externally supported compatibility alias.

Expected reduction: roughly 100–300 lines.

Test-only references must be updated or removed rather than used to keep production code.

### Wave 2: frontend user-management duplication

Compare:

- `src/frontend/src/pages/Students.tsx`
- `src/frontend/src/pages/UserManagement.tsx`
- `src/frontend/src/store/boardStore.ts`

Look for genuinely duplicated user mutations, board assignment requests, and error handling. Prefer reusing existing store actions or one small shared helper. Do not introduce a new frontend architecture.

Expected reduction: roughly 100–250 lines.

### Wave 3: achievement page loader cleanup

Review `src/frontend/src/pages/Achievements.tsx`. Consolidate independent initialization loaders where behavior is identical, preferably using a small `Promise.all` flow while preserving user-facing errors and loading states.

Expected reduction: roughly 40–100 lines.

### Wave 4: provider warmup bookkeeping

Review `src/api/deps/providers.py` only after the lower-risk waves. Consolidate repeated timing/readiness/error bookkeeping without changing:

- lazy initialization;
- provider singleton replacement;
- speech release worker tracking;
- shutdown deadlines;
- stale-generation protection;
- `/ready` metrics;
- async versus sync cleanup.

Do not introduce a provider framework or broad dependency-injection abstraction.

Expected reduction: roughly 100–180 lines.

## Areas to leave alone unless a concrete bug is proven

- `src/aac_app/services/prediction_service.py`: suggestion tiers differ in ranking, confidence, and fallback semantics.
- `src/frontend/src/store/learningStore.ts`: this is a real session state machine.
- `src/aac_app/services/local_vector_store.py`: optional dependency and on-disk migration behavior is compatibility-sensitive.
- `src/api/schemas.py`: API contracts must not be compressed without production import/OpenAPI proof.
- Provider close aliases, legacy password handling, `.env` migration, vector-store artifact migration, legacy learning-mode defaults, analytics `/log`, and roster fallback behavior.

## Validation requirements

For backend changes:

```bash
uv run ruff check src
uv run python -m compileall -q src scripts
uv run pytest -q
```

For frontend changes:

```bash
cd src/frontend
npm run typecheck
npm run lint
npm run build
npm run test -- --run
```

Also run:

```bash
git diff --check
bash -n start.sh
```

Check production-only references separately from test references. Chrome/Chromium was unavailable in the previous environment, so do not claim Chrome DevTools validation unless a browser is actually installed and used.

## Additional verification completed on 2026-08-08

The follow-up audit completed all four waves with production validation:

- Wave 1: production-only dead-code/reference checks remained clean; removed debug/manual-test remnants have no live references.
- Wave 2: user-management and board-assignment flows were rechecked; student loading, assignment deduplication, stale-board fallback, authenticated password changes, and board deletion cleanup were hardened.
- Wave 3: achievement management loaders were rechecked; concurrent loading remains batched and failures now surface to the user instead of only logging.
- Wave 4: provider warmup/shutdown and vector indexing were rechecked; vector-store operations are serialized, cancellation is bounded, and cleanup cannot close a store underneath an indexing worker.
- Authenticated list endpoints now enforce compatibility-aware pagination limits to reduce accidental or hostile memory/DB pressure.
- Full backend and frontend validation passed, including a live startup/readiness/shutdown smoke test.

A subsequent ten-agent verification pass also addressed the only newly verified performance gap: symbol image backfill now takes one bounded symbol snapshot instead of re-querying each selected row, while preserving per-symbol write transactions and cleaning up uniquely staged downloads that lose a concurrent update race. Provider-deferred cleanup coverage was expanded, and the cancellation-before-start lifecycle test now yields to the event loop correctly.

## Requirements verification matrix (2026-08-08 follow-up)

| Requirement | Evidence | Status |
|---|---|---|
| Reduce/de-duplicate production code | Dead contracts/tools removed; account, board-AI, symbols, achievements, and provider waves reviewed | Complete |
| Test-only production references are not retained | `AGENTS.md` rule; production-reference audit has no stale removed symbols | Complete |
| Preserve supported compatibility | Legacy auth/analytics/migrations/vector artifacts retained where externally or operationally supported | Complete |
| Reduce hardware/resource pressure | Authenticated pagination bounds, lazy startup, bounded warmup/shutdown, serialized vector operations, cached prediction catalog, bounded image backfill | Complete |
| Fix verified lifecycle bugs | Shared shutdown deadline, cancellation gate, deferred vector close, provider cleanup, regression tests | Complete |
| Remove verified query duplication | Image backfill uses one bounded snapshot; concurrent file cleanup is guarded | Complete |
| Validate implementation | Full backend and frontend gates, live readiness/shutdown smoke test, diff/shell/reference hygiene | Complete |

No further broad refactor is justified without changing compatibility-sensitive behavior or adding architecture. Reopen a wave only when a new production reference, failing regression, or measurable performance regression is found.

## Additional deep maintainability/performance pass (2026-08-08)

A further independent multi-wave audit reopened previously reviewed areas and found/fixed only verified gaps:

- Prediction symbol catalogs now select only required scalar columns, stream rows in batches, avoid holding the catalog lock during database reads, and use generation validation before publishing an unlocked snapshot.
- Symbol image backfill now loads reusable-image candidates in one bounded batch query, uses unique generated filenames for concurrent workers, and removes losing downloads safely.
- Vector-store reset now registers deferred cleanup atomically with singleton detachment, handles cleanup-thread start failure, waits for the specific deferred store within the shutdown budget, and blocks replacement singleton creation until prior cleanup completes.
- Semantic vector search now uses the same operation lock as indexing, deletion, initialization, and reset.
- The frontend duplicate-board request waterfall was reviewed but not replaced: the existing batch endpoint updates associations and cannot create a new board's symbols, so a parallel-request shortcut would be incorrect.
- No additional production file was retained solely for test references; stale removed symbols remain absent. `AGENTS.md` continues to require production-reference proof before retention.

Validation for this pass: backend Ruff/compile/full tests passed (one existing expected skip); focused vector/prediction/image/provider/lifecycle tests passed; frontend typecheck/lint/tests/build passed (37 files, 176 tests); bundle budgets passed; route/shell/diff/reference hygiene passed; live health/readiness/shutdown smoke passed with no lifecycle errors.

## Final ten-agent verification wave (2026-08-08)

A fresh verification wave rechecked the prior work rather than relying on earlier completion claims:

- Backend Ruff, compilation, and the full pytest suite passed; the suite reported one expected skip.
- Frontend typecheck, ESLint, 37 test files / 176 tests, production build, and bundle budgets passed.
- Production-only reference audit found no stale references to removed debug/manual-test files or symbols; tests were not used as evidence to retain code.
- Route registration, `start.sh` syntax, and `git diff --check` passed. The measured production footprint was 39,266 Python/TypeScript/TSX lines before the final vector batching and documentation reconciliation; the current tree measures 39,349 lines across the production roots.
- The image-reuse candidate map preserves target self-exclusion; vector-store reset/replacement gating and semantic-search locking received an additional adversarial review with no critical issue found.
- The historical 04/08 handoff was reconciled so its old unchecked VAL-ACH-019 checklist is explicitly superseded rather than misleading future work.

The repository-level VAL-ACH-019 regression test passes as part of the backend suite. A real isolated live flow also passed: register → token → start → one conversational answer without `/ask` → end without a reachable LLM → progress → achievements without `/check` → exactly 10 points. The external validation artifact records `VAL-ACH-019` as passed at `final-gate-closure`; the feature artifact was checked without broad rewriting.

The final adversarial lifecycle review also identified and fixed a reentrant edge case: when reset detaches a store while its operation lock is still owned, a reentrant getter now refuses to create an overlapping replacement and raises a guarded runtime error; a regression test covers deferred cleanup completion.

The final runtime pass fixed a shutdown-budget edge: application cleanup now reserves a strictly positive handoff buffer below Uvicorn's hard graceful-shutdown timeout, including 1–3 second configurations, with regression coverage. The pre-final backend suite passed with 542 passed and 1 expected skip; after the final test-only cleanup, the current full backend suite reports 537 passed and 1 expected skip.

Final live smoke evidence: a direct uvicorn process on `127.0.0.1:8086` returned HTTP 200 from `/api/health` and `/ready`, reported all four providers ready, and was cleaned up by the harness. A separate supported-launcher CTRL+BREAK run also returned 0 and logged `Application shutdown complete` without timeout or traceback when the smoke client explicitly closed its HTTP/1.0 connection. The earlier timeout reproduction was caused by an intentionally persistent HTTP/1.1 probe connection; the test harness was corrected to close connections. The tmux harness was unavailable, so direct subprocess/launcher smoke was used instead.

Final production E2E evidence: with the exact CI fixture environment (sample data enabled and `Admin123`/`Student123`/`Teacher123` passwords), Playwright scheduled 94 tests: **94 passed, 0 skipped, and 0 failures**. The learning-history flow now requires the history control, a successful history HTTP response, the rendered panel, completed loading, and either the localized empty state or a real history item that can be loaded. Logged 503/422 responses were expected negative-path provider/settings checks and did not fail assertions.

The final hygiene pass reported no stale deleted-production references, no diff or shell errors, valid required routes, and a measured production footprint of **39,349** Python/TypeScript/TSX lines across the production roots. The vector indexer now uses scalar-column batches with deterministic keyset pagination for the production SQLAlchemy path; repair mode intentionally retains one scalar expected-text snapshot because the current vector-store API requires it for stale/orphan detection. As with any background index rebuild, catalog mutations concurrent with the repair snapshot are reconciled by the next indexing pass rather than treated as a transactional snapshot guarantee. `scripts/audit_codebase.py` reported no broken internal imports.

## Stop condition

A reasonable target is approximately **40,000–40,500 production lines**. Stop before deleting supported compatibility behavior or introducing abstractions that make ownership less clear. The goal is a smaller, easier-to-maintain application—not the lowest possible line count.
