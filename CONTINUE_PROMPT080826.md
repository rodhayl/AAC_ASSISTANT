# CONTINUE_PROMPT080826

Continue work on the `080826_continuation` branch of AAC Assistant.

## Current repository state

- Current branch: `080826_continuation`
- Current release baseline: `b2bd6e4 fix(release): make installer upgrades report and close safely`
- Handoff status last reconciled in: `d7c9b69`/`808432f`/`9469190` (offline model bundling, regression coverage, and documentation reconciliation)
- Remote branch: `origin/080826_continuation`
- HEAD is `9469190` (`docs(release): reflect offline model bundling and current validation state`) and the branch is three commits ahead of `origin/080826_continuation`.
- The working tree is clean and release-ready; the offline bundling and installer update-wizard changes are committed.
- The configured upstream is `origin/080826_continuation`; use that explicit branch when publishing reviewed commits.

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
- Windows launcher/package behavior was changed explicitly in the release-safety follow-up: graceful update signaling, bounded close polling, and the opt-in `AAC_ASSISTANT_NO_BROWSER=1` headless mode are now documented and tested.

## Current production-only footprint

Measured while excluding tests, E2E files, generated files, dependencies, and test-only files:

- Total: **40,937 lines** (current working tree, 2026-08-13)
- `src/frontend/src`: 18,803
- `src/api`: 10,025
- `src/aac_app`: 10,587
- `scripts`: 1,432
- `src/scripts`: 90

This replaces the earlier 40,776-line estimate; remeasure after any future production edits. The count includes the cycle-free frontend auth bridge and the offline model-bundling script (`scripts/bundle_models.py`), and excludes tests, E2E files, generated files, dependencies, and `__pycache__`. Every later section carrying an earlier date is historical evidence from that checkpoint; the current footprint, pending status, and latest validation in this opening section and the dated current-verification section below are authoritative.

Largest remaining files:

1. `src/api/deps/providers.py` — 1052
2. `src/aac_app/services/prediction_service.py` — 695
3. `src/frontend/src/pages/Communication.tsx` — 675
4. `src/frontend/src/store/learningStore.ts` — 663
5. `src/frontend/src/pages/Students.tsx` — 644
6. `src/api/schemas.py` — 643
7. `src/frontend/src/pages/Settings/LearningModesTab.tsx` — 630
8. `src/aac_app/services/local_vector_store.py` — 603
9. `src/frontend/src/pages/Symbols.tsx` — 587
10. `src/api/routers/symbols.py` — 561
11. `src/frontend/src/pages/Achievements.tsx` — 561
12. `src/aac_app/services/symbol_analytics.py` — 557
13. `src/aac_app/services/learning/responses.py` — 546
14. `src/frontend/src/lib/tts.ts` — 545
15. `src/aac_app/services/achievement_system.py` — 535

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

Check production-only references separately from test references. Chrome is installed in the current environment, but the delegated browser agent was rate-limited during the latest pass; do not claim a new interactive browser session from that pass. Managed/frozen smoke tests must set `AAC_ASSISTANT_NO_BROWSER=1` to avoid opening the user's default browser.

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

## Final near-duplicate consolidation wave (2026-08-12)

An area-by-area near-duplicate sweep (largest files → services → routers → stores → pages → mid-size components → hooks/lib/utils → providers) produced eight behavior-preserving commits, all pushed to `origin/080826_continuation`: one of them also fixed a latent production JWT bug found during the sweep.

