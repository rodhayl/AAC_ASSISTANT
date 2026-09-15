# PROMPT_4 — Full production sweep: backend correctness, frontend session integrity, config/CI/packaging parity, lifecycle and hardening

## 1. Mission

Three hardening passes are behind us (`133d790` F01–F16 → `bb0c4a0` D1–D13 → `1e1caa7` N/Q
backlogs, rationales in `PROD-FIXES.md`). Each pass was independently re-verified and is
genuinely in the tree. This iteration is different: it is the first **whole-product production
sweep**, built from six parallel read-only audits (backend routers/services, frontend
stores/flows, config/CI/packaging/docs, uncovered routers/deps/schemas, services/lifespan,
frontend depth) whose load-bearing claims were re-checked against the code. The backlog below
is 40 concrete defects in seven tiers — no discovery tasks, no vague hardening. Fix them all,
with fail-before/pass-after evidence for each. This is a large backlog by design: work it
tier by tier (A→G), keep every gate green as you go, and do not leave parallel old/new
implementations standing. Net complexity must go down. Finish with a SHORT report (per item:
files changed + validation evidence).

## 2. Repository context

- AAC Assistant: FastAPI backend (`src/api`, `src/aac_app`, `src/config.py`) + React frontend
  (`src/frontend/src`) + SQLite (Postgres-compatible aspirations — several items below are
  SQLite-masked). Groq is the production LLM provider; explicit-model rule in `generate()`.
- Baseline: branch `fix/pagination-n1-e2e` at `1e1caa7` **plus 5 uncommitted files** that are
  part of the working baseline, not your work: `PROD-FIXES.md`, `src/api/logging_config.py`
  (R1 exception redaction), `src/frontend/src/store/authStore.ts` (pending-op spinner),
  `src/frontend/tests/authStore.test.ts`, `tests/test_logging_config.py`. **Commit these 5
  files first** (review, test, commit), then implement the backlog on top.
- Architectural constraints (AGENTS.md): no `.env`/DB/auth-artifact mutation (temp dirs +
  synthetic creds); named test files only; offline queue fail-closed; strict moderation
  fail-closed; `log_event` isolated from caller transactions; `git diff --check` clean; stop
  all runners. `LocalSpeechProvider.transcribe` alias is already deleted (verified safe —
  sole remaining `.transcribe(` is faster-whisper's own model method); do not resurrect it.

## 3. Starting procedure

1. `git status --short`, `git log --oneline -2`, `git diff --cached --stat` (expect empty).
2. Run the baseline gates once and record results: `uv run ruff check src tests scripts`,
   `python -m compileall -q src scripts`, `git diff --check`, plus
   `pytest tests/test_logging_config.py` and frontend `authStore.test.ts` (covers uncommitted R1/spinner).
3. For every item below, reproduce first (probe or failing test on current code), then fix.

## 4. Previous-iteration verification (re-checked — re-verify after your changes)

| Claim | Verdict | Basis |
|---|---|---|
| Q1–Q11 in `1e1caa7` | VERIFIED (spot) | `refresh_query_fallback_allowed()` single rule in `config.py:461`; `REQUEST_RECEIVE_INACTIVITY_TIMEOUT_SECONDS = 25.0` in `main.py:373`; public `resolve_groq_api_key()`; raw import deltas; `is\|es` copula + scope note |
| R1 exception redaction (uncommitted) | VERIFIED | `_redact_exception` + patcher `_replace`; 20/20 logging tests green |
| Spinner pending-count refinement (uncommitted) | VERIFIED | `pendingLoadingOps` + `finally` + reset in `clearSession`; 25/25 authStore specs green |
| HEAD extras: `GROQ_MODEL` setting + `resolve_groq_model()` DB>config>env | VERIFIED | `config.py:156`, `deps/providers.py:408-424`, `.env.example:36` |
| HEAD extras: `transcribe` alias deletion | VERIFIED SAFE | repo-wide search: only faster-whisper internal use remains |
| HEAD extras: CI prod bootstrap password | PRESENT, LIVE-RUN OPEN | `ci.yml:106,109` uses non-default credential; gate never executed here |
| Prior report's "168 tests / 8 files" style counts | ACCEPTED AS REGRESSION SIGNAL ONLY | re-ran: 193 backend / 10 files green; gates above green |

## 5. Audited defect backlog

### Tier A — data loss / auth integrity / spend (do first)

**A1 [P1] Import-history bounds exceed DB columns; `DataError` escapes → whole-import 500.**
`src/api/routers/export_import.py` accepts `topic_name`/`topic` ≤ 200 and `status` ≤ 50
(`_validate_import_payload`), but `LearningSession.topic_name` is `String(100)` and `status`
is `String(20)` (`models/learning.py:50,62`). `_import_learning_history`'s `except`
(line ~741) catches only `(AttributeError, TypeError, ValueError, OverflowError)` — not
`DataError`. A signed export with a 101–200-char legacy topic commits fine on SQLite (which
over-stores silently, so tests never see it) but raises `DataError` at flush/commit on
Postgres, aborting the single atomic `db.commit()` and rolling back the **entire** recovery
import as an unhandled 500. Fix: tighten bounds to column widths (`topic_name`/`topic` ≤ 100,
`status` ≤ 20); add a test with over-width values asserting 400, not 500.

**A2 [P1] 401 refresh-and-retry never strips the expired token.**
`src/frontend/src/lib/api.ts`: the retry path does `delete retryConfig.headers.Authorization`
after a successful silent refresh. But the request interceptor normalizes headers to an
`AxiosHeaders` instance (`AxiosHeaders.from(...)`), where `delete obj.Prop` does not clear the
internal store — `headers.has('Authorization')` stays true, the interceptor skips attaching the
fresh token, the retry re-sends the expired token → second 401 → forced logout. Users with a
valid refresh token get bounced to `/login`. Fix: delete/set via the `AxiosHeaders` API (or
rebuild headers) and explicitly attach the fresh token on retry. Validation: spec with
`AxiosHeaders`-shaped `error.config.headers` asserting the retried request bears the new token.

**A3 [P1] Offline replay success path can corrupt the next session's queue.**
`src/frontend/src/lib/api.ts::flushQueue`: the error branch guards publishes with
`generation === replayGeneration`, but the success branch does unconditional
`queue.shift(); persistQueue()`. `clearSessionMutations` (logout) empties the queue and bumps
the generation — yet an already-awaited replay landing in the success branch shifts/persists
whatever is now at `queue[0]`, i.e. the **new session's** item (its own comment claims the old
flush "cannot mutate the new session's queue" — false on this path). Fix: guard the success
publish with the same generation/owner check. Validation: deferred-success-after-logout spec
asserting the new session's queue is untouched.

