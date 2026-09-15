# PROMPT_1 — Fix verified follow-up defects from the F01–F16 production-hardening pass

## 1. Mission

The previous iteration (HEAD `133d790`, "Fix 16 audited production-readiness defects (F01–F16)")
did real, valuable hardening work. An independent audit re-verified every claim against the
workspace and found the fixes **directionally correct but incomplete in 9 specific, reproducible
ways**, plus 3 adjacent defects and 1 repo-hygiene problem. Your job: implement the 13 concrete
fixes below, each with a targeted validation that fails before and passes after. Leave the tree
**smaller and simpler** — consolidate duplicates, delete superseded code, do not add frameworks
or dependencies. Finish with a SHORT report (per-item: what changed, validation evidence).

## 2. Repository context

- Project: AAC Assistant — FastAPI backend (`src/api`, `src/aac_app`, `src/config.py`) + React
  frontend (`src/frontend/src`) + SQLite. Groq is the production LLM provider.
- HEAD `133d790` fixed F01–F16 (JWT secret validation, offline-persistence allowlist, refresh
  transport/coalescing, collab revalidation + caps, voice offload, fail-closed moderation,
  log redaction, Groq credential isolation, body bounds, log rotation, export link remap,
  safety-log transactions, CI prod gate, `/ready` DB probe). Full rationale lives in
  `PROD-FIXES.md` (read the F01–F16 fix notes before touching those files).
- Current branch is `fix/pagination-n1-e2e`. Working tree vs HEAD: one unstaged line in
  `tests/test_collab_ws.py` (dropped unused `TestClient` import) plus one **untracked** file
  `tests/test_export_link_remap.py` (295 lines) — see D13.
- Architectural constraints that must remain true: Groq's explicit-model requirement lives in
  `generate()`/`generate_sync()`, never `__init__` (model-listing builds a client from key
  alone); offline queue stays fail-closed (allowlist + sensitive rejection); strict moderation
  stays fail-closed; `log_event` stays isolated from caller transactions; no `.env`/DB/auth
  artifact mutation — use temp dirs + synthetic credentials; no full suites without explicit
  authorization (run named test files only); `git diff --check` clean at the end.

## 3. Starting procedure

1. `git status --short`, `git log --oneline -3`, `git diff HEAD --stat` — confirm the state above.
2. Read `PROD-FIXES.md` fix notes for any F-item you touch. Preserve all legitimate HEAD changes;
   you are completing them, not reverting them.

## 4. Previous-iteration verification (independent re-check — re-verify after your changes)

| Item | Claim | Verdict |
|---|---|---|
| F01 JWT secret validation | effective-secret check in prod | VERIFIED (spot-checked) |
| F02 offline allowlist | secrets rejected, board edits kept | VERIFIED |
| F03 refresh via body | frontend sends body | PARTIALLY VERIFIED → D5 (query fallback retained server-side, no removal plan) |
| F04 refresh coalescing | per-token map + epoch discard | VERIFIED, but sibling gap → D12 (login/setup error path unguarded) |
| F05 collab revalidation | 60s interval, idle receivers covered | PARTIALLY VERIFIED → D4 (non-403 swallowed; expiry checked only every 60s — folded into D4 fix) |
| F06 collab caps/pool | room cap, send timeout, session release | VERIFIED |
| F07 voice offload | to_thread + semaphore(2) + temp copy | PARTIALLY VERIFIED → D8 (sync file copy still on loop, before semaphore) |
| F08 fail-closed sentinel | errors/caps/ambiguity block; 600-char chunks | PARTIALLY VERIFIED → D2 (meter counts 1 row per N chunk-calls) |
| F09 log redaction | patcher + prod levels + no verbatim child/upstream logging | PARTIALLY VERIFIED → D1 (JSON/Bearer/header forms leak through redactor) |
| F10 Groq isolation | no OpenRouter fallback; DB→config→env | PARTIALLY VERIFIED → D9 + D10 (duplicated `__init__`; DB key unstripped in one path) |
| F11 body bound | ASGI 12MB pre-parse bound | PARTIALLY VERIFIED → D3 (413 skipped when app already responded) |
| F12 log rotation | 20MB rotation | VERIFIED |
| F13 links + truncation | second-pass remap, flush fix, name matching, meta.truncated | PARTIALLY VERIFIED → D6 + D7 (assigned↔assigned links lost; truncation invisible in API result + UI) |
| F14 safety-log isolation | isolated tx, 200-char detail, retention w/ meter guard | PARTIALLY VERIFIED → D11 (per-event COUNT/DELETE amplification; stale `db=` args) |
| F15 CI prod gate | `e2e-production-gate` w/o TESTING, /ready + 429 gates | VERIFIED (workflow read) |
| F16 /ready probe | bounded SELECT 1 | VERIFIED |