| Commit | Change |
|---|---|
| `b049b02` | Remove orphaned `scripts/validate_database.py` (zero references anywhere; logic duplicated in `fix_null_passwords.py`) plus stale `scripts/__pycache__` artifacts |
| `4071e4a` | `settingsStore.ts`: three identical model-list fetch actions → one `fetchModelList(endpoint, stateKey, failureMessage)` helper |
| `6a8688e` | `prediction_service.py`: `_board_personal`/`_board_popular` (identical usage-ranked board queries) → one `_board_usage_symbols(user_id, confidence, source)` helper |
| `673f20c` | `board_ai.py`: duplicated find-or-create-symbol block → `get_or_create_symbol(db, label, symbol_key)` used by `create_board` and `apply_ai_suggestion` |
| `8c6cfb8` | `Communication.tsx`: three identical TTS utterance handlers → one `speakText` helper |
| `d4375dd` | `VoiceTab.tsx`: `installVoiceDependencies`/`installTTS` (identical flows) → one `runInstall(endpoint, timeoutMs, messages)` helper |
| `4d5093d` | **Bug fix + dedup:** `jwt_utils.py` `create_access_token` raised in production even with a valid secret — now guarded only when the placeholder secret is in use (`_require_secure_secret`); the near-identical token-encode blocks of `create_access_token`/`create_refresh_token` merged into `_encode_token`; `useAccessibleInteraction.ts` byte-identical `handlePointerUp`/`handlePointerLeave` merged behind `cancelDwell`; regression test added |
| `a77c723` | `providers/`: byte-identical HTTP-client close lifecycle (`_consume_close_task`/`close_async`/`close_sync` plus state) copied in `OllamaProvider`/`OpenRouterProvider` → hoisted into `BaseLLMProvider` |

Reviewed without change (verified non-duplicates): provider lifecycle functions (`providers.py`), pydantic schema inheritance (`schemas.py`), board-store mutation scaffolding, learning-store answer flows (already share `finishAnswer`/request-id guards), auth-store actions (divergent success paths), export/import and symbols routers, the four largest pages (already use shared `LoadingState`/`ConfirmDialog`/`SymbolGrid`), and `LearningModesTab`/`AiProviderFields` (per-provider differences are genuine).

Near-duplicate-wave validation (all green on `a77c723`; subsequent commits recorded the JWT smoke, build evidence, and handoff updates):

- Backend: Ruff clean, compileall clean, full pytest suite passed (1 expected skip), `git diff --check` clean.
- Frontend: typecheck passed, ESLint clean, 41 files / 197 tests passed, production build within bundle budgets (largest JS 333.9 kB / 450 kB budget).
- Footprint: 40,125 production lines, inside the 40,000–40,500 stop-condition target.
- `scripts/audit_codebase.py`: no broken internal imports. Dead-code audit confirmed every new helper is used by exactly its intended call sites and no stale references to removed code remain. The `jwt_utils` refactor leaves no stale references: private helpers are used only internally, all public API symbols have live production callers, and the module's `__init__` re-exports resolve.

## Live JWT login smoke test (2026-08-12)

Live end-to-end verification of the `4d5093d` JWT production fix. The server ran as a real uvicorn process on `127.0.0.1:8233` with **`ENVIRONMENT=production`** and a valid 32-character `JWT_SECRET_KEY` — the exact scenario the fix unblocked (previously `create_access_token` raised `ValueError` unconditionally in production, so login returned HTTP 500).

| Step | Result |
|---|---|
| `/api/health` | `200` `{"status":"online"}` |
| `/ready` | `200`, all 4 providers ready (speech, llm, achievement, vector_store) |
| `POST /api/auth/token` (`admin1`/`Admin123`) | `200` — `access_token` + `refresh_token` minted, `token_type: bearer` |
| Access-token claims | `sub=admin1, user_id=1, type=access, iss=aac-assistant`, `exp` in the future |
| `GET /api/auth/me` (Bearer access token) | `200` — `user: admin1 type: admin active: True` |
| `POST /api/auth/refresh?refresh_token=…` | `200` — new access token minted |
| `GET /api/auth/me` (refreshed Bearer token) | `200` — `user: admin1 type: admin` |
| Negative path (wrong password) | `401` — credentials rejected |

Note: the authenticated identity endpoint is **`/api/auth/me`** (the `auth_users` router mounts at `/api/auth`). `GET /api/auth/users/me` correctly returns `422` because it matches `/users/{user_id}` with `user_id: int` and `"me"` is not an integer — app behavior is correct, not a regression.

