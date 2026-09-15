# PROMPT_5 — DRAFT (PROMPT_4 execution in flight; §4 verdicts to be filled in refinement)

> **Draft status — read first.** When this prompt was written, the PROMPT_4 implementation agent
> was still executing (branch `fix/pagination-n1-e2e`, baseline `1e1caa7` + 5 uncommitted files;
> by draft time its working tree had grown to ~24 modified files plus new sweep tests — i.e.
> execution is live and line numbers below may have drifted; rely on file + symbol names, not
> line numbers). §4 is therefore a **verification shell**: statuses are marked `PENDING — verify
> in tree`, and the refinement pass will fill actual verdicts from the PROMPT_4 agent's report. §5 is the
> **fresh, fully-verified backlog** from areas PROMPT_4 never covers (file handling, auth depth,
> uncovered routers/schemas, services/lifespan remainder, frontend depth, e2e, operator
> tooling, test infra) — every item was checked against the code with exact locations. If any
> §5 item is already fixed in the tree you receive, verify it is genuinely fixed (behavior +
> test) and mark it done with evidence; do not re-implement landed work.

## 1. Mission

Prior passes hardened the core (F/D/N/Q backlogs, Tiers A–G per `PROD-FIXES.md`). This iteration
closes the **remaining surface**: upload/file integrity, account-lifecycle auth gaps, refresh
token rotation, unvalidated schema fields on uncovered routers, service/lifespan races,
frontend depth (forms, e2e integrity, feedback), operator tooling safety, and test-fidelity
gaps. 66 concrete defects in Tiers H–R, no discovery tasks. Fix them all with fail-before/
evidence. Net complexity must go down. Finish with a SHORT report (per item: files changed +
validation evidence).

## 2. Repository context

- AAC Assistant: FastAPI backend (`src/api`, `src/aac_app`, `src/config.py`) + React frontend
  (`src/frontend/src`) + SQLite (Postgres aspirations — SQLite silently over-stores over-width
  strings, so width bugs must be asserted at the validation layer). Groq is the production LLM
  provider; explicit-model rule in `generate()`.
- Constraints (AGENTS.md): no `.env`/DB/auth-artifact mutation (temp dirs + synthetic creds);
  named test files only; offline queue fail-closed; strict moderation fail-closed; `log_event`
  isolated from caller transactions; `git diff --check` clean; stop all runners. Do not
  resurrect the deleted `LocalSpeechProvider.transcribe` alias (verified safe to be gone).

## 3. Starting procedure

1. `git status --short`, `git log --oneline -3`, `git diff --cached --stat`. Record the actual
   baseline (commit hash + modified files) at the top of your work log.
2. Complete §4 first: for each PROMPT_4 tier, confirm presence in the tree (code + tests), spot-
   check behavior, and record FIXED / PARTIALLY FIXED / NOT FIXED with evidence. Skip and mark
   done anything genuinely landed — but a green suite alone is not proof; exercise the behavior.
3. Then implement §5 tier by tier (H → I → J → K). Reproduce every item before fixing.

## 4. PROMPT_4 verification shell (PENDING — fill during execution)

For each tier, verify against the tree and record a verdict. PROMPT_4's scope (see `PROMPT_4.md`
§5): Tier A (A1–A7: import bounds, token strip, replay guard, LLM limits, difficulty, conflict
retry, collab queue), Tier B (A8–A14: 400-masking, UTC meter, batch N+1, history defer, export
N+1, refine_prompt, null-vs-None), Tier C (A15–A19: rehydrate gating, logout ordering, remote
dirt, settings races, toast counts), Tier D (A20–A25: config parity, CI passwords, TESTING
parity, start.bat pin, pip-audit extras, JWT doc), Tier E (E1–E6: ARASAAC staff gate, list
pagination, analytics batch cap, prompt-field bounds, TTS/lang/warmup validation, assignment
404), Tier F (F1–F7: portable migrations, warmup creds, shutdown races, scan bounds, seed
upsert, vector retry, CORS/warmup verify-first), Tier G (G1–G5: client bounds, Smartbar,
boundaries, batch clear, a11y), Deferred D-a–D-f.

| Tier | Status | Evidence required |
|---|---|---|
| A | PENDING | behavior probes for A1/A2/A3/A5 + 429 tests for A4 + specs for A6/A7 |
| B | PENDING | Postgres-width rejections, 500-vs-400 mapping test, TZ-pinned meter, statement counters |
| C | PENDING | rehydrate/logout/remote-dirt/settings/toast specs |
| D | PENDING | settings-matrix check, workflow inspection, script inspection |
| E | PENDING | 403/pagination/422/404 tests per item |
| F | PENDING | migration fixtures, warmup singleton test, shutdown drain test, seed upsert test |
| G | PENDING | growth/paging/boundary/clear/a11y specs |
| Deferred D-a–D-f | PENDING | triaged or done |

Explicitly re-check high-risk interactions after your changes: interceptor header shapes (A2),
queue ownership across logout/retry/rehydrate (A3/A6/A15/A16), prompt construction (A5/A13/E4),
import count/transaction semantics (A1/A10–A14), warmup credential sources (F2).

## 5. Fresh audited backlog (verified in tree — implement, don't re-investigate)

> **Coverage note (second audit pass).** After drafting, a full-coverage iteration swept 100%
> of non-test production code (all 108 backend files + 131 frontend sources + scripts/root).
> Tiers L–O below are its verified findings. Deliberately excluded to avoid duplication with
> in-flight PROMPT_4 work: import `topic_name`/`status` width bounds (PROMPT_4/A1 covers them —
> verify via §4, do not re-implement), Smartbar counter reset (PROMPT_4/G2), guardian
> `template_name`/`custom_instructions`/persona/preview/`overrides` bounds (PROMPT_4/E4).
> Also ruled out (checked, no defect): `index_symbol`/`schedule_symbol_image_download`
> exception paths, `get_speech_provider` lazy default, `log_symbol_usage` validation,
> NULL-hash login (401 via `TypeError` catch), lockout/audit table caps, translation
> concurrency bounds, seed rerun idempotency, `update_ui_language`/`update_user_settings`
> allow-lists, board view-vs-collab-write split, auth input labels/`aria-describedby`,
> `useVoiceRecorder` stream cleanup, TTS audio-URL revocation, achievement/i18n key sampling.

