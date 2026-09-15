# PROMPT_6 — Refresh-rotation gaps, rate-limit holes, and frontend state/contract fixes

## 1. Mission

Implement the audited corrections below and leave the tree materially simpler and
more production-ready. This is **implementation work, not discovery**: every item
has been verified against the current tree with exact locations and required
changes. Fix them all with fail-before/pass-after evidence. Net code and
complexity must go down. Finish with a SHORT report (per item: files changed +
validation evidence).

## 2. Repository context

- AAC Assistant: FastAPI backend (`src/api`, `src/aac_app`, `src/config.py`) +
  React frontend (`src/frontend/src`) + SQLite (Postgres aspirations — SQLite
  silently over-stores over-width strings, so width bugs must be asserted at the
  validation layer). Groq is the production LLM provider; explicit-model rule in
  `generate()`, never the constructor.
- Latest iteration (PROMPT_5, Tiers H–R, 66 items) attempted: file integrity,
  account lifecycle, refresh rotation (`src/aac_app/services/
  refresh_rotation_service.py` + `src/aac_app/models/refresh_token.py` ledger),
  schema-width hardening, service correctness, frontend robustness. The working
  tree contains that large uncommitted sweep (~200 modified files) plus untracked
  `PROMPT_*.md`, the refresh ledger model/service, and new sweep tests.
- Constraints (AGENTS.md): no `.env`/DB/auth-artifact mutation (temp dirs +
  synthetic creds); named test files only (never bare `uv run pytest` /
  `npx playwright test` / `npm test -- --run` without file filters); offline
  queue fail-closed; strict moderation fail-closed; `log_event` isolated from
  caller transactions; `git diff --check` clean; stop all runners/servers at the
  end. Do not resurrect the deleted `LocalSpeechProvider.transcribe` alias. Do
  not run full suites unless explicitly authorized — use named files, then
  `scripts/verify_pr.py` only if a broad change genuinely requires it.

## 3. Starting procedure

1. `git status --short`, `git log --oneline -3`, `git diff --stat HEAD | tail`.
   Record baseline commit + modified files at the top of your work log.
2. Do §4 first (spot-verify high-risk PROMPT_5 claims + previous-agent claims),
   then implement §5 item by item (B1→B12). Reproduce every item before fixing
   (probe or failing test on current code).
3. Preserve legitimate in-flight work. Do not reset the tree.

## 4. Previous-iteration verification (you must re-check after your changes)

PROMPT_5 claimed 66 Tier H–R fixes. Spot-verified in the current tree:

| Claim | Verdict | Basis |
|---|---|---|
| H3 refresh rotation exists (ledger model/service, jti/family, grace window) | PARTIALLY VERIFIED — core exists but B1/B2/B3 gaps remain | `refresh_rotation_service.py:59-104`, `auth.py:574-634` bypass jti-less/`unknown`; `revoke_family` has zero production callers; `delete_user` never clears ledger |
| H1 lockout reset on all 4 creation paths | VERIFIED (code read) | resets present in all four paths |
| H4 SymbolUpdate excludes image/audio paths | VERIFIED (code read) | no `image_path`/`audio_path` in `SymbolUpdate` |
| H7 reset unlock + `10/hour` limiter | VERIFIED (code read) | unlock call + limiter present |
| H9 SSE per-user cap | VERIFIED (code read) | `MAX_STREAMS_PER_USER=5` → 429 |
| H29/H51 rehash without sec_ver bump | VERIFIED (code read) | no bump on rehash path |
| H30 achievement SQL filter, H34/H52 reasoning strip, H36 None-guard, H48 pickle=False+hashes | VERIFIED (code read) | present |
| H18 download anchor attach, H37 main.tsx fallback, H43 Sidebar catch, H38/H59 symbol-utterance preserve, H58 register confirm, H60 confirmBulkDelete filter | VERIFIED (code read) | present — but B4/B5/B6 show the same patterns incompletely applied nearby |
| Previous agent: "appended Live-Groq re-verification (2026-09-14) to PROD-FIXES.md; diff --check clean" | VERIFIED (doc present at `PROD-FIXES.md:1351`) / INSUFFICIENT EVIDENCE (live run) | section exists; server logs, key-handling, and `/ready` payload are not in the repo — re-confirm F03/F09/F10/F16 behavior yourself if you touch those paths; do not claim live validation you did not run |