The harness cleaned up after itself (temp data dir removed, port closed, no stray processes) at that historical checkpoint; the current working-tree status is recorded at the top of this handoff.

## Final production build and bundle budgets (2026-08-12)

A fresh production build was run from `src/frontend` with `npm run build` after the JWT/provider/documentation updates.

- Build completed successfully in **5.25 seconds** with exit code 0.
- The repository bundle-size gate passed:
  - Largest measured JavaScript: **333.9 kB** (budget: 450 kB).
  - Largest measured CSS: **96.7 kB** (budget: 150 kB).
- The largest emitted JavaScript chunk was 341.91 kB raw / 108.74 kB gzip; the budget script's measured 333.9 kB value remained below the configured 450 kB limit.
- No bundle-budget warnings or build failures were reported.

The build produced no tracked changes and no generated artifacts were committed at that historical checkpoint; the current working-tree status is recorded at the top of this handoff.

## Release safety follow-up (2026-08-12)

The final installer/launcher safety cycle completed after the near-duplicate
wave and was committed and pushed as `b2bd6e4`:
`launcher.pyw`, `installer.iss`, the launcher/packaging tests, `README.md`,
`AGENTS.md`, `CONTINUE_PROMPT080826.md`, `docs/01_PROJECT_GUIDE.md`,
`docs/RELEASE_READINESS.md`, the historical plan/scenario status notices, and
`TEST_SCENARIOS` path corrections. That historical release-safety update
ended with a clean working tree; the current status is recorded at the top of
this handoff and currently contains pending changes.

- The installer now uses the same single-backslash `Local\\AACAssistantShutdown_`
  event namespace as the frozen launcher. It polls the path-matched process for
  up to 25 seconds before using the force-kill fallback, and aborts if the
  process remains.
- A rebuilt installer passed clean install, `/ready=200`, active upgrade with
  exit 0, graceful log evidence (`Shutting down AAC Assistant API...`), closed
  port, and preserved data/upload sentinels.
- A two-artifact isolated mechanics check passed `1.9.0 → 2.0.0 → 1.9.0`,
  preserving a valid SQLite database and upload sentinel and returning health
  200 after each transition. Both temporary artifacts used the current payload;
  this is installer/data-preservation evidence, not schema compatibility proof.
- `AAC_ASSISTANT_NO_BROWSER=1` now prevents the frozen launcher from opening
  the default browser. The rebuilt package passed a headless active-upgrade
  smoke on port 8258 with readiness, graceful shutdown, port closure, and data
  preservation. All test ports and temporary data were cleaned.
- Technical security review passed: internal import audit clean, focused security
  tests green, and `npm audit --omit=dev` reported 0 vulnerabilities.
- Complete gates passed after the change: backend suite with one expected skip,
  Ruff, compileall, frontend typecheck/lint, 41 Vitest files / 197 tests,
  production build, and bundle budgets (333.9 kB JS / 450 kB; 96.7 kB CSS /
  150 kB). PyInstaller rebuilt successfully with only existing optional hidden
  import/ctypes warnings; Inno Setup compiled with 0 errors and 0 warnings.
- `docs/RELEASE_READINESS.md` now documents physical SQLite backup, authenticated
  export/import recovery, operator versioned rollback, and the non-automated
  clinical/beta readiness requirements.

## Dependency cleanup verification (2026-08-12)

A fresh production-only dependency audit found no imports of the direct development dependency `requests`; the direct declaration was removed from `pyproject.toml` and `uv.lock` was regenerated without unrelated package changes. `requests` remains transitively required by `cachecontrol`, `fastembed`, and `pip-audit`, so it was intentionally not force-removed; this improves dependency accuracy but does not reduce the installed runtime footprint. `bcrypt` remains supported because the authentication service and password migration use it; `globby` remains because `src/frontend/scripts/i18n-audit.mjs` imports it.

