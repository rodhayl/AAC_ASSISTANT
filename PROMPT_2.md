# PROMPT_2 — Complete the D1–D13 follow-ups and fix verified residual defects

## 1. Mission

HEAD `bb0c4a0` ("Fix 13 follow-up defects D1–D13", on `fix/pagination-n1-e2e`) implemented the
PROMPT_1 backlog. An independent audit re-verified every D-item against the workspace with live
probes: **9 of 13 fully verified, 4 partially verified or incorrect**, plus new defects found
in the changed code. Your job: fix the 12 concrete items below — each has demonstrated behavior,
root cause, required change, and validation. Net code must go **down** (several items are pure
deletion/consolidation). Finish with a SHORT report (per item: files changed + validation
evidence, no long prose).

## 2. Repository context

- AAC Assistant: FastAPI backend (`src/api`, `src/aac_app`, `src/config.py`) + React frontend
  (`src/frontend/src`) + SQLite. Groq is the production LLM provider; its explicit-model rule
  lives in `generate()`/`generate_sync()`, never `__init__`.
- Iteration history: `133d790` fixed F01–F16 (rationale in `PROD-FIXES.md`); `bb0c4a0` fixed
  D1–D13 (rationale in its commit message + `PROMPT_1.md`). Read both before touching those files.
- Constraints (AGENTS.md): no `.env`/DB/auth-artifact mutation (temp dirs + synthetic creds);
  named test files only, never full suites without authorization; Groq stays production provider;
  offline queue stays fail-closed; strict moderation stays fail-closed; `log_event` stays
  isolated from caller transactions; `git diff --check` clean; kill background runners.

## 3. Starting procedure

1. `git status --short`, `git log --oneline -3` — expect clean tree on `fix/pagination-n1-e2e`
   at `bb0c4a0` (plus untracked `PROMPT_1.md`, a prompt artifact — leave it).
2. Reproduce each N-item's probe **before** fixing (commands given), so you have fail-before
   evidence.

## 4. Previous-iteration verification (independently re-checked — re-verify after your changes)

| Item | Verdict | Note |
|---|---|---|
| D1 redactor (JSON/Bearer/X-Key) | VERIFIED | probe: all 4 shapes masked |
| D2 sentinel `call_count` meter | VERIFIED | probe: 9 chunk calls → `call_count=9` |
| D3 overflow substitution/abort | VERIFIED (code) | but no regression test → N10 |
| D4 collab narrow handler + per-iteration expiry | VERIFIED (code) | dead handler residue → N8 |
| D5 refresh opt-in fallback | VERIFIED | comment misplacement → N12 |
| D6 assigned↔assigned remap | PARTIALLY VERIFIED | owned→assigned still lost → N1 |
| D7 truncation surfacing | PARTIALLY VERIFIED | counts are inputs → N6; UI branch untested → N9 |
| D8 voice copy in worker | VERIFIED (code) | — |
| D9 provider hook | PARTIALLY VERIFIED | dual mechanism, dead override → N4 |
| D10 stripped shared key | VERIFIED | — |
| D11 prune throttle | PARTIALLY VERIFIED | throttle works; `db=` cleanup **not done** (21 remain) → N3 |
| D12 stale login/setup guard | VERIFIED (code) | branch untested → N9; `isLoading` gap → N5 |
| D13 tests committed | VERIFIED | 106 passed (5 named files + acceptance gaps re-run) |

Gates re-run in audit: `pytest` 106 passed
(`test_content_safety`, `test_export_link_remap`, `test_collab_ws`, `test_phase2_security`,
`test_password_reset_security`), `test_acceptance_gaps` 9 passed, `ruff` clean, `compileall`
clean, `git diff --check` clean.

## 5. Audited defect backlog (your implementation scope — fix, don't re-investigate)

### N1 [P1] Owned→assigned board links still dropped on import — `src/api/routers/export_import.py`
- Demonstrated: probe importing owned board O (links to source-ID 20) + assigned board A
  (source-ID 20) via the real `_import_boards` → `_import_assigned_boards` → `_remap_linked_boards`
  sequence prints `OWNED_LINK: None EXPECTED: 2` — assertion fails on current HEAD.
- Root cause: the first `_remap_linked_boards` runs inside `_import_boards` **before** assigned
  boards exist (target missing → skipped), and the second call only iterates `assignedBoards`
  sources, so owned sources are never revisited once their target arrives.
- Fix: after `_import_assigned_boards` populates the shared map, re-run the remap over the
  **combined** board list (or move the single remap pass after both imports). Add the probe as a
  regression test in `tests/test_export_link_remap.py` (owned→assigned + assigned→owned).
- Validation: probe passes; existing 7 link tests + retry-merge tests green.

### N2 [P1] Redactor bypass via `***` substring + brace-eating on unquoted JSON — `src/api/logging_config.py::_redact_message`
- Demonstrated: `_redact_message('my password is foo***bar baz')` returns input **unchanged**
  (proven LEAK probe); `_redact_message('{"token": 12345678}')` yields `'{token=***'` — masked
  but the closing brace is eaten by bare-pattern `\S+`.