Re-check high-risk interactions after your changes: refresh rotation vs
logout/replay/delete, limiter coverage vs TESTING bypass, bulk selection vs
ownership, text vs symbol submit contracts, vector error paths vs re-embed.

## 5. Audited defect backlog (verified — implement, don't re-investigate)

### B1 [P1] JTI-less and pre-rotation refresh tokens bypass single-use rotation
- Files: `src/api/routers/auth.py::refresh_access_token:574-634`,
  `src/aac_app/utils/jwt_utils.py::create_refresh_token:168-191`,
  `src/aac_app/services/refresh_rotation_service.py::status:59-84`,
  `::consume:87-104`.
- Current behavior: guard is `if isinstance(presented_jti, str) and
  presented_jti:` — `None`/empty `jti` skips the ledger entirely and mints +
  `record_issued`s a successor; `"unknown"` (never-issued/aged-out row) falls
  through with no consume and no replay check (`auth.py:599-601` comment admits
  it). `create_refresh_token` explicitly allows `jti=None`; `consume` only marks
  a found row.
- Evidence: control flow above; a pre-rotation token stays signature +
  `sec_ver` valid and is reusable until 7-day expiry, each use minting a new
  chain while the old credential stays live — the exact theft window H3 was
  supposed to close.
- Root cause: rotation treats the ledger as advisory for legacy tokens instead
  of enforcing single-use at the token layer.
- Required change: enforce rotation for every refresh: mint `jti` always (no
  `None` path for new tokens); on use, `unknown`/missing-`jti` tokens get
  one-time grace (mint successor + record) AND are bound so the presented token
  cannot be reused (e.g. record the presented `jti` if present, else rotate the
  family and invalidate the presented token via `sec_ver`/family handling —
  pick the smallest change consistent with the existing `sec_ver` machinery, no
  parallel revocation store). Document the legacy-transition rule in code.
- Expected: stolen pre-rotation refresh cannot mint repeatedly; normal refresh
  transparent; double-use of old refresh → 401 + family revocation.
- Validation: tests — jti-less token second use fails; `unknown`-`jti` second
  use fails; normal rotate-then-reuse-old → 401 + sessions revoked; concurrent
  same-token double exchange within grace still coalesces per existing client
  contract.

### B2 [P1] `delete_user` leaves the rotation ledger → FK failure on delete
- Files: `src/api/routers/auth_users.py::delete_user:687-857`,
  `src/aac_app/models/refresh_token.py:27-29`, `src/aac_app/db.py:86`.
- Current behavior: `delete_user` deletes ~15 associated tables including
  `FailedLoginAttempt` but never `RefreshTokenRecord`; model is
  `ForeignKey("users.id")` with no `ondelete` cascade, and `PRAGMA
  foreign_keys=ON` is set. Logout/replay paths use `revoke_user`; delete path
  does not.
- Evidence: call-site enumeration of the delete function vs model definition.
- Impact: admin `DELETE /api/auth/users/{id}` for any user that ever
  logged in/refreshed fails with FK `IntegrityError` (500).
- Required change: delete ledger rows for the user inside `delete_user`
  (reuse `revoke_user` or explicit delete) in the same transaction; consider
  `ondelete="CASCADE"` as belt-and-braces only if migrations support it —
  prefer the explicit delete, no new abstraction.
- Validation: test — create user → login/refresh (ledger row exists) → admin
  delete → 200 and zero ledger rows; previously 500/FK error.

### B3 [P2] Rotation `family` never validated; `revoke_family` is dead code
- Files: `refresh_rotation_service.py::status:59-84`, `::consume:87-104`,
  `::revoke_family:107-123`, `src/api/routers/auth.py:574-608`.
- Current behavior: `status`/`consume` filter only `jti+user_id`, never compare
  stored `family` vs presented `fam`; successor inherits `presented_family`
  verbatim with no binding check; repo-wide search shows zero production callers
  of `revoke_family`.