### Tier H — file integrity + account lifecycle (backend)

**H1 [P1] New accounts inherit stale lockout rows — first-run DoS.**
`auth.py:259` records login attempts even for unknown users, and `delete_user`
(`auth_users.py:835-838`) explicitly clears `FailedLoginAttempt` "otherwise a later account
with same username could inherit" — but none of the four creation paths
(`initial_admin_setup` auth.py:66, `register` auth.py:555, `admin_create_user`
auth_users.py:64, `create_student` users.py:58) reset lockout rows (verified: zero
`reset_attempts`/`unlock` hits in all four ranges). An attacker pre-locking `admin1` makes
first-run setup instantly 403-locked. Fix: delete/reset lockout rows for the username after
successful creation in all four paths. Validation: pre-lock → create → immediate login
succeeds; previously 403.

**H2 [P1] Setup form accepts the banned default password via submit path.**
`Setup.tsx:52` defines `notDefault` (≠ `admin123`) and the button disables on it, but
`handleSubmit` (L56+) checks only length/case/digit + mismatch — never `notDefault`. Enter-key
submit (or any future caller) reaches `setupAdmin` with `Admin123`, which the UI claims to
forbid. Fix: `if (!notDefault) { setLocalError(...); return; }` in `handleSubmit`.
Validation: spec submitting `Admin123` asserts local error + no `setupAdmin` call.

**H3 [P1] Refresh tokens never rotate — stolen refresh mints forever.**
`auth.py:532-551` returns only a new `access_token`; `jwt_utils.py:156-178` refresh has no
`jti`, and `decode_refresh_token` checks only exp/iss/type/sec_ver. A stolen 7-day refresh is
usable unlimited times until expiry/logout/password-change. Fix: rotate refresh on each use
with single-use `jti` (+ server-side reuse detection that revokes the family on replay, wired
into the existing `sec_ver` machinery, not a parallel revocation store). Update frontend
`refreshAccessToken` to persist the rotated refresh. Validation: double-use of an old refresh
→ 401 + family revoked; normal flow transparent; concurrent-refresh coalescing still holds.

**H4 [P2] Generic symbol update bypasses file validation and orphans uploads.**
`symbols.py::update_symbol` runs a bare `setattr` loop over `SymbolUpdate` (which includes
`image_path`/`audio_path`, `schemas.py:413-414`) with no `_save_symbol_image`/`remove_owned_
upload` handling — unlike `update_symbol_image` (L574-596) which validates + cleans up. Staff
can store arbitrary URLs/paths without MIME/bomb checks; replaced UUID files are never deleted
yet served forever under the 1-year immutable cache. Fix: exclude `image_path`/`audio_path`
from `SymbolUpdate`; force image changes through `update_symbol_image`. Validation: PUT with
paths → 422/ignored + old file intact; image route still replaces + deletes.

**H5 [P2] Multipart description/keywords bypass the 10k JSON cap.**
`symbols.py:403-405,454-456` (`upload_symbol`, `generate_svg_symbol`) declare bare
`Form(None)` while `SymbolBase.description/keywords` cap at 10_000 (`schemas.py:388,392`) and
columns are `Text` (no DB backstop) — ~12 MB rows via the form path. Fix: `max_length=10000`
on both form fields in both routes. Validation: 10_001-char form value → 422; boundary passes.

**H6 [P2] ARASAAC downloads persisted without size/content validation.**
`arasaac.py:153-168` writes upstream bytes as `.png`; `services/arasaac.py:107-123` returns
`response.content` unbounded with no length/type check — vs `file_uploads.py:150-186` (5 MB +
`Image.verify()` + bomb→413 + allowlist). A large/mislabeled upstream payload (bomb,
HTML-as-PNG) lands in `/uploads` and is served. Fix: run downloaded bytes through the same
size + PIL-verify allowlist before persisting. Validation: oversized/non-image payload → 413/
discard; valid PNG imports byte-identical.

**H7 [P2] Password reset leaves lockout in place; reset endpoint unthrottled.**
`users.py::reset_user_password` bumps `sec_ver` + commits but never unlocks
(`lockout_service.reset_attempts`/`unlock_account` absent) — a locked student stays 403 after
a teacher reset with the correct new password. Same endpoint (`users.py:279`) has no limiter
while `change-password` has `10/hour` and login/refresh have per-minute caps — a compromised
staff token can churn passwords (`sec_ver` bumps revoke victim sessions) unbounded. Fix: unlock
on successful reset + `@conditional_limiter("10/hour")` matching `change-password`.
Validation: locked → reset → login succeeds; burst resets → 429.

**H8 [P2] Heavy non-LLM endpoints have no rate limit.**
`export_import.py::export_data` (full export queries + counts), `symbols.py::get_symbols`
(limit 1000 + vector search under lock + 50k recall scan), `arasaac.py::search_arasaac` +
`import_arasaac_symbol` (upstream egress + disk writes per call; 10s/120s timeouts, no cache)
— none limited (limiters exist only on auth routes). Fix: per-endpoint `conditional_limiter`
rates + short search cache for ARASAAC. Validation: burst → 429; single calls unaffected;
cache hit skips upstream.

**H9 [P2] Unbounded concurrent SSE streams per user.**
`notifications.py::notifications_stream` → `subscribe(user_id)`; `notification_events.py:88`
`_subscribers: dict[int,set]` has no per-user cap (queue bounded at 100, subscribers not) —
vs `collab.py:28 MAX_ROOM_SIZE=50`. One user can open unlimited streams (FD/memory). Fix: cap
concurrent streams per user, reject excess with 429 + close. Validation: N+1th stream → 429;
disconnect frees the slot.

**H10 [P2] Guardian prompt-adjacent fields E4 didn't name.**
PROMPT_4/E4 covers `template_name`/`custom_instructions`/persona/preview/`overrides` — still
unbounded: `private_notes`, `change_reason`, `MedicalContext` subfields (E4 named persona/style/
forbidden/trigger only), all stored as JSON/Text and merged into prompts/services. Fix: length/
count caps mirroring sibling profile fields (verify each field's current bound-state first —
skip any E4 already capped). Validation: over-bound → 422; stored values round-trip.