- Root cause: the D1 double-mask guard tests `"***" in group(0)` (substring) instead of
  `value == "***"` (exact), so any real secret containing three asterisks evades all passes;
  the bare pattern has no value-shape awareness for JSON.
- Fix: guard on exact masked value (`== "***"`, allowing the JSON `"***"` quoting), and make
  the JSON pass also cover unquoted scalar values (`"key": 12345` / `true` / `null`) without
  consuming structural braces. Extend redactor unit tests with both cases.
- Validation: both probes mask correctly; D1's 8-shape probe still fully masked.

### N3 [P2] D11's claimed `db=` cleanup never happened — 6 safety call sites + 15 neighbors
- Demonstrated: `grep -rn "log_event(" src -A 8 | grep -c "db="` → **21**, including
  `questions.py:220`, `responses.py:208,527,573,632`, `session.py:110`, `summaries.py:77`,
  `prediction_service.py:675,…` — all still passing `db=` to a parameter that is deliberately
  ignored, signaling a false ownership contract to readers.
- Fix: remove the dead `db=` arguments at every `content_safety.log_event` call site; then
  remove the compat `db` kwarg itself after a repo-wide search proves no external callers
  (keep it only if a real external/dynamic caller exists — evidence required, "tests use it"
  does not count per AGENTS.md).
- Validation: `grep` count → 0 (or only justified keepers); throttle tests green; `ruff` clean.

### N4 [P2] Dual provider key-resolution mechanisms, one dead — `openrouter_provider.py`, `groq_provider.py`
- Demonstrated: `OpenRouterProvider.__init__` takes `_api_key_env` **and** defines
  `_resolve_api_key`; `GroqProvider` passes `_api_key_env="GROQ_API_KEY"` **and** overrides
  `_resolve_api_key` — the `_api_key_env` branch never calls the hook, so Groq's override is
  dead code and the next editor must update two mechanisms.
- Fix: keep exactly one — the `_resolve_api_key` override point (delete the `_api_key_env`
  parameter; `GroqProvider.__init__` becomes `super().__init__(api_key=..., model=...)` + base
  URL line). No behavior change.
- Validation: existing Groq/OpenRouter tests + key matrix (Groq-only, OpenRouter-only, neither,
  padded keys) unchanged and green.

### N5 [P2] `emptyAuthState` omits `isLoading` — stuck spinner after logout-during-login — `src/frontend/src/store/authStore.ts:75-82`
- Demonstrated by code: `login` sets `isLoading: true`; `logout` does `set(emptyAuthState())`
  which has no `isLoading` key → a logout mid-login leaves `isLoading: true` forever; likewise
  D12's stale-skip path never resets `isLoading` when it discards a stale failure.
- Fix: include `isLoading: false` in `emptyAuthState`; in the D12 stale-skip branches, reset
  `isLoading` only when no newer operation owns it (i.e. skip the error but still clear a
  spinner that belongs to the discarded attempt — guard with the same epoch check semantics,
  never unconditionally).