## 5. Audited defect backlog (all independently reproduced or code-traced — fix, don't re-investigate)

### D1 [P1] Log redactor misses the most common secret shapes — `src/api/logging_config.py::_redact_message`
- Behavior: `_redact_message('{"groq_api_key": "sk-supersecret123"}')` returns input **unchanged**;
  `'X-Groq-API-Key: sk-supersecret123'` unchanged; `'Authorization: Bearer sk-...'` becomes
  `'Authorization=*** sk-...'` — the secret itself survives. Only bare `key=value` is masked.
- Evidence: direct probe of the real function (3 LEAK cases above). JSON bodies and standard
  header renderings are exactly what provider error paths and request logs emit.
- Root cause: regex `key\s*[:=]\s*\S+` cannot match a quoted JSON key (`"key": "val"`) or
  space-separated `Bearer` credentials.
- Fix: extend redaction to (a) JSON `"key"\s*:\s*"value"` pairs for the same key set,
  (b) `Bearer\s+\S+` tokens, (c) `X-*-API-Key[:= ]\S+` header forms. Keep the 2000-char
  truncation. Add unit tests with synthetic canaries for each shape across a capturing sink.
- Validation: the 3 LEAK probes above must mask; existing log-hygiene behavior unchanged.

### D2 [P1] Sentinel cost meter undercounts chunked moderation ~N:1 — `src/aac_app/services/content_safety.py::moderate_output`
- Behavior: a ~5000-char text issues **9** `generate()` calls (one per 600-char chunk) but writes
  **1** `surface="sentinel"` row. Reproduced with a counting fake `generate` (9 calls / 1 row).
- Impact: `_count_sentinel_today` (the daily-cap meter) undercounts long-text spend up to ~10x;
  the daily cap is enforceable only for short texts.
- Fix: make meter == spend — either one audit row per spent chunk call, or a `call_count`
  recorded on the single row that `_count_sentinel_today` sums (preferred: single row + count
  column keeps the retention math intact). Update `_count_sentinel_today`, `_prune_events`
  meter protection, and `tests/test_export_link_remap.py` retention expectations accordingly.
- Validation: counting-fake test with multi-chunk text asserts meter increment == generate calls.

### D3 [P1] Body-bound 413 silently skipped when the app already responded — `src/api/main.py::_BoundedReceiveMiddleware`
- Behavior: both `send_413()` and the end-of-request `if overflowed: await send_413()` return
  without sending when `response_started` is true. An endpoint that swallows the abort and
  returns 200 therefore **succeeds on an oversized body** — contradicting the code's own
  "413 guarantee even when the app swallows the abort" comment. Fail-open.
- Fix: when overflow is detected after the app responded, close the connection with an error
  rather than leaving a 200 in place (e.g. raise/terminate the connection; at minimum log at
  warning with byte counts and do not present success). Document the chosen semantics next to
  the middleware. Add an ASGI-level test: oversized chunked body + abort-swallowing app must
  not yield a clean 200.
- Validation: declared-length → 413 (existing), chunked → 413 (existing), chunked +
  swallow-app → no clean success.

### D4 [P1] Collab revalidation swallows the errors it claims must propagate — `src/api/routers/collab.py::board_channel`
- Behavior: the inner `require_board_view_access` re-check has a careful comment — only 403
  means "revoked", anything else must propagate — but the enclosing `try/except Exception: pass`
  (line ~324) swallows that propagation, and transient DB failures also silently keep a
  potentially-revoked socket alive indefinitely with no log line.
- Fix: narrow the handler — 403 → close 1008; DB/transient failure → log warning with a
  consecutive-failure counter and close only after K consecutive failures (suggest K=3) so a
  blip doesn't mass-kick rooms but a revoked-while-DB-down socket cannot linger forever;
  non-403 policy errors → log + close 1011. Also check `token_exp` on **every** loop iteration
  (cheap integer compare, no DB) instead of only inside the 60s branch, closing the up-to-60s
  post-expiry window.
- Validation: tests for 403-close, transient-failure tolerance then close, and expiry enforced
  without waiting 60s (reuse `tests/test_acceptance_gaps.py` controllable-clock pattern).

### D5 [P2] Refresh-token query fallback retained with no sunset — `src/api/routers/auth.py::refresh_access_token`
- Behavior: server still accepts the 7-day credential from `request.query_params` indefinitely;
  F03's "no credential in URLs" holds only for the current frontend. Old clients/proxies keep
  logging it.
- Fix: emit a deprecation warning log (no secret) on query-param use, add a dated removal note
  in code + `docs/SECURITY_ARCHITECTURE.md`, and scope the fallback behind an explicit opt-in
  setting defaulting to off in production (fail-closed: production rejects query transport
  unless the operator deliberately re-enables it during migration).