**H11 [P3] Vocabulary-progress commit inconsistency.**
`symbols.py::add_symbol_to_board` flushes achievement progress without the explicit pre-response
commit `achievements.py:446-450` performs ("before responding"), relying on teardown commit —
immediate re-reads race. Fix: commit after the achievement check like the check route (keep the
best-effort `try/except` boundary so progress can never fail the symbol write). Validation:
add → immediate progress read reflects the award.

### Tier I — e2e integrity + operator tooling + docs

**H12 [P2] Whole Playwright project runs as the student by default.**
`playwright.config.ts:29-39` sets `storageState: playwright/.auth/student.json` on the entire
`chromium` project — any spec not overriding `test.use({storageState})` executes with the wrong
role, masking privilege bugs or failing falsely (teacher/admin states provisioned but
unconsumed). Fix: remove project-level `storageState`; require explicit per-spec/project role
opt-in. Validation: role-gated specs fail/pass correctly per role; suite green.

**H13 [P2] Groq-verify spec leaves a live paid key on the server.**
`e2e/groq-verify.spec.ts` types `E2E_GROQ_API_KEY` into the settings UI (autosave PUT) with no
restore/mask step (`grep delete|restore|afterAll` → zero hits); the GET fallback doesn't assert
`res.ok`. A shared/CI server retains the key. Fix: capture prior settings, restore/mask at test
end (even on failure), assert `res.ok` in the fallback. Validation: post-spec settings contain
no live key; fallback failure surfaces the status.

**H14 [P2] Null-password fixer defaults to destructive with no flag.**
`scripts/fix_null_password_hashes()` supports a non-destructive impossible-hash mode, but
`main()` hardcodes `delete_invalid=True` (L138) with no `--delete/--disable-login` flag —
an operator following the recovery runbook irreversibly deletes users. Fix: explicit flags,
default to non-destructive. Validation: default run disables (no deletes); `--delete` deletes;
dry-run untouched.

**H15 [P2] i18n audit is blind to `.ts` sources and multiline JSX.**
`scripts/i18n-audit.mjs` globs only `src/**/*.tsx` (store/toast/lib `.ts` invisible) and
explicitly skips multiline nodes. Fix: extend glob to `**/*.{ts,tsx}` with code-aware filter;
flag multiline JSX text. Validation: planted hardcoded strings in a `.ts` store + multiline JSX
trip the gate; clean tree passes.

**H16 [P3] Launcher waits 30 s after a server-thread crash.**
`launcher.pyw`: `run_server` re-raises in a daemon thread, but the main thread blocks in
`_wait_for_server(url)` (30 s deadline) before checking `is_alive()`. Fix: poll thread
liveness inside the wait; abort early when it dies. Validation: crash-injected startup exits
fast with the error surfaced.

**H17 [P3] Dist-freshness gate trips on test-only edits; release doc points at a ghost path.**
`e2e/prod-guard.mjs` treats any newer file under `src/` as stale build but only ignores whole
dirs (`e2e`, `tests`) — `src/**/*.test.*` still invalidates `dist`, incentivizing guard
bypasses. `docs/MAINTAINER_GUIDE.md:69` cites `installer/installer.iss`; the file is repo-root
`installer.iss` (verified present, `installer/*.iss` absent). Fix: ignore test globs in the
mtime walk; correct the doc path. Validation: test-only touch keeps the guard green; doc path
resolves.

### Tier J — frontend robustness (all verified by code read)

**H18 [P2] Export download silently does nothing in Firefox.**
`lib/download.ts::downloadJson` clicks a never-attached anchor; Firefox requires in-document
nodes for synthetic-click navigation. Fix: append → click → remove (keep delayed revoke).
Validation: DOM-attachment assertion in spec (or manual Firefox check noted in report).

**H19 [P2] Teacher-created students get no password confirmation.**
`Students.tsx`: mismatch is checked only for admin creators (L382-386) and the confirm field
renders only for admins (L796-809); the teacher branch posts a single typed password — a typo
creates an un-loggable account needing an admin reset. Fix: always render + validate confirm.
Validation: teacher-path mismatch blocked; match creates.

**H20 [P2] Six unbounded client-side growth sites.**
`tts.ts::lastSpokenAt` (set per `enqueue`, never evicted); `useBoardEditorSymbols` context maps
(non-current keys never evicted); `learningStore.messages` (uncapped; only providerHistory
sliced); `notificationsStore.add` (unconditional prepend; SSE-fed); `offlineStore.addConflict`
(exact-duplicate dedupe only, persisted); `SymbolSearchModal` (1000/page walk accumulated +
fully rendered). Fix: LRU/time caps, context eviction, message windowing (history from
backend), newest-N caps, paged/virtualized results. Validation: flood tests per site asserting
bounded memory/persisted bytes + intact behavior.

**H21 [P3] Small validation/identity fixes.**
`Achievements.tsx:475` uses editable `a.name` as React key (management table correctly uses
`a.id`) → `key={a.id ?? a.name}`; `SymbolPicker.tsx:70-72` spreads unvalidated categories
(`Symbols.tsx:122-126` already filters `typeof === 'string'` — copy that validation).
Validation: duplicate/renamed achievements render correctly; malformed categories payload
cannot break the picker (specs for both).

**H22 [P3] Search-failure feedback + batch clear.**
`SymbolSearchModal::handleSearch` catch only `console.error`s and the `noResults` hint requires
truthy `query` (category failures render blank) → inline error + retry. `BoardEditor::clearBoard`
loops sequential deletes with toast-only catch (stale grid on partial failure) → batch clear
endpoint (preferred) or bounded-parallel deletes + refetch on success AND partial failure.
Validation: failure specs asserting visible feedback and post-failure UI/server agreement.

**H23 [P3] Voice/fullscreen toggles lack accessible names.**
`CommunicationChat.tsx:171-180`, `Communication.tsx:544-550,876-882`: `title`-only icon
buttons vs `aria-label`'d neighbors. Fix: `aria-label` (+ `aria-pressed` on the toggle).
Validation: role queries name the controls and reflect state.