- Validation: new `authStore.test.ts` cases — logout-during-login leaves `isLoading: false`;
  stale-failure-after-newer-login keeps `error: null` (covers N9's D12 half too).

### N6 [P2] Import result counts report inputs, not outcomes — `export_import.py::import_data`
- Demonstrated by code: `boards`/`symbols`/`learning_history` are `len()` of the payload lists,
  so an idempotent retry that merges everything and creates **0** rows still reports full counts.
- Fix: count actually created rows (boards created vs matched, placements added, sessions added)
  and report `{ok, boards_created, boards_merged, symbols_added, learning_history_added,
  truncated, total_learning_sessions}`. Keep old `boards`/`symbols`/`learning_history` keys as
  aliases only if the frontend needs them — otherwise replace and update `DataManagementTab`.
- Validation: retry-import test asserts `boards_created == 0` with `boards_merged == N` on
  second import; first import asserts created counts.

### N7 [P2] `assigned_by` accepts bools and is unvalidated — `export_import.py::_import_assigned_boards`, `_validate_import_payload`
- Demonstrated by code: `isinstance(True, int) and True > 0` is true, so
  `assigned_by: true` passes the guard and SQLite stores it as user-ID 1 (the admin) via the
  `Integer` FK column; `_validate_import_payload` never inspects `assigned_by` at all.
- Fix: reject bools explicitly (`type(x) is int`-style check matching the file's existing
  convention) and add `assigned_by` shape validation (int ≥ 1 or absent) to
  `_validate_import_payload`; unknown/non-positive assigners fall back to the importer.
- Validation: `assigned_by: true/"1"/-5` → importer fallback; valid existing user → preserved;
  invalid shape → 400.

### N8 [P3] Dead `except HTTPException: raise` in collab revalidation — `src/api/routers/collab.py:323`
- Demonstrated by code: the inner `require_board_view_access` 403/non-403 outcomes are fully
  handled inline (close 1008 / close 1011 + return), and nothing else in the `try` raises
  `HTTPException` — the outer `except HTTPException: raise` is unreachable.
- Fix: delete the dead handler (the generic `except Exception` transient path below already
  covers real DB failures with the 3-strike policy).
- Validation: collab WS tests + acceptance-gaps F05 tests green; no behavior change.

### N9 [P3] New branches without tests: D7 truncated toast, D12 stale-error guard
- Demonstrated: `grep truncat tests/DataManagementTab.test.tsx` → no hits (its i18n mock lacks
  `importTruncated` entirely); `grep stale tests/authStore.test.ts` → only checkAuth/refresh
  cases, nothing for login/setup failure staleness.
- Fix: add `DataManagementTab` test — import result with `truncated: true` shows the
  `importTruncated` warning toast with shown/total counts; add `authStore` tests per N5.
- Validation: new specs fail before (assert on untested branch), pass after.

### N10 [P3] D3's abort-after-response path has no regression test — `src/api/main.py`
- Demonstrated: no test exercises `resolve_overflow` when `response_started` is already true
  (the exact fail-open case D3 fixed).
- Fix: ASGI-level test with an abort-swallowing app that starts a 200 response before consuming
  the body on an oversized chunked upload — assert no clean 200 is delivered (connection
  aborted) plus the warning log; keep the existing declared-length/chunked 413 expectations.
- Validation: test fails on pre-D3 logic (mental or `git stash` check), passes now.

### N11 [P3] D5 comment block splits the password section — `src/config.py:177-186`
- Demonstrated: the `AAC_REFRESH_ALLOW_QUERY_FALLBACK` block (with its own comment) was inserted
  between `# Optional deterministic passwords are intentionally unset by default.` and the
  `AAC_SEED_*_PASSWORD` fields, orphaning that comment from its fields (duplicated header
  comment now appears twice).
- Fix: move the D5 setting + comment adjacent to related auth settings (near JWT/refresh
  configuration), leaving one passwords comment over the password fields.
- Validation: `compileall`, settings tests green; pure move.

### N12 [P3, deferred-cleanup] Micro-residues to sweep while touching the files
- `collab.py`: comments removed by D4 (lifespan fallback, revocation-mirror note) carried
  useful context — restore one-line versions; `REVALIDATE_MAX_FAILURES`/`REVALIDATE_INTERVAL`
  deserve module-level names for test configurability (acceptance tests currently monkeypatch
  the clock past a hardcoded 60s).
- `content_safety.py`: `call_count=max(1, int(call_count or 1))` raises `TypeError` on
  non-numeric input → event silently lost; coerce defensively (`try/except → 1`).
- `_prune_events` callers: document that direct calls bypass the D11 throttle (one-line comment
  at each direct call site or in the docstring — docstring already notes it; verify).
- Validation: `ruff`, `compileall`, affected named tests.

## 6. Simplification / deletion targets

- N4 (one hook, not two), N3 (dead kwargs), N8 (dead handler), N11 (comment repair).
- N6 may delete the aliased count keys if the frontend is updated in the same change.
- No new dependencies, frameworks, or config keys. No new abstractions.

## 7. Functional validation (real behavior)

- Import matrix end-to-end (API level): cyclic owned links, assigned↔assigned (existing),
  **owned→assigned and assigned→owned** (new), forged-external cleared, retry merge with
  created/merged counts, `assigned_by` edge shapes, 137-session truncation flags.
- Refresh: body works; query rejected by default in prod-mode test config; opt-in accepts +
  logs deprecation (assert log line, never the token).
- Redactor canary suite: D1's 8 shapes + `***`-containing secret + unquoted JSON numerics.
- Sentinel: multi-chunk text bills `spent` calls in one row; cap enforced for long texts.
- Collab: F05 acceptance cases still green after N8/N12 touch-ups.
- Auth store: N5 scenarios via the new specs.

## 8. Regression validation

- Named files only: `tests/test_export_link_remap.py`, `tests/test_content_safety.py`,
  `tests/test_collab_ws.py`, `tests/test_acceptance_gaps.py`, `tests/test_phase2_security.py`,
  `tests/test_password_reset_security.py`, plus frontend `authStore.test.ts` and
  `DataManagementTab.test.tsx`.
- `uv run ruff check src tests scripts`, `python -m compileall -q src scripts`,
  frontend `typecheck`/`lint` if TS touched, `git diff --check`.
- Each N-item needs fail-before/pass-after evidence (probe output or new test).

## 9. Cleanup after implementation

- Remove the residues in N3/N4/N8/N11/N12 rather than leaving old+new side by side.
- Delete the temporary probe files if you recreate them; keep only the committed regression tests.
- Stop any servers/runners started; confirm none remain.

## 10. Final bug hunt

Re-inspect every touched flow (import remap ordering, redactor pass interactions, provider
resolution, auth-store epoch/isLoading interplay, prune throttle accounting) for regressions,
stale callers, newly dead code, and fresh simplification wins.

## 11. Definition of done

- All 12 N-items fixed or blocked with demonstrated evidence; net complexity down.
- §4 re-verified post-change; targeted validations fail-before/pass-after where practical.
- Named regression tests + lint/compile gates green; `git diff --check` clean.
- SHORT final report: per item, files changed + validation evidence.