- Impact: `family` column is write-only metadata; chain-confusion not prevented;
  dead revocation API misleads future callers.
- Required change: either validate family (reject/mint correctly on mismatch
  and actually call `revoke_family` on replay per the H3 design) or delete
  `revoke_family` + `family` column usage and document user-scope revocation as
  the contract. Prefer the smaller coherent option; do not keep both a checked
  and an unchecked path. Per AGENTS.md production-only rule, dead code goes —
  remove the function if it stays uncalled.
- Validation: test for the chosen contract (mismatched-family replay →
  revocation, or grep + test proving no `revoke_family` references remain).

### B4 [P2] `duplicateBoard` stale-context early-returns orphan partial copies
- Files: `src/frontend/src/store/boardStore.ts::duplicateBoard:277-374`.
- Current behavior: cleanup (`api.delete(newBoardId)`) exists only in `catch`;
  six `if (!isCurrentMutation(context)) return;` exits after `newBoardId` is
  set (L306-308 link-resolve loop, symbol-copy loop, refetch) return silently
  with the created board + partial symbols left behind.
- Evidence: `newBoardId` assignment vs early-return sites vs catch-only delete.
- Impact: token/logout/board-switch mid-copy leaves orphan half-duplicates for
  manual deletion — the H57 fix closed the failure path but not the
  cancellation path.
- Required change: on every post-creation early-return, attempt best-effort
  `api.delete(newBoardId)` (or restructure so creation happens after all
  fallible reads resolve) — keep the existing catch cleanup, extend it to the
  stale-context returns.
- Validation: spec — inject mutation invalidation mid-copy (after creation) →
  no orphan board; success path byte-identical.

### B5 [P2] Text/voice answer submits discard user input on failure; symbol path fixed, others not
- Files: `src/frontend/src/pages/Learning.tsx::handleSend:353-365`,
  `::answerAndContinue:348-351`,
  `src/frontend/src/store/learningStore.ts::submitAnswer:553-580`,
  `::submitVoiceAnswer` (~same shape), `::submitSymbolAnswer:637-644`.
- Current behavior: `handleSend` does `const answer=input; setInput(''); await
  answerAndContinue(answer)`; `submitAnswer`/`submitVoiceAnswer` catch only
  `set({error...})` with no `throw`, while `submitSymbolAnswer` explicitly
  throws (H38/H59 comment) and its callers preserve the strip on failure.
- Impact: failed text/voice submit permanently discards the composed answer
  with no retry; inconsistent success/throw contract across three sibling
  methods.
- Required change: unify the contract — make `submitAnswer`/`submitVoiceAnswer`
  rethrow (like `submitSymbolAnswer`) and clear `input` only on success (restore
  on catch), mirroring the symbol path. No new state.
- Validation: specs — failed text submit preserves input + shows error; failed
  voice submit same; success clears.

### B6 [P2] Bulk selection state goes stale across account switch; select-all checkbox misreports
- Files: `src/frontend/src/pages/Boards.tsx:66-70` (state),
  `:98-128` (user/search effect), `:331-342` (`manageableBoards` +
  `toggleSelectAll`), `:354-356` (`confirmBulkDelete`), `:452` (checkbox).
- Current behavior: (a) `deleteBoardId/selectedBoardIds/bulkDeleteOpen/
  bulkDeleting/bulkDeleteError` persist across `userId:userType` change — the
  effect only updates request keys/fetches, unlike `Students.tsx:147-186` which
  clears on context change. Overlapping global IDs manageable by the new user
  can be deleted without the new user selecting them. (b) selection writes
  `manageableBoards` but `checked` compares against `boardsToShow`, so with any
  visible unowned board the box never shows checked.
- Required change: reset selection/dialog state when the user key changes; fix
  `checked` to compare against `manageableBoards.length` (or disable/hide the
  box when nothing manageable is visible).
- Validation: specs — switch user → selection/dialog cleared; mixed
  owned/unowned list → select-all checks the box and deletes only manageable.