### Tier K — test fidelity (backend)

**H24 [P2] `client` fixture skips lifespan; `setup_test_db` patches 4 of ~15 session sites.**
`tests/conftest.py:83-96` does `yield TestClient(app)` instead of `with TestClient(app)` (no
startup/shutdown — unlike `collab_client`), so most API tests diverge from prod lifespan
behavior; `setup_test_db` patches 4 modules while `get_session()` users in
`prediction_service`, `content_safety`, `vector_utils`, `arasaac_library_import`,
`ngram_builder`, `symbol_svg_autogen`, `symbol_image_backfill`, `seed.py` resolve against the
uninitialized `:memory:` DB. Fix: `with TestClient(app) as c: yield c`; patch the single
source `src.aac_app.db.get_session` (or route services through `get_db`) instead of four call
sites. Validation: suite green under lifespan; a canary test proving startup state + shutdown
run; no test regresses to the uninitialized DB.

### Tier L — schema-width hardening, second wave (all verified: column vs writer)

**H25 [P1] Session-start derived names overflow `String(100)`.**
`learning/session.py:118-132` builds `LearningPlan(name=f"Learning: {topic}")` (100+10) and
`LearningTask(name=f"Explore {topic}")` (100+8) from `topic` validated to `max_length=100`
(`schemas.py:573`) into `String(100)` columns (`models/learning.py:102,121`) with no
truncation — 91+-char topics 500 on Postgres at `db.flush()` (SQLite masks it). Fix: truncate
(`topic[:90]` / `topic[:92]`) or widen columns with migration. Validation: 100-char topic
starts a session cleanly; stored names fit 100.

**H26 [P1] Board-AI LLM labels/colors bypass every width bound.**
`board_ai.py:247-269` writes `item["label"]` into `Symbol(label=…)` (`String(100)`) via
`get_or_create_symbol` (checks only `label_looks_bad`) and into `BoardSymbol(custom_text=…)`
(`String(100)`), plus `item.get("color")` into `String(20)` — with only `isinstance(str)`
checks upstream (`board_generation_service.py:170-184`). The validated `AISuggestion.label ≤
100` covers only the single-apply path, not this auto path; import validates the same fields
but generation does not. Fix: enforce ≤100 (label/custom_text) and hex-or-≤20 (color,
drop/replace on violation) before insert. Validation: overlong LLM-shaped labels → rejected/
truncated, never 500; boundary values persist byte-identical.

**H27 [P2] Background autogen topic-words unbounded into `Symbol(label)`.**
`prediction_service.py:658,679-722` schedules each LLM topic word (`_parse_topic_words` caps
*count* at 10, not length) through `ensure_symbol_generated → _persist_generated_symbol`
(`symbol_svg_autogen.py:152-161`), which checks only empty — a long phrase fails the background
commit (lost write + rollback noise). Fix: skip/truncate words >100 before scheduling or at
persist. Validation: 200-char word never reaches INSERT; normal words unaffected. Related, do
in the same change: bulk ARASAAC import (`arasaac_library_import.py:177-187`) writes upstream
`keywords[0]/categories[0]` with no bound while the single-import path caps 100/50
(`arasaac.py:36-38`) — mirror those truncations (upstream length distribution unverified, so
this is hardening, not a proven 500).

**H28 [P2] Autogen stores the casefolded dedup key as the display label.**
`symbol_svg_autogen.py:331,363-364` passes `normalized` (casefolded) as the thread `label`;
`_persist_generated_symbol:152` stores it — `Casa` is saved/displayed as `casa`
(`runtime_translation.py:77`). Fix: pass the original label for storage, normalized form only
for the dedup key. Validation: mixed-case topic word round-trips with original casing; dedupe
still case-insensitive.

### Tier M — services correctness (all verified by code read)

**H29 [P2] Routine Argon2 rehash logs out every device.**
`auth.py:339-342` persists `updated_password_hash` then calls `mark_credentials_changed`,
which bumps `security_version` (`credential_service.py:8-11`); `auth_service.py:79` returns a
new hash on routine `verify_and_update` upgrades, not just legacy migration. A hash-parameter
upgrade revokes all sessions. Fix: persist rehashes without the `sec_ver` bump (reserve
revocation for real credential changes). Validation: login with rehash-triggering hash keeps
other devices' tokens valid; password change still revokes.

**H30 [P2] Achievement check scans all custom achievements per user.**
`achievement_system.py:93-108` loads every custom automatic achievement (`.all()`) then filters
`target_user_id` in Python. Fix: SQL filter `(target_user_id IS NULL OR target_user_id =
:user_id)`. Validation: statement-counted test; awarded behavior identical.

**H31 [P2] Board generation `max_tokens=1000` vs `item_count` up to 100.**
`board_generation_service.py:148-150` fixes the budget while `item_count` scales to 100
(`schemas.py:533`, `board_ai.py:214-218`) — large grids deterministically fail the exact-count
check (`:180-184`). Fix: scale `max_tokens` with `item_count`. Validation: 100-item request
returns 100 valid items; small requests unchanged.

**H32 [P2] SVG autogen index failure leaves symbols unsearchable with no retry.**
`symbol_svg_autogen.py:172-180` logs warn-only on vector-index failure and `finally:307-314`
records `_recent_failures` only when `failed=True` — the symbol stays invisible to semantic
search until the next full repair. Fix: treat index failure as retryable/requeue. Validation:
injected index failure → symbol retried and searchable.

**H33 [P2] Vector-store readiness materializes full id sets; stale-check fails open.**
`local_vector_store.py:299-311` builds three whole-table id sets in Python per check; `:322-323`
returns the *entire* input as stale when the schema is unavailable, so a broken sqlite-vec
triggers a full-catalog embed attempt (`vector_utils.py:88`). Fix: count/`EXCEPT` comparison;
return empty set when unavailable. Validation: O(1)-memory check; unavailable store → no-op,
not full re-embed.

**H34 [P2] Reasoning blocks leak to the student on reasoning-only responses.**
`learning/common.py:63` returns `cleaned.strip() or text` — when the response is *only*
reasoning, the fallback republishes the original text with think blocks. Fix: return the
stripped result even when empty. Validation: reasoning-only output → empty, never tags.