The ten-pass review also confirmed that CI setup/build repetition is necessary because jobs use isolated runners, sample seeding is a small fixed dataset where batching would add complexity without measurable benefit, and no test-only production file or dead compatibility route was found.

## Current continuation verification (2026-08-12)

A fresh production build reproduced the JWT maintenance regression before the fix: the backend and readiness were healthy, but the forged-token browser flow emitted four `ReferenceError: Cannot access 'et' before initialization` page errors. The root cause was the static `api.ts` ↔ `authStore.ts` import cycle. The cycle is now removed through the small `src/frontend/src/lib/authState.ts` reader bridge; `api.ts` reads the bridge and `authStore.ts` registers its Zustand snapshot after initialization.

Post-fix evidence: focused frontend API/auth tests passed **33/33**, typecheck and ESLint passed, the production build passed, and the isolated production `maintenance.spec.ts` passed **5/5** (three fixture setup tests, settings-cache regression, and forged-token JWT regression) with no page errors. The isolated server reached `/ready` with all four providers ready and shut down cleanly; no traceback, timeout, proactor, or connection-reset diagnostics were found.

The latest ten-pass maintainability sweep found no additional safe production consolidation: image backfill is already bounded, export history is limited, and complete board/achievement export is intentional. The current working tree is pending and must not be represented as release-ready until intentionally committed and the complete gates are rerun after the bridge change. Interactive browser automation was not repeated because the browser agent returned a temporary rate-limit response; the focused Playwright production test is the available GUI evidence for this pass.

## Final readiness smoke follow-up (2026-08-12)

The earlier runtime shutdown discrepancy was reproduced with an unreliable
probe/log capture and was not accepted as a product failure. A repeatable
headless rehearsal was then run on isolated port 8247 with explicit
`Connection: close` probes:

- Supported `scripts/start_server.py` launcher reached `/api/health` in 4.24 s
  and `/ready` in 9.60 s; all four providers reported ready.
- `CTRL_BREAK_EVENT` produced a graceful wrapper exit code 0 in 0.27 s.
- The captured log contained `Application shutdown complete` and no traceback,
  connection-reset, or Windows proactor diagnostics.
- Temporary data, logs, processes, and the test port were cleaned.
- Focused lifecycle/packaging validation: 56 passed, 1 expected skip for the
  optional `faster-whisper` dependency, 0 failed; Ruff and diff checks passed.

Direct Uvicorn cold and warm runs also reached readiness and shut down in about
0.2 s, with exit code 3 caused by direct signal injection. The supported
launcher normalizes the controlled shutdown to exit code 0. This does not
claim clinical, hardware, clean-VM rollback, or real-user acceptance; those
remain the explicit release blockers in `docs/RELEASE_READINESS.md`.

## Current continuation validation (2026-08-12)

The lifecycle follow-up fixed a real test-resource race without changing production behavior: collaboration WebSocket tests now use isolated contextual `TestClient` fixtures, consume server close frames while the portal is alive, and preserve original assertion failures during cleanup; the board-router test removed its global `TestClient`. Generated `.phase3-e2e-data` and `.phase4-e2e-data` directories were removed.

- Backend: Ruff, compileall, and the complete pytest suite passed: **629 passed, 2 expected skips, 0 failed**. The skips are optional `faster-whisper` tests.
- Focused lifecycle regression: boards/collaboration tests passed **9/9 in three consecutive runs** with `PytestUnraisableExceptionWarning` promoted to an error; no closed-database warnings remained.
- Frontend: typecheck, ESLint, **42 Vitest files / 211 tests**, production build, and bundle budgets passed. Largest measured JS was 338.8 kB / 450 kB and CSS 96.7 kB / 150 kB.
- GUI E2E: after removing the production `api.ts` ↔ `authStore.ts` initialization cycle through `src/frontend/src/lib/authState.ts`, a fresh production build and isolated backend passed **107/107 Playwright tests**, with 0 skipped/failures and no unexpected page/server errors. The run used explicit fixture passwords, `PLAYWRIGHT_BASE_URL=http://127.0.0.1:8262`, and `AAC_ASSISTANT_NO_BROWSER=1`; the server reached readiness with all four providers and shut down cleanly.
- Runtime: isolated uvicorn smoke returned HTTP 200 from `/api/health` and `/ready`, reported all four providers ready, and left no matching pytest/uvicorn/python process. `uv lock --check`, production `npm audit` (0 vulnerabilities), `bash -n start.sh`, and `git diff --check` passed.
- Independent review found no material unresolved lifecycle, accessibility, security, or duplication issue. The only remaining warnings are third-party deprecations from `slowapi` and Starlette's TestClient/httpx integration.