### B7 [P2] Heavy write/import/AI endpoints have no rate limit (export-only coverage)
- Files: `src/api/routers/export_import.py::import_data:937` (no decorator vs
  `export_data:768-769 @conditional_limiter("10/hour")`),
  `src/api/routers/board_ai.py::create_board:149` (none vs
  `generate_ai_suggestions:406 "20/minute"`),
  `src/api/routers/symbols.py::create_symbol:332`, `::upload_symbol:404`,
  `::generate_svg_symbol:460` (none vs `get_symbols:199 "60/minute"`).
- Current behavior: `import_data` (1000 boards/assigned, 10k symbols, 10 MB
  body, atomic multi-table commit), AI `create_board` (LLM + up to 100
  `get_or_create_symbol` + inserts + indexing), and symbol mutations (file
  IO + optional LLM + vector indexing) are unbounded per user/IP.
- Impact: authenticated-user CPU/DB/write-lock amplification; staff-token abuse.
- Required change: add `conditional_limiter` rates mirroring siblings
  (import ≈ export `10/hour`; AI create ≈ suggestions scale; symbol mutations a
  modest per-minute bound) + short ARASAAC search cache if still absent (H8).
  No new frameworks.
- Validation: burst → 429 tests per endpoint; single calls unaffected.

### B8 [P2] Communication page never cancels TTS on exit (fixed everywhere else)
- Files: `src/frontend/src/pages/Communication.tsx:206-213` (status subscribe
  only; sole `cancelAll` is pre-speak at :416) vs `hooks/useSymbolHunt.ts:
  236-252` + `store/learningStore.ts:396,655,726` (cancel on exit/unmount).
- Current behavior: navigating away mid-speech leaves the singleton speaking
  with stale page state; `isSpeaking` rehydrates as speaking on remount.
- Required change: `tts.cancelAll()` in the unmount cleanup (and on
  boardless-exit transition if one exists), mirroring the hunt/learning paths.
- Validation: spec — unmount mid-speech → `cancelAll` called, no leaked audio.

### B9 [P2] SentenceStrip chips not keyboard/AT operable; remove button unlabeled
- Files: `src/frontend/src/components/board/SentenceStrip.tsx::SortableSymbol:
  56-79` (outer clickable `div` with `onClick` speak, no `role`/`tabIndex`/
  `onKeyDown`/`aria-label`; inner remove `button` with only an `X` icon, no
  `aria-label`) vs outer strip controls (all labeled).
- Impact: keyboard-only/switch/screen-reader users cannot preview chips or
  identify the remove control.
- Required change: proper button semantics + `aria-label` (parameterize remove
  with the symbol label, same pattern as the H45 utterance-chip item).
- Validation: role/name keyboard specs per control.

### B10 [P3] Vector error path fails open into a full re-embed
- Files: `src/aac_app/services/local_vector_store.py::get_stale_symbol_ids:
  324-359` (schema-unavailable correctly returns `set()` at :336; generic
  `except` at :357-359 returns `set(expected_texts)`), caller
  `vector_utils._index_all_symbols:88` treats it as "everything stale".
- Impact: transient DB/vector error amplifies into a full-catalog embed attempt
  instead of a no-op retry later (the H33/H55 item fixed the unavailable branch
  but not the exception branch).
- Required change: return `set()` on inspection failure (log + retry later),
  matching the unavailable branch.
- Validation: injected inspection failure → empty set, no re-embed; normal
  stale detection unchanged.

### B11 [P3] Multipart `language` unbounded; operator script loads whole user table
- Files: `src/api/routers/symbols.py:416,469`
  (`language: str = Form("en")` vs bounded siblings `label ≤100`,
  `description/keywords ≤10000`, `category ≤50`); `scripts/migrate_passwords.py:
  89,153` (`db.query(User).all()` twice, no chunking).
- Current behavior: multi-MB `language` buffered to the 12 MB ASGI cap before
  `normalize_language_code(...) or "en"` discards it; operator script O(N) ORM
  materialization.
- Required change: `max_length` (e.g. 10–16, matching the TTS `lang` 2–10 bound
  + BCP-47 slack) on both form fields; paginate/chunk the script queries
  (`yield_per` batches). One-line-class fixes, no new helpers.
- Validation: oversized `language` → 422; script handles large user fixtures in
  bounded memory.