**A4 [P1] LLM-cost endpoints have no rate limit while auth routes do.**
Repo-wide, `conditional_limiter` is used only in `auth.py` (4 sites) and `auth_users.py` (1
site); `limiter.py` sets no defaults. Unlimited: `learning.py::ask_question/submit_answer/
submit_voice_answer/submit_symbol_answer`, `board_ai.py::generate_ai_suggestions`,
`analytics.py::get_next_symbol_suggestions_post` (LLM topic-word fetcher),
`providers.py::tts_synthesize/warmup_models`. Any authenticated user can burn unbounded
provider spend/CPU. Fix: add `conditional_limiter` (or equivalent per-route limits, consistent
with the auth-route pattern) to every LLM-invoking endpoint. Validation: burst test per
endpoint class asserting 429; legit single calls unaffected.

**A5 [P1] `ask_question` difficulty is unvalidated and interpolated into the LLM prompt.**
`src/api/routers/learning.py:459`: `difficulty: str | None = None` with no validation; the
service only handles `None`, any other string is interpolated verbatim into the generation
prompt and persisted on session history, later re-served — while session-start uses
`Literal["basic","intermediate","advanced"]` (`schemas.py:559-567`). This is a prompt-injection
surface plus unvalidated persisted data. Fix: allow-list against the same `DifficultyBand` at
the router, 400/422 otherwise; test with `?difficulty=<injection string>` and each valid band.

**A6 [P2] Manual conflict retry bypasses replay protection and fails silently.**
`OfflineConflictsPanel.tsx::handleRetry` calls `api.request(conflict.config)` **without** the
`[OFFLINE_REPLAY]` flag that auto-replay sets, so an expired-token 401 triggers global logout
+ `/login` redirect instead of a visible conflict; failures only `console.error`, never update
the conflict's error text (retry count was already bumped). Fix: send manual retries with the
replay marker + ownership check; surface failures via toast/conflict-error update. Validation:
expired-token retry stays in place with an error message; no logout.

**A7 [P2] Token-refresh reconnect drops queued collab moves.**
`useBoardCollab.ts` effect deps `[boardId, token]` (line 60) tear down the socket on every
token rotation, and `ws.ts::close()` does `queue.length = 0` — while `send()` queues moves
made while not OPEN. Drag moves made during the refresh window are silently lost to
collaborators. Fix: preserve the send queue across token-driven reconnects, or skip reconnect
when only the credential rotated. Validation: queue-then-rotate spec asserting queued moves
flush on the new socket.