The current pending changes still require an intentional commit/review before release; this handoff does not claim the working tree is clean.

## Offline packaging follow-up (2026-08-13)

The release now ships fully offline: `build_package.bat` syncs the `voice`
extra, runs `scripts/bundle_models.py` to stage the fastembed semantic-search
model and the `tiny` faster-whisper model into the gitignored
`bundled_models/models/` directory, and `AAC_Assistant.spec` bundles those
weights plus the faster-whisper/ctranslate2/av runtime and the silero VAD asset
into the package. `src/config.py` gained `get_bundled_models_dir()` and
`resolve_model_cache_dir()`; the vector store and speech provider now prefer the
read-only bundled cache with `local_files_only=True` and fall back to on-demand
download into `data/models/` only for non-bundled voice sizes.

Verified end-to-end: the rebuilt PyInstaller onedir and the Inno Setup installer
(~218 MB versus the earlier ~48 MB) were installed silently, and the installed
application — with `HF_HUB_OFFLINE=1` and no network — reached `/ready` with all
four providers, loaded both models from `_internal/models`, and transcribed a
real voice sample (`"Hello, and I want to practice on Amal's today."`).

Validation for this pass: backend **642 passed, 0 skipped, 0 failed** (the two
optional `faster-whisper` skips are gone because the extra is now installed);
frontend typecheck, ESLint, **42 files / 212 tests**, production build, and
bundle budgets passed; `ruff`, `compileall`, and `git diff --check` passed.
Regression coverage was added in `tests/test_model_cache_resolution.py`.

## GUI route follow-up (2026-08-12)

A fresh headless production-build check covered the previously untested legacy
speak-mode route. The new Playwright regression navigates to `/play/1` and
asserts the authenticated redirect to `/communication?boardId=1`; the focused
`advanced.spec.ts` run passed **8/8** including setup, with no failures. Frontend
typecheck and ESLint also passed. The current full GUI evidence is **107/107 Playwright tests passed** after the
latest frontend bridge change; the focused route follow-up remains additional
coverage, not a replacement for the full suite.

The route and 404 paths are now both directly covered. No production change was
needed: `/play/:id` is an authenticated compatibility redirect intentionally
implemented in `src/frontend/src/App.tsx` and used by the Boards and Board
Editor pages.

## Offline queue follow-up (2026-08-12)

The continuation pass added bounded, session-scoped offline mutation recovery:
JSON-safe requests are restored after reload for the same authenticated user,
Authorization headers are stripped before storage and replay, FormData and auth
flows are excluded from persistence, conflicts are user-bound, storage is size
bounded, malformed entries are discarded safely, and the current request remains
persisted until successful completion. Focused validation passed **28/28**
frontend tests across API/auth/conflict behavior, plus typecheck and ESLint.

The queue remains intentionally **at-least-once**. A crash after a server accepts
a mutation but before local dequeue can replay it; exact-once behavior requires
server-side idempotency keys or endpoint-specific idempotency. This is recorded
as a release limitation rather than hidden as a frontend guarantee.

## Stop condition

A reasonable target is approximately **40,000–40,500 production lines**. Stop before deleting supported compatibility behavior or introducing abstractions that make ownership less clear. The goal is a smaller, easier-to-maintain application—not the lowest possible line count.
