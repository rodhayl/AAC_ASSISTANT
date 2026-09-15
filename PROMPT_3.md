# PROMPT_3 — Wire up outcome reporting, fix register-epoch regression, harden body/timeout paths

## 1. Mission

The last two iterations did strong work: `bb0c4a0` fixed D1–D13, and the current uncommitted
working tree on `fix/pagination-n1-e2e` implements the PROMPT_2 backlog (N1–N12) **plus** rigorous
regression tests for previously untested branches (D4/D7/D8/D9/D11, F06 room cap, F16 DB loss,
refresh-transport matrix). The audit verified all of it: 193 backend tests green across 10 named
files, 29 frontend tests green in the 2 touched specs, ruff/compileall/diff-check clean, and live
probes confirm the N1 (owned→assigned link), N2 (redactor bypass + brace-eating), and N7
(bool `assigned_by`) fixes behave as claimed. The N3 `db=` cleanup is complete (remaining `db=`
hits are `AuditLogService`'s own legitimate signature), the N4 single-hook provider resolution
holds (matrix test green), and the corrective-note restoration (`_PredictionContext(db=db)` etc.)
was verified intact in the tree.

Your job: implement the 11 concrete residual defects below — all independently evidenced, none
requiring rediscovery. Several are small regressions/complexity introduced by the recent passes
themselves. Net code must stay flat or shrink. Finish with a SHORT report (per item: files
changed + validation evidence).

## 2. Repository context

- AAC Assistant: FastAPI backend (`src/api`, `src/aac_app`, `src/config.py`) + React frontend
  (`src/frontend/src`) + SQLite. Groq is the production LLM provider; explicit-model rule lives
  in `generate()`/`generate_sync()`, never `__init__`.
- History: `133d790` (F01–F16, rationale in `PROD-FIXES.md`) → `bb0c4a0` (D1–D13) →
  current uncommitted tree (N1–N12 + coverage for D4/D7/D8/D9/D11 gaps; dispositions recorded in
  `PROD-FIXES.md` "Follow-up pass — 2026-09-13 (N1–N12)" and "Verification pass" sections).
- Constraints (AGENTS.md): no `.env`/DB/auth-artifact mutation (temp dirs + synthetic creds);
  named test files only; Groq stays production provider; offline queue fail-closed; strict
  moderation fail-closed; `log_event` isolated from caller transactions; `git diff --check`
  clean; kill background runners. Do not re-run full suites.

## 3. Starting procedure

1. `git status --short` (expect ~27 modified files, no staged changes), `git log --oneline -2`
   (expect `bb0c4a0` on `fix/pagination-n1-e2e`), `git diff --cached --stat` (expect empty).
2. Reproduce each Q-item's probe **before** fixing for fail-before evidence.

## 4. Previous-iteration verification (independently re-checked — re-verify after your changes)

PROMPT_2 N1–N12 + prior coverage gaps, verified by probe/code inspection/test runs:

| Item | Verdict | Evidence |
|---|---|---|
| N1 owned→assigned remap | FIXED | temp-probe passes (`linked_board_id` correct); combined pass in `import_data` |
| N2 redactor exact-guard + unquoted JSON | FIXED | probe: `foo***bar`, `{"token": 12345678}`, single-quotes all masked; perf 0.35ms |
| N3 `db=` removal + kwarg deletion | FIXED | 17 removals; signature test asserts no `db`/`session` param; `_PredictionContext(db=db)` intact |
| N4 single `_resolve_api_key` hook | FIXED | `_api_key_env` gone; key-matrix test green |
| N5 `isLoading` ownership | FIXED | `emptyAuthState` has `isLoading:false`; 4 new specs green — but register regressed → Q2 |
| N6 outcome counts | FIXED | retry reports `boards_created=0/merged=2` — but UI ignores them → Q1; clamps → Q10 |
| N7 `assigned_by` bool guard + validation | FIXED | temp-probe: `True` falls back to importer |
| N8 dead `except HTTPException` | FIXED | handler deleted |
| D4/D7/D8/D9/D11 new tests | VERIFIED | exercise real production code (thread-identity, ASGI harness, SQL counting); 193 passed |
| D5 refresh matrix, F16 DB-loss, F06 room-cap tests | VERIFIED | endpoint-level, pass |
| N10 abort test, N11 comment move, N12 coerce | FIXED | green; coerce covered by bad-`call_count` test |
| Previous agent's fail-before story (6/7 fail pre-fix) | INSUFFICIENT EVIDENCE (not re-run) | accepted on code-reading plausibility; your Q-items each need their own fail-before proof |

## 5. Audited defect backlog

### Q1 [P1] Import warning shows input lengths, outcome keys are write-only — `DataManagementTab.tsx`, `export_import.py`
- Demonstrated: `grep -rn "learning_history_added\|boards_created" src/frontend/src` → **zero hits**.
  The toast uses `body.learning_history` (payload input length), so an idempotent retry that adds
  0 rows still reports "showing 100 of 137". Worse, `total_learning_sessions` is only present
  when the meta value is an int — a `truncated:true` payload without it renders "of undefined".
- Root cause: N6 added outcome keys server-side but never wired the single consumer.
- Fix: toast prefers `learning_history_added` (fallback to `learning_history` for old servers);
  guard non-numeric `total` (fall back to the success toast or omit the count rather than
  printing "undefined"). Extend the N9 spec: retry-shaped result (`added: 0`) and missing-total
  result cases.
- Validation: new specs fail before (assert on `added`/no-"undefined"), pass after.

### Q2 [P2] N5 made `register` bump the session epoch — it publishes no session state — `authStore.ts`
- Demonstrated by code: `register` now does `loadingOwnerEpoch = ++checkAuthEpoch`, so starting
  a registration invalidates an in-flight login/checkAuth/refresh (a valid login success is then
  silently dropped by its epoch guard). Its own `catch` is also unguarded (`set({error...})`
  unconditionally), so a late register failure can stamp `registrationFailed` over a newer login
  session — the exact bug class D12/N5 just fixed elsewhere.
- Root cause: register was given a session-epoch ownership it must never hold; it changes no
  session identity.
- Fix: register must not bump `checkAuthEpoch`. Give it staleness-guarded sets consistent with
  login/setup (capture epoch without incrementing, guard both success-spinner and error sets
  against newer session owners), or scope it to `loadingOwnerEpoch` only. Add specs:
  register-start → login-wins → register-settles-changes-nothing; login-in-flight → register-starts
  → login-success-still-publishes.
- Validation: specs fail before (login success dropped / error stomped), pass after.

### Q3 [P2] D5 production re-check is dead-equivalent complexity — `auth.py::refresh_access_token`
- Demonstrated by code: `allow_query = config.get_bool(KEY, False)` is then AND-ed in prod with
  `str(config.get(KEY,"")).strip().lower() in {"1","true","yes","on"}` — the identical predicate
  `get_bool` already applies to the identical source (`get` = env-over-settings). The `if is_prod`
  branch can never change the outcome; three lookups where one suffices.
- Fix: extract `refresh_query_fallback_allowed()` (name it plainly, e.g. in `src/config.py` next
  to the setting, which N11 already relocated near the JWT block) implementing the single rule
  "explicit opt-in only", call it once from the endpoint, delete the branch. Lock with the
  existing D5 matrix tests (must stay green unchanged).
- Validation: D5 tests green; `grep` shows one lookup site; behavior identical in all 4 cells
  (prod/dev × set/unset).

### Q4 [P2] Body bound has no receive timeout — slow-loris holds workers — `main.py::_BoundedReceiveMiddleware`
- Demonstrated by code: `bounded_receive()` awaits `receive()` unboundedly, and the drain loop is
  the only place with a timeout. A client that trickles bytes under 12MB forever holds a worker
  and (for WS-adjacent HTTP) pool resources; the byte bound does not bound *time*.
- Fix: wrap the request-body wait with a bounded inactivity timeout (suggest per-read ~20–30s,
  consistent with existing 0.5s drain granularity and server timeouts); on expiry treat as abort
  → same `resolve_overflow`/abort semantics, warning log with bytes + elapsed. Cover declared,
  chunked, and stalled-mid-body shapes in the ASGI harness test.
- Validation: stalled-body test aborts instead of hanging (use short timeout injection, not real
  30s waits); existing 413 tests green.

### Q5 [P2] Private cross-module import of the Groq key helper — `board_ai.py`, `deps/providers.py`
- Demonstrated: `board_ai.py` does a function-local `from src.api.deps.providers import
  _effective_groq_key` — a private name imported across modules, undiscoverable and
  rename-fragile, now that N10 made it the canonical resolver for two call sites.
- Fix: export a public alias (e.g. `resolve_groq_api_key()`) from `deps/providers.py`, keep the
  private name as a deprecated alias only if external imports exist (verify by search), and use
  the public name in both callers. No behavior change.
- Validation: search shows no `_effective_groq_key` imports outside its module; key-matrix and
  singleton tests green.

### Q6 [P3] Collab shutdown comment claims a revocation that doesn't happen — `collab.py`
- Demonstrated: comment "revoke global event so local wait doesn't see stale shutdown" sits above
  `shutdown_event = None`, which revokes nothing — it merely ignores the global event when
  lifespan is inactive and allocates a local one below.
- Fix: rewrite to what the code does ("ignore the lifespan event outside lifespan; use a local
  event so tests don't observe production shutdown"), one line. No behavior change.
- Validation: comment/code agreement on re-read; collab tests green.

### Q7 [P3] Voice guard tests the wrong variable — `responses.py` (`elif is_voice and not audio_data`)
- Demonstrated by control flow: the `if` takes `audio_data or audio_path`, so the `elif` is
  reachable only when both are falsy — yet it names only `audio_data`, inviting a future edit to
  break the no-audio path (e.g. path-only uploads rejected as "No audio data").
- Fix: `elif is_voice and not audio_data and not audio_path:` (explicit), keeping the same
  "No audio data received." contract. Add a unit test for voice-with-neither-inputs.
- Validation: new test passes; F07/D8 voice tests green.

### Q8 [P3] First `log_event` in every process always runs retention — `content_safety.py`
- Demonstrated by code: `_last_prune_monotonic = 0.0`, so `now - 0 >= _PRUNE_THROTTLE_SECONDS` is
  true on the first event of every process boot → one full-table `COUNT(*)` on a hot path that
  the D11 throttle was built to avoid.
- Fix: initialize the throttle state lazily (first call sets the baseline without pruning, or
  sentinel value `None` meaning "no baseline yet"). Keep the D11 count/window semantics and the
  three throttle tests green (they set the globals explicitly and are unaffected).
- Validation: instrumented test — first-ever `log_event` with a fresh module state performs no
  `SELECT COUNT`; second within window performs none either until N calls/window.

### Q9 [P3] `moderate_output` spends a paid call on empty text — `content_safety.py::moderate_output`
- Demonstrated by code: `chunks = [...] if full_text else [""]` forces one `generate()` round-trip
  for `""`, billed as `call_count=1`, to gate an empty string whose publication is unobservable
  either way (allowed→empty passes through; blocked→empty suppressed — same downstream text).
- Fix: short-circuit falsy/blank text to `Verdict(allowed=True)` with **no** audit row and no
  `generate` call (meter unchanged — nothing was spent), documenting that empty output needs no
  verdict. Strict fail-closed posture is preserved: any non-blank text takes the full path.
- Validation: test with counting `generate` — empty/whitespace text → 0 calls, 0 new sentinel
  rows, allowed verdict; existing strict tests green.

### Q10 [P3] N6 `max(0, …)` clamps hide over-creation anomalies — `export_import.py::import_data`
- Demonstrated by code: `_boards_created = max(0, after - before)` and `_boards_merged =
  max(0, inputs - created)` — if a future bug clones on retry (the exact F13 defect class),
  `created > inputs` manifests as `merged = 0` instead of the impossible negative that would
  scream. An integrity signal is clamped into a plausible-looking lie.
- Fix: report raw deltas (allow the arithmetic to speak) and let the API test assert the
  invariant `created + merged == inputs` on retry; keep aliases untouched.
- Validation: retry test asserts the invariant; a synthetic over-creation scenario surfaces
  instead of clamping.

### Q11 [P3] Redactor `is`-shape is English-only in a Spanish-first app — `logging_config.py`
- Demonstrated by code: pattern 4 covers `password is <v>` but the product is Spanish-first
  (see `responses.py` language default); a translated log rendering `password es <v>` (or
  `contraseña es <v>`, if keys ever localize) passes the `is`-pass. The bare `=`/`:` pass still
  catches `password=...` shapes, so this is a narrow gap in one new pattern, not a leak class.
- Fix: extend the copula alternation to `(is|es)` with a test locking both, or document the
  English-only scope in the pattern comment if deliberately out of scope. Do not broaden the key
  list without evidence.
- Validation: `password es hunter2` masked (or scope documented + test asserting current behavior).

## 6. Simplification / deletion work

- Q3 (one lookup, one helper), Q5 (public alias, delete private cross-module use), Q6 (comment
  repair), Q10 (raw deltas, no masking arithmetic).
- Do not add config keys, providers, middleware layers, or abstractions. Q4 reuses the existing
  `resolve_overflow`/abort path — no new error type.

## 7. Functional validation

- Import matrix (API level): cyclic/cross-section links incl. owned→assigned (N1 lock), retry
  invariant `created + merged == inputs`, `assigned_by` edges, truncation flags with
  added-counts, `total` missing → no "undefined" in UI.
- Refresh matrix (existing D5 tests): behavior identical after Q3 refactor in all 4 cells.
- Redactor canaries: prior 8 shapes + `es`-copula + exact-`***` guard + single-quote pairs.
- Voice: neither-inputs rejection; slow-copy thread-identity test still green.
- Sentinel: empty text costs 0 calls; long text still bills `spent`.
- Stall test: mid-body stall aborts via Q4 timeout; declared/chunked 413s unchanged.

## 8. Regression validation

- Named files only: `tests/test_export_link_remap.py`, `tests/test_new_features.py`,
  `tests/test_content_safety.py`, `tests/test_collab_ws.py`, `tests/test_acceptance_gaps.py`,
  `tests/test_phase2_security.py`, `tests/test_groq_provider.py`, `tests/test_logging_config.py`,
  `tests/test_password_reset_security.py`, plus frontend `authStore.test.ts`,
  `DataManagementTab.test.tsx`.
- `uv run ruff check src tests scripts`, `python -m compileall -q src scripts`, frontend
  `typecheck`/`lint` if TS touched, `git diff --check`.
- Each Q-item needs fail-before/pass-after evidence (probe output or new test run against
  pre-fix code).

## 9. Cleanup after implementation

- Remove the dead D5 branch (Q3), the private import (Q5), misleading comment (Q6); no old/new
  parallel paths left standing.
- Delete temp probe files; keep only committed regression tests. Stop all runners/servers.

## 10. Final bug hunt

Re-inspect touched flows (auth epoch interplay incl. `register` vs `login` vs `checkAuth`,
middleware timeout vs drain-timeout interaction, redactor pass ordering with the new copula,
import count arithmetic on partial-failure rollback) for regressions, stale callers, newly dead
code, and fresh simplifications.

## 11. Definition of done

- All 11 Q-items fixed or blocked with demonstrated evidence; net complexity flat or down.
- §4 re-verified post-change; targeted validations fail-before/pass-after where practical.
- Named regression tests + lint/compile gates green; `git diff --check` clean.
- SHORT final report: per item, files changed + validation evidence.