### Tier B — backend performance / error semantics

**A8 [P2] Service catch-alls converted to 400s mask server failures.**
`learning/session.py` (`start_learning_session`, `get_topic_pool`, `get_session_progress`,
`get_user_history`) return `{"success": False}` on any `except Exception`; routers map that to
400 (404 only for progress, never 500). A DB outage during `get_topic_pool` presents as a
client error — clients won't retry, monitoring misses 500-class outages. Fix: distinguish
domain failures (validation → 400, safety → 403) from unexpected exceptions (propagate to
500). Validation: simulated DB failure asserts 500; validation failures still 400.

**A9 [P2] Sentinel day boundary uses local midnight vs DB-clock timestamps.**
`created_at` defaults to `func.now()` (DB clock; UTC on SQLite) but `_today_start()`
(`content_safety.py:618`) and `clear_safety_events` (`routers/content_safety.py:89`) use naive
`datetime.now()` server-local midnight. On non-UTC hosts the daily-spend meter and the
"preserve today's sentinel rows" guarantee drift by the UTC offset near midnight (cap
under/over-count; prune or admin-clear can delete same-day sentinel rows). Fix: UTC day
boundary everywhere the meter is compared. Validation: TZ-pinned test (e.g. UTC+14/UTC-12
around midnight) asserting meter + preservation use the same boundary as stored timestamps.

**A10 [P2] `batch_update_board_symbols` issues up to 1000 sequential SELECTs in an open write tx.**
`src/api/routers/symbols.py` (~741-782): `Body(max_length=1000)` caps the batch but each entry
does its own `query(BoardSymbol).filter(board_id, id).first()` while holding SQLite's single
write lock. Fix: one `id.in_(…)` fetch into a dict, then apply. Validation: statement-counted
test (event listener) asserting O(1) SELECTs for a large batch; behavior unchanged.

**A11 [P2] `get_history` loads 1000 full rows incl. `conversation_history` JSON.**
`learning.py::get_history` (`le=1000`) → `get_user_history` selects whole `LearningSession`
entities (up to 50 history entries each) while serializing only scalars. Fix:
`defer(LearningSession.conversation_history)` (or column-only query) + lower the route cap.
Validation: statement/payload-size test; deep-page response shrinks, fields intact.

**A12 [P2] `export_data` N+1 on achievements.**
`export_import.py` (~816-835): `UserAchievement` rows loaded without eager loading, then
`ua.achievement` per row — while the boards queries directly above use `selectinload`. Fix:
`.options(selectinload(UserAchievement.achievement))`. Validation: statement count constant in
achievement count; export bytes identical.

**A13 [P2] `AISuggestionsRequest.refine_prompt` unbounded into the LLM prompt.**
`schemas.py` (~520-523): `refine_prompt: str | None` with no `max_length`, interpolated into
the generation prompt and safety probe — siblings are bounded (`answer` 10k, `topic` 200).
Fix: `Field(None, max_length=…)` consistent with prompt-fed fields (2000–10000). Validation:
over-long value → 422; boundary value passes.

**A14 [P2] `_import_achievements` stores `null()` instead of `None`.**
`export_import.py` (~672-679): `earned_at=… if … else null()` puts a SQL element on an ORM
attribute; `bool(null())` raises `TypeError`, so any same-session truthiness check (the exact
pattern `export_data` uses: `ua.earned_at.isoformat() if ua.earned_at else None`) would raise;
the sibling history importer correctly uses `None`. Latent (row persists as NULL, re-reads as
None) but fragile/non-portable. Fix: pass `None`. Validation: attribute usable in-session
immediately after import; round-trip identical.

### Tier C — frontend session/UX integrity

**A15 [P2] First offline flush runs before the rehydrated session is validated.**
`onRehydrateStorage` fires unconditional `aac:auth-ready` → `resumeOfflineQueue()` flushes on a
persisted `user.id` without awaiting `checkAuth()`/refresh. Reload with an expired access token
replays with the dead token and each 401 becomes a manual conflict instead of being saved by a
refresh. Fix: gate the initial post-rehydrate flush on a validated/refreshed token. Validation:
expired-token reload spec — queue preserved, no conflicts minted, flush follows refresh.