**H35 [P2] Operator password reset doesn't restore access; user-service silent no-op.**
`src/scripts/account_admin.py:44-57` resets without checking `is_active`/lockout (vs API's
inactive→404 + lockout semantics; `unlock` is a separate subcommand) — access unrestored.
`user_service.py:91-96` silently no-ops on unknown `user_id` (API saved only by its pre-check).
Fix: clear lockout + warn on inactive in the script; return bool/raise on missing user.
Validation: locked/inactive reset restores login (with warning); unknown id surfaces.

**H36 [P3] Symbol-semantics crash on `label=None`.**
`symbol_semantics.py:100` does `s.get("label","").lower()` — the default applies only to
absent keys, so explicit `None` → `AttributeError` → 500. Fix: `str(s.get("label") or
"").lower()`. Validation: None/non-str labels handled, no 500.

### Tier N — frontend depth (all verified by code read)

**H37 [P2] Startup blank-screens if the English chunk fails.**
`main.tsx:13` top-level `await ensureLocale(...)` with no `try/catch`; `i18n/index.ts:118-121`
rethrows after transient failure → rejection escapes the module, app never mounts (offline /
English-locale users stuck on blank `#root`). Fix: mount anyway on failure so the bundled
Spanish fallback renders. Validation: injected chunk failure → app mounts with fallback.

**H38 [P2] Failed symbol sends permanently discard the utterance.**
`learningStore.ts:619-624` catches API errors into store state without rethrowing, but
`Learning.tsx:420-427` clears `symbolUtterance` unconditionally and `Communication.tsx:351-358`
clears the strip first with restore logic in a `.catch` that can never fire on API failure.
Fix: return success/throw on failure; clear utterance/strip only on success (keep drafts on
error). Validation: failed submit preserves the composed utterance + visible error.

**H39 [P2] Bulk delete bypasses the per-card ownership gate.**
`Boards.tsx`: cards gate on `canManageBoard(user, board.user_id)` (L584,602), but
`toggleSelectAll` (L327-333) selects every visible id and `confirmBulkDelete` (L345-370)
DELETEs them directly — teachers/students are offered (and attempt) deletes of unowned boards,
surfacing only as generic bulk errors. Fix: filter selection + delete set through
`canManageBoard`. Validation: unowned boards unselectable/undeleted; owned flow unchanged.

**H40 [P2] Dwell timer fires after unmount.**
`useAccessibleInteraction.ts`: the dwell `setTimeout` (L36-41) cancels only on
pointer-up/leave; no unmount cleanup (contrast `useHoverSpeak.ts:37`) — unmount mid-dwell
(e.g. linked-board navigation) fires `triggerClick` with a stale event. Fix: `useEffect`
cleanup clearing the timer. Validation: unmount-mid-dwell spec asserting no click fires.

**H41 [P2] Wasted fetch/render: object-identity deps, uncapped activity, warmup refire.**
`Dashboard.tsx:32` + `useTopicPickerPool.ts:69` depend on the whole `user` object while reading
only `user.id` → full refetches after unrelated settings saves. `Dashboard.tsx:145-158` renders
all ≤100 activity rows (assigned boards already `.slice(0, 6)`). `SettingsManager.tsx:19-54`
re-runs locale application + backend `warmup()` on every `settings` object replacement. Fix:
deps on `user?.id`/consumed primitives; slice activity (e.g. 10); narrow SettingsManager deps
to consumed values. Validation: settings-save triggers no refetch/warmup; activity DOM bounded.

**H42 [P2] Symbol Hunt keeps speaking after exit; topic cards reshuffle under the user.**
`useSymbolHunt.ts:236-242` transition to board-select clears timers but never `tts.cancelAll()`
(unmount does, L248) — queued prompts keep playing. `TopicPicker.tsx:161`
`ordered = useMemo(orderByPractice(topics), [topics])` re-shuffles on every identity change as
pictograms resolve (`useTopicPickerPool.ts:162-213`) — cards jump post-paint (mis-tap risk for
AAC users). Fix: `cancelAll()` on game-exit transition; seed/memoize shuffle independently of
pictogram resolution. Validation: exit-then-silence spec; order-stability spec across resolve.

**H43 [P2] Sidebar preloads create unhandled rejections.**
`Sidebar.tsx:73-88`: bare `import()` in sync `try/catch` (cannot catch async) with no
`.catch` — a failed chunk fetch surfaces as `unhandledrejection`, not the claimed silent skip.
Fix: `.catch(() => {})` on each preload. Validation: failed-chunk spec asserting no unhandled
rejection.

**H44 [P3] Notification read-state diverges silently on sync failure.**
`notificationsStore.ts:39-67` marks read optimistically, then only `console.error`s on PUT
failure — reload resurrects them as unread with no signal. Fix: revert optimistic update (or
toast) on sync failure. Validation: failed-sync spec asserting state consistency + feedback.

**H45 [P3] Accessibility: 5 verified gaps.**
`GuardianProfileModal` safety select falls back to `'default'` with no matching option (renders
blank, misrepresenting safety posture — fall back to `''`); `SymbolGrid` bulk checkbox has no
accessible name (add `aria-label` with symbol label); Navbar bell has static label, empty badge
span, no `aria-expanded` (add count + expanded state); `LearningMessageList` edit/report buttons
are hover-only `opacity-0` with no focus-visible override and `IconButton` adds none (touch/
keyboard users locked out); utterance-chip remove buttons share one static
`removeSymbolLabel` (parameterize with the symbol). Validation: role/name queries + keyboard-
only interaction specs per control.

### Tier O — contracts + test fidelity remainder

**H46 [P3] SPA `api`-prefix check is case-sensitive.**
`spa.py:49` matches lowercase `api` only, so `/API/…` serves `index.html` instead of JSON 404
(UNVERIFIED against live clients — no caller uses uppercase; fix is a one-word casefold).
Fix: casefold the prefix comparison. Validation: `/API/health`-shaped request returns JSON 404,
normal SPA fallback untouched. Treat as verify-first: if the router normalizes case upstream,
document as disproved instead.