### B12 [P3] Dead `family`/`revoke` residue + test-debt consolidation (tie-out)
- Files: B3 leftovers, plus `tests/test_refresh_rotation.py`,
  `tests/test_prod_sweep4_backend.py`, frontend sweep specs.
- Required change: as part of B3/B1, delete whatever becomes dead (unused
  imports, unreachable branches, superseded comments). Then consolidate tests:
  reuse existing suites, merge near-duplicate refresh/rotation/lockout tests,
  expand coverage only where a defect above lacks a discriminator, remove
  dead/superseded tests (e.g. any still asserting retired query-param refresh
  transport — the PROMPT_5 pass found two; re-check). Do not over-engineer new
  harnesses.
- Validation: `ruff`, `compileall`, named backend + frontend suites green,
  `git diff --check` clean; report which tests were merged/removed and why.

## 6. Simplification / deletion work

- B3/B12: delete `revoke_family` (and `family` plumbing if unvalidated) if it
  stays uncalled — do not keep checked and unchecked paths side by side.
- B5: one success/throw contract across `submitAnswer`/`submitVoiceAnswer`/
  `submitSymbolAnswer`; no new stores or flags.
- B6/B8/B9: narrower effects and existing `cancelAll`/label patterns; no new
  state, no new TTS singletons.
- B7: reuse `conditional_limiter`; no new middleware or config keys.
- B10/B11: return-empty / bound-existing-field fixes; no new helpers.
- No new dependencies, providers, middleware, or config keys.

## 7. Functional validation (real behavior, not just green suites)

- Refresh: normal login → refresh rotates transparently; old refresh reuse →
  401 + revocation; legacy/jti-less token cannot mint twice; delete-user with
  refresh history succeeds.
- Boards: duplicate mid-copy cancellation leaves no orphan; bulk select-all as
  teacher AND student respects ownership and reports honest checkbox state;
  account switch clears stale selection.
- Learning/Communication: failed text/voice/symbol submits preserve drafts +
  show errors in both callers; exiting Communication mid-speech silences TTS;
  chips operable keyboard-only.
- Heavy endpoints: bursts → 429, singles fine; oversized `language` → 422.
- Vector: injected inspection failure → no-op, no full re-embed.

## 8. Regression validation

- Named files only: backend tests covering auth/refresh/delete/limits/vector
  plus new targeted tests per B-item; frontend specs for touched
  stores/pages/components. Re-run affected Vitest files + `npm run typecheck`,
  `npm run lint`, `npm run build` if TS touched.
- `uv run ruff check src tests scripts`, `uv run python -m compileall -q src
  scripts`, `git diff --check`.
- Every item needs fail-before/pass-after evidence (probe output or pre-fix-
  failing test). Re-verify §4 high-risk rows after your changes.
- Test hygiene (§B12): reuse existing tests, merge near-duplicates, expand
  where a defect lacks a discriminator, remove dead/superseded tests with
  reasons. No full-suite runs without explicit authorization.

## 9. Cleanup after implementation

Remove superseded validators/comments/aliases, dead branches exposed by the
refactors, old/new parallel implementations, unused imports, and diagnostic
artifacts. Keep committed regression tests. Stop all runners/servers; confirm
the port is closed. Never commit `.env`, DBs, or auth artifacts.

## 10. Final bug hunt

Re-inspect every touched flow (rotation vs coalescing/WS revalidation/logout/
delete interplay; limiter coverage incl. TESTING bypass; bulk/duplicate
ownership; submit contracts in all three callers; TTS cancel paths; vector
error branches) for regressions, stale callers, newly dead code, and fresh
simplifications. Fix what you find; list what you explicitly ruled out.

## 11. Definition of done

- All B1–B12 fixed or blocked with demonstrated evidence; §4 rows re-verified.
- Targeted validations fail-before/pass-after where practical; named regression
  suites + lint/compile/build gates green; `git diff --check` clean.
- Obsolete/superseded code removed; duplicate logic consolidated; net
  complexity down.
- No known high-severity regression in touched flows.
- SHORT final report: per item, files changed + validation evidence. External
  gates (Windows rehearsal, human review, live CI/Groq runs) stay explicitly
  open unless actually executed with evidence.