**A16 [P2] Forced-logout redirect can outrun local session clearing.**
`authStore.ts::logout` only `set(emptyAuthState())` after awaiting `/auth/logout`, and the 401
handler navigates to `/login` without awaiting logout — persisted `auth-storage` still holds the
old token at navigation time, so the login page can briefly rehydrate stale auth. Fix: clear
persisted auth state synchronously before best-effort revocation; await logout before
navigating. Validation: post-logout storage/rehydration spec asserting no stale session flash.

**A17 [P2] Remote collab moves have no dirty-state identity.**
`useBoardEditorSymbols.ts::handleRemoteMove` writes only the local override map, never
`hasChanges`; `BoardEditor::handleSave` serializes merged symbols. Remote positions are either
lost (save disabled) or silently persisted as the local user's change. Fix: track remote vs
local dirt separately (or apply remote moves via refresh) + remote-presence indication.
Validation: remote-move-only session keeps save disabled yet displays positions; local edits
after remote moves persist both correctly.

**A18 [P2] Settings store: one sequence + one spinner for four providers; update leans on refetch.**
`settingsStore.ts`: single `modelRequestSequence`/`loading` shared by all providers and
settings loads — a second fetch invalidates the first (list stays `[]`, no error) and rapid
autosave PUTs (500ms debounce, no cancellation) can land out of order; `updateAISettings`
relies on inner `fetchAISettings()` to clear `loading`, which may early-return leaving it
stuck. Fix: per-endpoint request ids/loading flags; settled-state handling with post-refetch
staleness check; serialize/cancel overlapping autosaves. Validation: overlapping-fetch and
rapid-edit specs.

**A19 [P2] Truncated-import toast can render a missing "shown" count.**
`DataManagementTab.tsx::handleImportData` guards only `total` before interpolating
`{{shown}}`, but `added = body.learning_history_added ?? body.learning_history` may be
`undefined` on older payloads (Q1 wired `total` only). Fix: require both counts numeric for
the truncated template, else plain success. Validation: missing-`shown` payload spec.

### Tier D — config / CI / packaging / docs parity

**A20 [P2] Example/docs parity gaps for operator-visible settings.**
Measured: 43 Settings fields; `.env.example` missing 12, `env.properties.example` missing 24.
Concretely add: `AAC_REFRESH_ALLOW_QUERY_FALLBACK=false` + deprecation note (in code+docs,
absent from both examples — old clients fail `400` with no discoverable opt-in);
`AUTOGEN_DAILY_CAP/_PACING/_COOLDOWN`, `SENTINEL_DAILY_CAP/_PACING`, `SUPPORTED_UI_LANGUAGES`;
`GROQ_MODEL` (+precedence/fail-closed row) also to README config table and
`docs/01_PROJECT_GUIDE.md`; `AAC_ASSISTANT_NO_BROWSER`/`AAC_ASSISTANT_PORTABLE` behavior flags;
either sync the legacy `env.properties.example` (incl. `GROQ_MODEL`) or delete it pointing at
`.env.example`. Validation: script-level check — every Settings field greppable in at least one
example + user-facing keys in README table.

**A21 [P2] Production gate provisions `Student123`/`Teacher123` in `ENVIRONMENT=production`.**
`ci.yml:111/113` + `auth.setup.ts:19,27` create API-provisioned users with predictable
passwords under `ENVIRONMENT: production`, while `SECURITY_ARCHITECTURE.md:44-47` forbids
default passwords outside explicit test envs (the create-user path enforces only strength, so
nothing stops it). Fix: synthetic strong `E2E_*_PASSWORD`s in `e2e-production-gate`, or an
explicit documented CI exception. Validation: workflow inspection + password-policy unit check
against the new values.

**A22 [P3] `TESTING` vs `ENVIRONMENT=test` parity changes limiter behavior between jobs.**
`backend` sets both; `packaging-windows` sets only `ENVIRONMENT: test`, and
`auth_helpers.py:111` bypasses limits solely on `TESTING==1` — backend tests run unthrottled,
packaging smoke throttled. Fix: set `TESTING` (or document absence) per job intent.
Validation: per-job env matrix documented; limiter active/inactive as intended in each.

**A23 [P3] `start.bat` lacks the Python 3.13 pin `start.sh` enforces.**
`start.sh:14,67,76` pins `uv sync --python 3.13` + fallback guard; `start.bat:44` is bare `uv
sync`. `pyproject.toml:36` restricts `kokoro-onnx` to `<3.14`, so a 3.14-resolving Windows
checkout silently drops neural TTS. Fix: pin + guard in `start.bat`. Validation: script
inspection; Windows CI step if available.