- Validation: production-mode test — query refresh rejected/absent-token 400, body works;
  non-prod with opt-in still accepts query + logs deprecation.

### D6 [P2] Assigned↔assigned board links silently dropped on import — `src/api/routers/export_import.py`
- Behavior: `_remap_linked_boards` skips any source ID not in `imported`, and `imported` only
  ever contains **owned** boards (`_import_boards`), while assigned-created boards from
  `_import_assigned_boards` are never added. Links between two assigned boards (or from an
  assigned board created fresh this run) stay `None` forever. Also `_import_assigned_boards`
  sets `assigned_by=user.id` (self-assignment) — preserve the original assigner when present.
- Fix: return/include assigned-created boards in the remap map (second `_remap_linked_boards`
  call already exists — extend the map it receives), add a regression test with two linked
  assigned boards, and carry `assigned_by` from the payload when it names a real user.
- Validation: assigned↔assigned round-trip preserves links; forged-external links still cleared.

### D7 [P2] Export truncation is invisible to the user end-to-end — `export_import.py::import_data`, `src/frontend/src/pages/Settings/DataManagementTab.tsx`
- Behavior: export caps history at 100 with `meta.truncated/total_learning_sessions`, but
  `import_data` returns bare `{"ok": True}` and the UI shows only a success toast. A user
  recovering from export believes recovery is complete while history is truncated.
- Fix: return import counts + the export's truncation testimony
  (`{ok, boards, symbols, learning_history, truncated, total_learning_sessions}`) and surface
  it in `DataManagementTab` (success toast + persistent notice when `truncated` is true,
  using existing i18n keys pattern). No schema-version change; additive fields only.
- Validation: API test (137-session export → import result reports truncated/total) + UI test
  for the notice.

### D8 [P2] Voice file copy blocks the event loop before the offload — `src/aac_app/services/learning/responses.py::process_response`
- Behavior: the worker-temp-file copy (`open()` + `shutil.copyfileobj`, multi-MB synchronous
  I/O) runs on the event loop **before** `_voice_semaphore()`/`asyncio.to_thread` are entered.
  F07 offloaded transcription but left the I/O prologue on the loop.
- Fix: move the copy inside the semaphore-guarded `to_thread` section (copy in the worker
  thread; worker owns and deletes the copy), keeping the cancellation-safety property the
  comment describes. Keep the semaphore bound at 2.
- Validation: extend the F07 acceptance test — slow-copy + heartbeat concurrency; no model download.

### D9 [P2] `GroqProvider.__init__` duplicates the parent body — `src/aac_app/providers/groq_provider.py:17-30`
- Behavior: 14 lines duplicate `OpenRouterProvider.__init__` line-for-line (clients, model
  fields) with function-local imports, bypassing `super().__init__` solely to skip the
  OpenRouter key fallback. Any parent change (timeouts, headers, attrs) silently diverges.
- Fix: add a protected parent hook (e.g. `OpenRouterProvider.__init__(self, api_key=...,
  model=..., _api_key_env="GROQ_API_KEY" | None)` or a `_resolve_key` override point) and make
  `GroqProvider.__init__` a 3-line `super().__init__` call. No behavior change; delete the
  local imports.
- Validation: existing Groq/OpenRouter tests + matrix (Groq-only, OpenRouter-only, neither).

### D10 [P2] Groq effective-key whitespace handling differs per call site — `src/api/deps/providers.py::_effective_groq_key` vs `src/api/routers/board_ai.py`
- Behavior: deps returns the DB key **unstripped** (`if db_key: return db_key`) while board_ai
  strips. A padded DB key fails one path and works the other, and the singleton reuse compare
  (`strip() != api_key`) thrashes (recreates clients per request) for padded keys.
- Fix: strip once inside `_effective_groq_key`, export it, and make `board_ai` call the shared
  helper instead of its own inline precedence chain (deletes the near-duplicate).
- Validation: padded-key test — both paths resolve identically, singleton reused.

### D11 [P2] Safety `log_event` costs COUNT+SELECT+DELETE per call; ~10 stale `db=` pass-throughs — `content_safety.py`, callers
- Behavior: every `log_event` runs `COUNT(*)` over the whole table + retention select/delete.
  The collab label path calls it per blocked label, so anyone who can send labels can force
  repeated full-table counts (table grows to 10k) — log-spam → DB amplification. Separately,
  ~10 call sites (`questions.py:220`, `responses.py:201,520`, `summaries.py:77`,
  `prediction_service.py:675,1033,…`, `session.py:99`) still pass `db=` to a parameter that is
  now deliberately ignored — misleading ownership signal.
