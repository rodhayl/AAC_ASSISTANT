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

- Total: approximately **41,032 lines**
- `src/frontend/src`: 18,803
- `src/aac_app`: 10,619
- `src/api`: 9,098
- `scripts`: 1,408
- `src/scripts`: 88

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

## Stop condition

A reasonable target is approximately **40,000–40,500 production lines**. Stop before deleting supported compatibility behavior or introducing abstractions that make ownership less clear. The goal is a smaller, easier-to-maintain application—not the lowest possible line count.