**A24 [P3] Production `pip-audit` misses the voice stack.**
`requirements.txt` header shows export without extras (`faster-whisper`/`kokoro` absent) while
`ci.yml:50` audits production via that file. Fix: export production requirements with the
shipped extras or audit them explicitly in the production step. Validation: audit step covers
the voice packages (dry-run listing).

**A25 [P3] `SECURITY_ARCHITECTURE.md` overstates JWT-secret handling.**
"Placeholder or empty value is never used" vs `config.py:120` default `""` + early return
outside production. Fix: scope the sentence to production/first-run generation. Validation:
doc/code agreement on re-read.

### Tier E — authZ / input-bound hardening on uncovered routers (all verified by code read)

**E1 [P1] Any student can create global symbols via ARASAAC import.**
`src/api/routers/arasaac.py:91 ::import_arasaac_symbol` uses `Depends(get_current_active_user)`
then creates shared `Symbol` rows, writes PNGs to `UPLOADS_DIR/symbols`, and triggers
`index_symbol` — while the neighboring `symbols.py:328,361,409` create/reorder/upload endpoints
all require `get_current_staff_user`. A student pollutes the shared catalog with unbounded
disk/vector-store growth. Fix: require `get_current_staff_user` for `POST /api/arasaac/import`.
Validation: student token → 403 + no row/file; staff → 200 as before.

**E2 [P2] Unbounded achievement and roster lists.**
`achievements.py::list_all_achievements` (role check present, but `.all()` with no skip/limit)
and `guardian_profiles.py::list_students_with_profiles` (no Query params; service
`guardian_profile_service.py:415` `query.all()` with join) grow linearly — neighbors
(`get_leaderboard` le=100, `users.py`, `auth_users.py`, `notifications.py`) all cap. Fix: add
capped `skip/limit` to both endpoints + service query. Validation: over-limit seed asserts
paged sizes and stable ordering.

**E3 [P2] `SymbolUsageRequest.symbols` unbounded → N inserts per request.**
`schemas.py:738` declares a bare `list[SymbolUsageItem]`; `analytics.py:140` passes through;
`symbol_analytics.py:161-184` inserts one `SymbolUsageLog` per item — while sibling
`SymbolAnswerSubmit.symbols` caps at 100. Fix: `Field(max_length=100)` (or the batch size the
route documents). Validation: 101-item payload → 422; 100 → 200.

**E4 [P2] Prompt-fed schema strings bypass the bounds their persisted twins enforce.**
`GuardianProfileCreate/Update.template_name` (plain `str`, column `String(100)`,
`models/guardian.py:16`; create path catches only `IntegrityError`, not `DataError`) —
same Postgres-500 class as A1; `LearningModePreviewRequest` fields (`mode_key`,
`prompt_instruction`, `student_id`, `sample_question`, `topic`) flow into
`preview_system_prompt`/`build_conversation_user_prompt` (`learning_modes.py:98-117`) while the
persisted equivalents cap at 50/10_000/100; `GuardianProfileFields.custom_instructions` +
persona/style/forbidden/trigger strings/lists interpolate directly into the system prompt
(`template_manager.py:250-325`) with no lengths/counts; `preview_template(overrides: dict|None)`
(`guardian_profiles.py:171`) deep-merges arbitrary nesting via `_apply_dot_overrides`
(`template_manager.py:209-226`). Fix: mirror column/persisted bounds onto every preview/guardian
prompt-fed field (`template_name` ≤ 100, preview fields = create/start caps,
`custom_instructions` ≤ 10_000 + nested/list caps, `overrides` size/depth/key validation
against the strict profile schema). Validation: over-bound/oversized-nesting payloads → 422;
boundary values pass; prompt content identical for in-bounds inputs.

**E5 [P3] `TTSSynthesizeRequest.lang` unbounded; unlock `username` unbounded; warmup `targets` unvalidated.**
`providers.py:248` `lang` has no min/max while every sibling language field caps at 10
(`schemas.py:8,393,478`) — oversized strings flow into engine args/logs. `auth_users.py:866`
`admin_unlock_account(username: str)` is a bare query param (no length cap) while every other
username input caps at 50 (`schemas.py:14,111,172`) — MB-long strings into WHERE/audit paths.
`providers.py:320,332` `WarmupRequest.targets` is an unbounded `list[str]` that silently ignores
unknown values (`targets=["typo"]` → `{}` 200). Fix: `lang` min 2/max 10;
`username = Query(..., min_length=1, max_length=50)`; validate `targets` against
`{"tts","speech","vector"}` with 400 on unknown + list-length cap. Validation: boundary tests
for all three.