### Tier P — read-path resilience + supply-chain + services (third coverage pass, all verified)

**H47 [P1] Board reads 500 on translation outage.**
`board_helpers.py:19-21` calls `_translate_symbol_text()` with no `try/except`;
`translate_text` raises `RuntimeError` on failure/open circuit (`runtime_translation.py:329-340`);
neither `GET /boards/{id}` (`boards.py:175-186`) nor the list path guards `serialize_board`.
One external-endpoint outage breaks all translated board views — the core read path. Fix: catch
`RuntimeError` per symbol, fall back to source text (log once, degraded-not-dead). Validation:
injected translation failure → boards render untranslated, 200s everywhere.

**H48 [P1] Network-downloaded voice catalog pickle-loaded with size-only gate.**
`providers/local_tts_provider.py:184` runs `np.load(..., allow_pickle=True)` on the Kokoro
voices pack downloaded via `urlopen` (`:332-382`); `model_files_present` (`:314-329`) accepts
on `>1MB` alone. A compromised mirror → arbitrary code execution at catalog-read time;
truncated downloads pass the gate and fail later at load. Fix: pin expected sha256/size per
file, verify post-download, and load the catalog without pickle. Validation: tampered/
truncated fixture rejected before load; valid pack loads identically.

**H49 [P2] ARASAAC download paths buffer unbounded bodies; shape breaks go silent.**
`services/arasaac.py:115-139` buffers full `response.content` with no byte cap on any download
path (compromised upstream → unbounded memory per request); `search_symbols` direct-indexes
`item["_id"]` inside a bare `except Exception: return []` (`:86-105`), so upstream shape
changes surface as silent empty results. Fix: stream with a max-bytes cap (reject oversize);
narrow the fallback to network/validation errors, let structural errors propagate.
Validation: oversized body rejected; malformed-upstream fixture raises diagnosably.

**H50 [P2] Board generation token budget can't fit large grids.**
`board_generation_service.py:148-150` fixes `max_tokens=1000` while `item_count` scales to 100
(`schemas.py:533`, `board_ai.py:214-218,427-431`); `:180-184` raises unless valid items exactly
equal `item_count` — large AI fills burn a call then always 500. Fix: scale `max_tokens` with
`item_count`. Validation: 100-item request returns 100 valid items; small grids unchanged.

**H51 [P2] Routine Argon2 rehash revokes every session.**
`auth.py:339-342` persists `updated_password_hash` then calls `mark_credentials_changed`
(`security_version+1`); `auth_service.py:79` returns new hashes on routine upgrades, not just
legacy migration. Fix: persist rehashes without the `sec_ver` bump (reserve it for real
credential changes). Validation: rehash-triggering login keeps other devices valid; password
change still revokes.

**H52 [P2] Reasoning-only responses leak think blocks to the student.**
`learning/common.py:63` returns `cleaned.strip() or text` — a response containing only
reasoning falls back to the original text with tags. Fix: return the stripped result even when
empty. Validation: reasoning-only fixture → empty output, never tags; normal answers intact.

**H53 [P2] Symbol-catalog fallback scan unbounded on genuinely new labels.**
`symbol_catalog.py::find_symbol_by_normalized_label` iterates the full id/label table for the
Python casefold comparison after the fast-path miss (every new board-AI label materializes
~17k rows in-request). Fix: `yield_per()` + row cap, or reuse the bounded `unicode_recall_ids`
helper. Validation: statement-counted test on a large fixture; match results identical.

**H54 [P2] Operator/admin password tooling gaps.**
`src/scripts/account_admin.py:44-57` resets without `is_active`/lockout handling (access not
restored; `unlock` is a separate subcommand) and `--password` (L93) takes the secret as CLI
argv (process-table/shell-history leak; env fallback exists but argv wins). `user_service.py:
91-96` silently no-ops on unknown `user_id`. Fix: clear lockout + warn on inactive; prefer
env/stdin secret with a warning when `--password` is used; return bool/raise on missing user.
Validation: locked/inactive reset restores login with warning; argv-use warns; unknown id
surfaces.

**H55 [P3] Achievement scan + vector check waste.**
`achievement_system.py:93-108` loads all custom automatic achievements then filters
`target_user_id` in Python → SQL filter `(target_user_id IS NULL OR = :user_id)`.
`local_vector_store.py:299-311` builds three whole-table id sets per readiness check →
count/`EXCEPT` comparison. `symbol_svg_autogen` index failure is warn-only with no retry
(`:172-180`, `:307-314`) → treat as retryable/requeue. `symbol_semantics.py:100` crashes on
explicit `label=None` (`s.get("label","").lower()`) → `str(s.get("label") or "").lower()`.
Validation: statement-counted test; unavailable store → no-op; None-label fixture → no 500.

**H56 [P3] Script hygiene: fd leak, `sys.exit` in library, link-check fences, config exposure.**
`scripts/smoke_live.py` never closes the server log handle before `rmtree` (fd leak; Windows
cleanup failure) → close in `finally`. `scripts/migrate_passwords.py:133-136` calls
`sys.exit(1)` inside a library function (kills importers; untestable) → raise, let `main()`
set the code. `scripts/verify_pr.py::check_markdown_links` regexes fenced code blocks (example
snippets false-fail the gate) → strip fences first. `routers/config.py:10-20` returns server-
side `OLLAMA_BASE_URL` unauthenticated → require auth or drop the field. Validation: Windows-
style cleanup test (or inspection + unit test), import-safety test, fence-snippet fixture,
unauthenticated GET assertion.

### Tier Q — frontend depth, second wave (all verified by code read)