- Fix: throttle retention enforcement (e.g. probabilistic or at-most-once-per-N-calls/minute
  per process, still always enforced on the same isolated session when it runs), and remove
  the dead `db=` arguments at call sites (keep the compat kwarg on the function or remove it
  if all call sites are cleaned — prefer full removal if no external callers exist; verify by
  repo-wide search first).
- Validation: retention still bounded under spam; blocked-label flood test shows bounded query
  count per event; `ruff` clean.

### D12 [P2] Stale login/setup failure overwrites a newer session — `src/frontend/src/store/authStore.ts`
- Behavior: `login`/`setupAdmin` guard **success** with epoch checks but the `catch` blocks call
  `set({ error... })` unconditionally. A slow failed login started before a newer successful
  login stamps its error onto the new session.
- Fix: capture the epoch result the same way (`isStillCurrentLogin()`/`isStillCurrentSetup()`)
  in the catch path and skip publishing when stale. Mirror the existing refresh-discards-stale
  tests for login→login and setup→login.
- Validation: deferred-failure-after-newer-login test — newer session keeps `error: null`.

### D13 [P3, process] Claimed F13 evidence is not committed on this branch
- Behavior: `PROD-FIXES.md` + HEAD message claim `tests/test_export_link_remap.py` (7 tests),
  but the file is **untracked** (`??` in `git status`) and HEAD's stat doesn't contain it;
  `tests/test_collab_ws.py` has an unstaged 1-line fix. The link-remap/retention safety net
  exists on disk only — a checkout/CI run from HEAD never executes it.
- Fix: review the untracked file, move the shared `collab_client` fixture consistently
  (it already moved to `conftest.py`), run the named files, and commit both test files on
  this branch. Do not lose the 7 tests.
- Validation: `git status --short` clean for those paths; named pytest runs green from a fresh
  checkout state.

## 6. Simplification / deletion work (do as you go, not as a separate phase)

- D9 + D10 remove two near-duplicate credential-resolution paths; end state: exactly one
  `_effective_groq_key` used by both `deps/providers.py` and `board_ai.py`.
- D11 removes all dead `db=` pass-throughs (and the compat kwarg if the repo-wide search
  proves no external callers).
- D3: collapse the two `send_413` call sites into one overflow-resolution path with documented semantics.
- D4: hoist the per-connection `import time` / `create_session_factory` / model imports in
  `collab.py` to module top level (they run per-socket today).
- No new abstractions, wrappers, or config keys except the D5 transitional opt-in (which must
  have a dated removal note).

## 7. Functional validation (real behavior, not just old tests)

- Refresh marathon: body refresh, expired/revoked/malformed refresh, query fallback per D5
  semantics — no token ever in a URL in the default path (assert on request targets).
- Collab lifetime: idle receiver closed on deactivation / sec_ver bump / assignment removal /
  expiry without waiting 60s (extend `tests/test_acceptance_gaps.py` patterns).
- Import round-trips: cyclic owned links, assigned↔assigned links (new), forged-external
  cleared, retry merges (no clones), 137-session truncation reported through API + UI.
- Strict moderation: multi-chunk text — blocked verdict correct AND meter increment equals
  spent calls; cap enforced for long texts.
- Oversized bodies: declared-length and chunked 413s, plus the abort-swallowing app case.
- Secret hygiene: JSON/Bearer/header canary probe across the redactor and one live sink.

## 8. Regression validation

- Named files only (per AGENTS.md): `tests/test_acceptance_gaps.py`,
  `tests/test_export_link_remap.py`, `tests/test_content_safety.py`,
  `tests/test_phase2_security.py`, `tests/test_collab_ws.py`, plus affected frontend specs
  (`authStore.test.ts`, `offlinePersistence.test.ts`, DataManagement tests).
- `uv run ruff check src tests scripts`, `compileall -q src scripts`,
  frontend `typecheck`/`lint` if TS touched, `git diff --check`.
- Every D-item needs a validation that would have failed before the fix (new test or
  documented probe command + output).

## 9. Cleanup after implementation

- Remove superseded inline precedence chain in `board_ai.py`, dead `db=` args, swallowed
  `except: pass` blocks you replace, and the duplicated provider `__init__` body.
- Commit the D13 test files. Kill any background servers/runners you start; verify none remain.

## 10. Final bug hunt

Re-inspect every touched flow for: regressions, half-migrated old/new paths coexisting,
stale callers of changed helpers, newly dead code, and new simplification opportunities.
Verify the F-verdict table in §4 still holds after your changes.

## 11. Definition of done

- All 13 items addressed or blocked with demonstrated evidence; net code/complexity down.
- §4 re-verified post-change; targeted validations fail-before/pass-after where practical.
- Named regression tests + lint/compile gates green; `git diff --check` clean.
- SHORT final report: per item, files changed + validation evidence (no long prose).