**E6 [P3] Admin assignment view can't distinguish empty from missing.**
`board_assignments.py:21 ::get_assigned_boards`: teacher path 404s on missing/inactive student
via `verify_student_access`, admin path skips the existence check and returns `[]` 200 for a
nonexistent `student_id` (contrast `guardian_profiles.py:230`, 404 for all roles). Fix: student
existence lookup on the admin path, 404 like the teacher path. Validation: admin + bogus id →
404; admin + real-but-unassigned id → 200 `[]`.

### Tier F — services, migrations, lifecycle (all verified by code read)

**F1 [P1] Non-SQLite additive migrations have no upgrade path.**
`schema.py::ensure()` relies on `create_tables()` (missing tables only) plus additive helpers,
but `_ensure_sqlite_columns`, `_ensure_sqlite_indexes`, `_ensure_foreign_key_actions` all
early-return for non-SQLite (`schema.py:19-20,127-128,324-325`); only one `tts_voice` widen has
a Postgres branch — while `db.py:36-38` accepts any `DATABASE_URL`. A Postgres deployment
upgrading from an older release misses every additive column/index/FK fix and fails at runtime.
Fix: apply the additive migrations in a dialect-portable helper instead of SQLite-only ones.
Validation: fresh-DB and legacy-DB (pre-column) fixtures on SQLite behave identically before/
after; Postgres DDL path reviewed (or live-checked if available).

**F2 [P1] Warmup installs Groq credentials from different sources than the getter.**
`deps/providers.py`: `get_groq_provider()` uses stripped `resolve_groq_api_key()`/
`resolve_groq_model()` (DB > config > env), but `_init_llm_provider_sync()` (~782-791) passes
raw DB-only `_get_setting_value("groq_api_key", "")` (unstripped, no config/env fallback) into
the installed singleton. With an env-only or padded key, warmup installs an empty-key instance
the first request discards and rebuilds — httpx client churn on every cold start. Fix:
construct the warmup instance from the same `resolve_*` helpers. Validation: env-only-key test
asserts warmup-installed provider `is_configured()` and singleton identity is preserved by the
first getter call.

**F3 [P2] N-gram rebuild worker races shutdown; image-download tasks outlive lifespan.**
`ngram_builder.py::run_periodic_ngram_rebuild` loops `await asyncio.to_thread(rebuild_fn, …)`
with no shutdown-event check — lifespan cancels the wrapper but the sync worker keeps mutating
n-gram files and popping `prediction_service._models` while shutdown only handshakes with the
*index* worker (`main.py:325-332`) before `reset_providers_async()`. Separately,
`symbol_image_backfill.py::_scheduled_tasks` keeps download tasks the shutdown path never
cancels/awaits (cancellation list `main.py:274-284` has no entry) — shutdown can return while
downloads hold DB sessions, httpx clients, and partial files. Fix: same
`shutdown_started`/`finished` handshake + budget wait for the n-gram worker; track
scheduled-download tasks in app state and cancel/await them in the shutdown budget.
Validation: shutdown-with-active-rebuild/download test asserting clean drain within budget and
no use-after-close.

**F4 [P2] Unbounded catalog scans on miss paths.**
`symbol_catalog.py::find_symbol_by_normalized_label` falls back to iterating the full
`Symbol.id/label` table with no `yield_per`/limit for the Python casefold comparison (every
genuinely new label materializes ~17k rows in-request); `vector_utils.py::_index_all_symbols`
repair mode builds the whole `{id: text}` dict and an unbounded `NOT IN` bind list;
`ngram_builder.py::collect_usage_bigrams` streams with `yield_per(1000)` but calls
`_resolve_log_language()` per log (1 + up to 2 queries each) inside one long transaction.
Fix: `yield_per()` + row cap (or reuse the bounded `unicode_recall_ids` helper); page the
repair snapshot and batch orphan deletes; preload one `id → language` map per rebuild.
Validation: statement-counted tests asserting bounded queries on large fixtures; identical
results.

**F5 [P2] Default learning-mode seed never completes a partial set.**
`seed.py::_create_default_learning_modes` returns early when *any* system
(`created_by IS NULL`) mode row exists, without checking all four
`DEFAULT_LEARNING_MODES` keys are present — a subset-seeded DB misses modes forever and
sessions referencing the absent `mode_key` fail validation. Fix: upsert per `key`.
Validation: partial-seed fixture gains exactly the missing modes; full-seed path unchanged
(no duplicates on rerun).