**H57 [P2] Board duplicate orphans on mid-copy failure.**
`boardStore.ts::duplicateBoard` creates the board row, then POSTs symbols one by one
(L278-331); any mid-loop failure throws with error-state only — the half-duplicated board
stays for manual deletion (link pre-resolution narrows but doesn't close the window). Fix:
delete the new board when the copy loop fails. Validation: injected mid-copy failure → no
orphan board; success path byte-identical.

**H58 [P2] Register has no confirmation and no `minLength`; create/edit report wrong outcomes.**
`Register.tsx:21-83`: single `required`-only password field, hardcoded student role — a typo
creates an un-loggable account (contrast `Students.tsx` confirm + `minLength={8}`,
`UserManagement.tsx` `minLength={8}`). Fix: confirm-password field with match check +
`minLength={8}`. Same root pattern, fix together: `UserManagement.tsx:302-323` nests the
reload inside the create try (reload failure reports successful creates as failures, inviting
duplicates) → reload outside/nested-try; `Symbols.tsx:174-195` reports metadata+image as one
outcome (PUT-ok + POST-fail shows total failure though the edit persisted) → separate image-
step messaging. Validation: mismatch blocked client-side; reload-failure-after-create still
toasts success + closes; image-failure toast distinguishes saved metadata.

**H59 [P2] Symbol-send failures permanently discard the utterance.**
`learningStore.ts:619-624` swallows API errors into store state without rethrowing, but
`Learning.tsx:420-427` clears `symbolUtterance` unconditionally and `Communication.tsx:351-358`
clears the strip first with restore logic in a never-firing `.catch`. Fix: success flag/throw
contract; clear only on success, keep drafts + visible error otherwise. Validation: failed
submit preserves input in both callers.

**H60 [P2] Bulk board delete bypasses the ownership gate.**
`Boards.tsx`: per-card actions gate on `canManageBoard` (L584,602), but `toggleSelectAll`
(L327-333) selects every visible id and `confirmBulkDelete` (L345-370) DELETEs them directly —
unowned boards attempted, surfacing as generic bulk errors. Fix: filter selection + delete set
through `canManageBoard`. Validation: unowned boards unselectable; owned bulk flow unchanged.

**H61 [P2] `format()` throws `RangeError` on one bad timestamp, crashing the view.**
`lib/format.ts:22-28` passes `new Date(value)` straight to `Intl...format()`; callers
`Boards.tsx:621`, `Dashboard.tsx:154`. Fix: fallback string on `isNaN(date.getTime())`.
Validation: malformed-timestamp fixture renders fallback, view survives.

**H62 [P3] Assign/create UX swallows applied mutations.**
`Students.tsx:240-251` returns early without toast/modal-close when the boards-list ref changed
mid-flight although the POST applied (user retries → 409 confusion) → guard the assign by its
own mutation id. `Achievements.tsx:305-319` POSTs `{user_id: selectedStudentId}` with no null
guard (only button `disabled` protects) → early-return on null. `lib/learningTopics.ts:38-105`
migrates board-less legacy items → 422 aborts the whole queue → validate `board` non-empty in
the filter (skip-and-drop invalid rows). Validation: specs for all three (applied-assign
toasts; null award never sent; malformed legacy row can't block the queue).

**H63 [P3] Fetch/render waste + feedback gaps.**
`Dashboard.tsx:145-158` renders all ≤100 activity rows (slice to ~10); `Dashboard.tsx:32` +
`useTopicPickerPool.ts:69` depend on whole `user` while reading only `user.id` (settings saves
→ fetch storms) → narrow deps; `SettingsManager.tsx:19-54` re-applies locale + backend
`warmup()` per settings-object replacement → narrow to consumed primitives.
`useBoardAISuggestions.ts:114-159` never clears `aiError` on new apply (unlike apply-all L180)
→ clear on start. `topicCatalog.ts:72-77` substring pictogram match (`ir` in `mirar`) → word-
boundary/token match. Validation: storm-free settings save; bounded DOM; stale banner cleared;
correct pictograms on `mirar/algo`-shaped fixtures.

**H64 [P3] Accessibility + startup resilience.**
`Achievements.tsx:475` uses editable `a.name` as React key → `key={a.id ?? a.name}`;
`Achievements.tsx:676-686` award rows are `<div onClick>` (keyboard-inoperable) → real
`<button>` semantics; `SymbolGrid.tsx:46-50` bulk checkbox unlabeled → `aria-label` with
symbol name; Navbar bell has static label + empty badge + no `aria-expanded` → count +
expanded state; `LearningMessageList.tsx:112-133` edit/report hover-only → focus-visible
rules + touch affordance; utterance chips share one static remove label → parameterize with
the symbol; `useHoverSpeak` returns mouse-only handlers spread onto Smartbar buttons → add
`onFocus`/`onBlur` mirror. Startup: `main.tsx:13` unguarded `await ensureLocale` blanks the
app on chunk failure → mount with bundled `es` fallback; `Sidebar.tsx:73-88` bare preload
`import()` in sync try/catch → `.catch(()=>{})`. Validation: keyboard-only specs per control;
offline-chunk failure mounts fallback; failed preload emits no unhandled rejection.

### Tier R — final consistency + GUI verification readiness

**H65 [P3] Notification read-state and hunt audio hygiene.**
`notificationsStore.ts:39-67` marks read optimistically then only `console.error`s on PUT
failure (reload resurrects as unread, badge jumps) → revert or toast on sync failure.
`useSymbolHunt.ts:236-242` game-exit transition never `tts.cancelAll()` (unmount does, L248)
→ cancel on exit transition. Validation: failed-sync consistency spec; exit-then-silence spec.

**H66 [P3] Login setup-notice dead code + full-reload link.**
`Login.tsx:26-29` sets `setupRequired` then immediately navigates, so the banner (L65-78)
never displays; its link is a full-reload `<a href="/setup">`. Fix: remove the unreachable
banner (or delay navigation) + router `Link`/`navigate`. Validation: setup path navigates
without reload; no dead UI.
`spa.py:49` matches lowercase `api` only, so `/API/…` serves `index.html` instead of JSON 404
(UNVERIFIED against live clients — no caller uses uppercase; fix is a one-word casefold).
Fix: casefold the prefix comparison. Validation: `/API/health`-shaped request returns JSON 404,
normal SPA fallback untouched. Treat as verify-first: if the router normalizes case upstream,
document as disproved instead.

## 6. Simplification / deletion work

- H8/H9: reuse `conditional_limiter` + collab-style caps; no new frameworks.
- H30/H33: filters/set-ops in existing queries; no new helpers or stores.
- H41: narrower dep arrays and slices; no new state.
- H15/H17: extend/ignore in existing scripts and docs; no new tooling.
- H20: caps/eviction inside existing stores; no new stores or caches.
- H24: fewer patches (one source) — delete the four call-site patches if the single-source
  patch covers them.
- No new dependencies, providers, middleware, or config keys (H3 reuses `sec_ver` machinery;
  H7 reuses existing limiter rates).

## 7. Functional validation

- Uploads: staff-only paths validated, oversized/bomb/mislabeled payloads rejected, orphans
  cleaned, Firefox download works.
- Accounts: pre-locked creation logs in; reset unlocks; rotation transparent + replay revokes;
  setup rejects `Admin123` via UI submit; teacher typo blocked.
- Heavy endpoints/SSE: 429s under burst; single calls fine; stream slots freed on disconnect.
- Prompts: injection-shaped `difficulty`/preview/guardian values → 422; boundary values pass.
- e2e/tooling: role-correct projects, no leaked keys, guard green on test-only edits, fixer
  defaults non-destructive, launcher fails fast.
- Shutdown/startup: lifespan runs in tests (H24 canary); seeded modes complete; migrations
  verified on fixtures.

## 8. Regression validation

- Named files only: backend `tests/test_*.py` covering each touched area + new targeted tests
  per item; frontend specs for touched components/stores/e2e configs (run the affected Vitest
  files, plus `typecheck`/`lint`/`build` if TS touched).
- `uv run ruff check src tests scripts`, `python -m compileall -q src scripts`,
  `git diff --check`.
- Every item needs fail-before/pass-after evidence (probe output or pre-fix-failing test).

## 9. Live-GUI verification protocol (mandatory — browser tools, NOT Playwright)

Existing suites (Vitest + Playwright) already pass on this tree and therefore prove nothing
about your changes. After implementing Tiers H–R, you must drive the **real running product in
a real browser** (chrome-devtools MCP or equivalent browser tool with `google-chrome`; do NOT
write or run Playwright specs for this) and fix every issue you find proactively. Procedure:

1. **Build + serve:** `npm run build` in `src/frontend`, then start the backend serving the
   production build on `127.0.0.1:8086` with an **isolated** `DATA_DIR` (temp dir, never the
   real `data/`), `TESTING=1` + seeded demo accounts (`admin1/Admin123`, `student1/Student123`,
   `teacher1/Teacher123`) for speed. Kill the server at the end; confirm the port is closed.
2. **Walk every flow below as three roles** (admin, teacher, student), watching the browser
   console + network tabs throughout — any console error, failed request, or blank/stuck UI
   is a defect you must fix, not note:
   - first-run setup (fresh DATA_DIR, no seed): banned-password rejection, mismatched
     passwords, successful bootstrap → dashboard;
   - login/logout (incl. logout mid-login), register with typo + match, expired-session
     behavior (stale token → refresh → seamless retry, never a bounce);
   - boards list (paging, search, select-all + bulk delete as teacher AND student, duplicate
     with symbols, broken-link handling), board editor (move/save/clear, collab in TWO
     browser windows simultaneously, remote-move display + save semantics);
   - symbol library (search incl. `mirar`/`algo`-shaped queries, categories, edit with +
     without image change, bulk select with screen-reader names);
   - learning session end-to-end (start with 100-char topic, ask/answer incl. voice-path UI,
     symbol answers with simulated failure → draft preserved, history panel, session summary);
   - achievements (award flow keyboard-only, duplicate names render correctly);
   - settings (AI provider switch + model fetch overlap, rapid slider edits, truncated-import
     warning toast with shown/total, export download actually saves a file);
   - students/user management (teacher create with mismatch, admin create + reload-failure
     simulation via offline devtools, assign board, reset password → student logs in
     immediately without separate unlock);
   - notifications bell (count announced, mark-read survives reload), offline mode (devtools
     offline → queue → reconnect → no conflicts minted for expired token after refresh);
   - Symbol Hunt game (exit mid-speech → silence), dashboard streak display, locale switch
     es↔en on every visited page (no hardcoded strings, no blank fallbacks).
3. **Failure injection (devtools):** offline mid-save, 500-injected via request blocking on
   save/clear/import endpoints, expired token (delete from storage), oversized upload. The UI
   must always show feedback, never lose user input, never misreport outcomes.
4. **Accessibility keyboard-only pass:** full Tab/Enter/Space run of login → boards → editor →
   learning → settings; every icon-only control operable and named; no hover-only functionality.
5. **Record evidence:** for each flow — role, steps, observed result, console/network status,
   plus any bug found → fix → re-verified. This log is part of your final report. If your
   environment truly has no browser tool available, say so explicitly and substitute the
   closest live-server + `curl` walk — do not silently treat unit tests as GUI validation.

## 10. Manual-QA readiness checklist (state for each line: DONE / OPEN with evidence)

The next step after you is a human full-QA pass. Your report must close with this table filled
in: live-GUI walk (§9) complete per flow; no console errors on any walked flow; no known
P1/P2 open; failing-first evidence for every Tier H–R item; gates green (ruff, compileall,
typecheck, lint, build within budget, named backend + frontend suites); no background
runners/servers left; no `.env`/DB/auth-artifact mutation; external gates still open
(Windows artifact rehearsal, live-Groq run, human beta/privacy review, CI green run) unless
actually executed.

## 11. Cleanup after implementation

- Remove superseded validators/comments/aliases and dead branches exposed by refactors; keep
  no old/new parallel paths. Delete temp probes; keep committed regression tests. Stop all
  runners/servers.

## 12. Final bug hunt

Re-inspect every touched flow (upload replacement paths, lockout/creation/reset interplay,
rotation vs coalescing/WS revalidation, limiter coverage, prompt construction, e2e role
isolation, fixture lifespan effects on the whole suite) for regressions, stale callers, newly
dead code, and fresh simplifications.

## 13. Definition of done

- §4 verdicts recorded with evidence; all Tier H–R items fixed or blocked with demonstrated
  evidence; net complexity down.
- Targeted validations fail-before/pass-after where practical; named regression tests +
  lint/compile/build gates green; `git diff --check` clean.
- SHORT final report: per item, files changed + validation evidence. External gates (Windows
  rehearsal, human review, live CI/Groq runs) stay explicitly open unless actually executed.