**F6 [P2] Vector-store getter raises transient 500 across a reset.**
`deps/providers.py::get_vector_store` (~649-656) raises `RuntimeError("Cannot create a
replacement…")` when a reset queued deferred cleanup in the lock gap, instead of waiting for
the deferred event and retrying. A search racing a settings-change reset fails 500. Fix:
release locks, wait for the deferred event, retry construction. Validation: racing
reset-during-search test asserts success (or bounded wait), never the `RuntimeError`.

**F7 [P3] CORS credentialed wildcard + warmup executor abandonment (bounded verification).**
`main.py` sets `allow_credentials=True` with `allow_methods/headers=["*"]` (origin handling
itself is correct) — some stacks reject literal `*` on credentialed preflights; and
`warmup_providers()` uses `shutdown(wait=False, cancel_futures=True)`, abandoning running
initializers past the 30s budget with unverified lock/exit interactions. Fix: enumerate the
explicit methods/headers the API uses; run warmup initializers with explicit timeouts, never
holding provider/vector locks across blocking loads. Validation: preflight test with
credentials; warmup-timeout test asserting no lock is held past budget. Treat as
verify-first: if the pinned Starlette/Python semantics prove the current shape safe, document
the finding as disproved instead of changing code.

### Tier G — frontend hardening: bounds, feedback, resilience (all verified by code read)

**G1 [P2] Unbounded client-side growth in five stores/queues.**
`tts.ts::TTSQueue.lastSpokenAt` (set on every `enqueue`, never evicted);
`useBoardEditorSymbols.ts` per-`${userId}:${boardId}` context maps (only current key ever
deleted); `learningStore.ts::messages` (appends every turn; only `providerHistory` is
`.slice(-10)`-capped); `notificationsStore.ts::add` (unconditional prepend; SSE feeds it for
the session lifetime + full-backlog `walkPages` fetch); `offlineStore.ts::addConflict` (dedupes
only exact request keys, persists everything to localStorage); `SymbolSearchModal.tsx`
(`SEARCH_PAGE_SIZE = 1000` walkPages accumulated then fully rendered as tiles). Fix: LRU/time
caps on the TTS map; evict non-current editor contexts; window `messages` (last N, history from
backend); cap notification items (newest N); cap stored conflicts (newest N);
page/virtualize symbol-search results. Validation: growth tests per store (N+1 inserts →
bounded length/persisted bytes); modal renders paged results.

**G2 [P2] Smartbar auto-refresh dies after the first batch; prediction/search failures silent.**
`Smartbar.tsx`: `autoRefreshCountRef` increments per poll but is never reset on a new
`is_generating` batch, so later generations stick on spinner tiles; `fetchSuggestions` catch
only `console.error`s (no error state — indistinguishable from empty vocabulary).
`SymbolSearchModal.tsx::handleSearch` catch only `console.error`s + clears results, and the
`noResults` hint requires truthy `query`, so category-search failures render blank. Fix: reset
the counter on each fresh pending-generation batch; error state/toast on non-cancelled
prediction failures; inline error + retry for search failures. Validation: second-batch
auto-upgrade spec; failure specs asserting visible feedback (not just empty UI).

**G3 [P2] No error boundary on auth/recovery shell routes.**
`App.tsx`: every protected page is wrapped, but `RootLayout` shell (`SettingsManager`,
`AppToaster`, `Outlet`), `/login`, `/register`, `/setup`, and `*` are not — a render crash
there unmounts the whole router with no fallback. Fix: wrap shell outlet + auth/setup/NotFound
routes in `ErrorBoundary`. Validation: crash-injection specs per route asserting fallback UI.

**G4 [P2] Board clear is N sequential deletes with stale UI on partial failure.**
`BoardEditor.tsx::clearBoard` loops `await deleteBoardSymbol` per symbol; `catch` toasts but
never refetches — partial deletes leave a stale grid. Fix: batch clear endpoint (preferred) or
bounded-parallel deletes + refetch/sync on success AND partial failure. Validation: partial-
failure spec asserting UI matches server state afterwards.

**G5 [P3] Icon-only voice/fullscreen toggles lack accessible names.**
`CommunicationChat.tsx:171-180` voice toggle and `Communication.tsx:544-550,876-882`
fullscreen buttons expose `title` but no `aria-label`/`aria-pressed`, unlike neighboring
controls. Fix: add both (pressed state for the toggle). Validation: axe/role queries naming
the controls and reflecting toggle state.

### Deferred (verified, lower severity — take only after Tiers A–G)

**D-a.** `update_board` unknown-field guard checks the schema's own fields, so it can never
fire; allow-list against real `CommunicationBoard` columns (`boards.py`, `schemas.py`).
**D-b.** `delete_board` orphans `SavedTopic.board_id` (plain Integer, no FK): null it in the
same transaction or add FK `SET NULL` (`boards.py`, `models/learning.py:32`).
**D-c.** Symbol-picker/board-roster load failures only `console.error` (silent truncation
appearance); surface in UI and assert walk page-size vs server caps (`SymbolPicker.tsx`,
`Boards.tsx`, `lib/pagination.ts`).
**D-d.** `BoardEditor` hasMore/delete-reset paging quirks (extra boundary fetch; delete drops
pages 2+): derive `hasMore` from totals/one-ahead probe, preserve paging across deletes.
**D-e.** Settings model-list single sequence/spinner already covered by A18; if A18 lands
cleanly, close this.
**D-f.** `preview_template`/`ask_question` prompt-injection hardening is covered by E4/A5; keep
this line only as a re-verification checkpoint, not new work.

## 6. Simplification / deletion work

- A10/A11/A12: fewer queries, same bytes — delete per-row loops, no new helpers beyond a dict.
- A8: replace catch-all→400 mappings with a small status-mapping helper shared by learning
  routes; delete the repeated shapes.
- A18: one request-id mechanism parameterized per endpoint, not new stores.
- A20: if the legacy template can't be synced, delete it (one template, not two).
- No new dependencies, providers, middleware, or config keys (A4 reuses `conditional_limiter`).

## 7. Functional validation

- Import round-trips incl. over-width rejection (400), outcome counts, truncation toasts with
  both/new/old payload shapes, Postgres-equivalent strictness where feasible (SQLite masks
  widths — assert at validation layer); partial-mode seed completion; dialect-portable
  migration fixtures.
- Auth marathon: body refresh, opt-in query + deprecation log without token, silent-retry with
  `AxiosHeaders`, logout ordering with storage inspection, rehydrate-with-expired-token flow;
  student ARASAAC import → 403.
- Collab: queued moves survive refresh reconnect; remote dirt behaves per A17.
- Spend: 429s on LLM endpoints under burst; single calls unaffected; `refine_prompt`/
  `difficulty`/guardian/preview boundaries; warmup installs env-key singleton without churn.
- Export/history/board endpoints: statement counts flat in achieven/assignment/history volume;
  history pages light; paged achievement/roster lists stable.
- Shutdown: active n-gram rebuild + scheduled downloads drain within budget, no use-after-close.
- Frontend: bounded stores under flood (memory + localStorage), Smartbar second-batch upgrade,
  visible failure feedback, error boundaries on shell/auth routes, named voice/fullscreen
  controls, batch clear consistency.
- Config: settings-matrix check (every field documented); CI gate inspection for passwords,
  TESTING parity, audit coverage.

## 8. Regression validation

- Named files only (backend): current `tests/test_*.py` files covering each touched area
  (acceptance gaps, content safety, logging, groq provider, new features, phase2, collab,
  export remap, password reset, startup warmup) + new targeted tests per item (endpoint
  allow-list/422s, statement counters, TZ-pinned meter, shutdown drain, warmup singleton,
  seed upsert, migration fixtures); frontend specs for touched stores/components (`authStore`,
  `api`, `offlineStore`, `notificationsStore`, `learningStore`, `tts`, `DataManagementTab`,
  `Smartbar`, `SymbolSearchModal`, board/collab/settings suites as affected).
- `uv run ruff check src tests scripts`, `python -m compileall -q src scripts`, frontend
  `typecheck`/`lint`/`npm run build` if TS touched, `git diff --check`.
- Every item needs fail-before/pass-after evidence (probe output or pre-fix-failing test).

## 9. Cleanup after implementation

- Commit the 5 baseline files separately from new work (two commits: baseline, then backlog).
- Remove superseded limiters/comments/aliases, dead branches exposed by refactors, diagnostic
  scripts. Stop all runners/servers; confirm none remain.

## 10. Final bug hunt

Re-inspect every touched flow for regressions, stale callers, newly dead code, and
simplifications (especially: interceptor header shapes after A2, queue ownership after
A3/A6/A15/A16, prompt construction after A5/A13, count/transaction semantics after A1/A10–A14,
example/doc parity after A20–A25).

## 11. Definition of done

- All Tier A–G items fixed or blocked with demonstrated evidence; Deferred triaged explicitly.
- §4 re-verified post-change; targeted validations fail-before/pass-after where practical.
- Named regression tests + lint/compile/build gates green; `git diff --check` clean.
- SHORT final report: per item, files changed + validation evidence. External gates (Windows
  rehearsal, human review, live CI/Groq runs) stay explicitly open unless actually executed.
