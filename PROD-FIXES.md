# Production readiness fixes — agent handoff

Audit date: 2026-09-09. Baseline: `7c2f9f079f72354f02ab19f62caa0887ddb862b1`.

Verdict: **not ready for production sign-off**. Confirmed security, privacy, and request-lifecycle defects remain. Build and deployment verification also have unresolved evidence gaps. This was a source audit with focused tests and isolated probes, not a completed live deployment, penetration test, or clinical review.

## Prompt for the fixing agent

```text
/goal Fix the production-readiness issues in PROD-FIXES.md in AAC_ASSISTANT, starting with P1 security/privacy and availability defects. Reconfirm each finding against the current tree, implement small scoped fixes, add meaningful regression coverage, and update this document with the change and actual validation evidence for every item. Resolve P2 items as well. Follow AGENTS.md, preserve user data and documented external API compatibility, and keep Groq as the production provider with its explicit model requirement in generate(), not its constructor. Do not modify real .env, databases, saved credentials, or authentication artifacts. Use isolated temporary runtime directories and synthetic credentials for reproduction. Do not add frameworks or dependencies without concrete need. Do not preserve dead application code for tests. Do not run full test suites unless the user explicitly authorizes them; use named affected test files/specs. Do not modify Windows launcher/packaging behavior without the task-specific authorization required by AGENTS.md. Finish with a per-item disposition, actual test/build results, and any external release gates still blocked. Never mark production readiness complete merely because code checks pass: missing dependency audits, production-mode smoke, Windows release rehearsal, and human acceptance evidence must remain explicitly open when unavailable.
```

The tasks below are the concrete scope of that goal. P1 means fix before production sign-off; P2 means resolve before release, with deployment-dependent limitations documented explicitly. A passing existing test does not invalidate a finding when the test encodes the problematic behavior.

## P1 findings

### F01 — Production accepts an insecure environment JWT secret

- **Evidence:** `src/config.py:345` validates the process secret only to decide whether to generate/rewrite dotenv content. `Settings.JWT_SECRET_KEY` is an unconstrained string, and environment settings still override the generated secure file value. `src/aac_app/utils/jwt_utils.py:35` rejects only one exact placeholder; it does not enforce the shared length/placeholder policy.
- **Confirmed probe:** with `ENVIRONMENT=production`, an isolated `load_settings(temp_directory)` accepted a synthetic short environment key; token creation and decoding both succeeded. PyJWT emitted an insecure-key-length warning, not a rejection.
- **Impact:** a deployment typo or known short secret leaves signed credentials forgeable with a weak key despite apparent startup safeguards.
- **Fix:** validate the final effective secret before token use, consistently across configuration and JWT code. Reject invalid explicitly configured production secrets with a safe diagnostic; do not silently rotate existing valid credentials. Normalize environment-name checks consistently.
- **Acceptance:** production subprocess tests for short keys, whitespace, each placeholder, environment-over-dotenv precedence, and a valid environment-only read-only deployment. Never print actual keys.

### F02 — Offline persistence captures administrator passwords and provider secrets

- **Evidence:** `src/frontend/src/lib/api.ts` queues essentially every non-GET request except a short auth exclusion list. `/users/reset-password`, privileged account creation, and `/settings/ai` are not excluded. `src/frontend/src/lib/offlinePersistence.ts:78` preserves request data/params and removes only the Authorization header. Actual callers include `pages/UserManagement.tsx:384`, `pages/Students.tsx:478`, and `store/settingsStore.ts:128`.
- **Confirmed probe:** transpiling and invoking the actual sanitizer preserved synthetic `new_password` and `groq_api_key` fields unchanged. The queue uses sessionStorage; this is persistent across reloads within the tab, not an assertion about permanent localStorage retention.
- **Impact:** sensitive operations store plaintext secrets and may unexpectedly execute after reconnection; conflict persistence can retain the same payloads.
- **Fix:** use an explicit allowlist for supported offline communication/board mutations. Reject sensitive operations before queue/conflict insertion. Sanitize existing persisted entries on hydration, including secret-bearing headers and params. Surface a safe reconnect-required message without retaining secrets.
- **Acceptance:** offline password reset, admin/student creation, provider settings, and secret-bearing headers never appear in queue/conflict storage; ordinary supported board edits still survive reload and replay for the same user.

### F03 — Refresh tokens travel in request URLs

- **Evidence:** `src/api/routers/auth.py:426` declares plain `refresh_token: str` as a query parameter. `src/frontend/src/store/authStore.ts:287` sends it in Axios `params`.
- **Impact:** the seven-day credential appears in request targets and can enter Uvicorn/reverse-proxy access logs and diagnostics.
- **Fix:** send refresh credentials in a request body or another deliberately supported non-URL credential channel. Update frontend and API contract together. Audit documented external consumers before retiring query compatibility; any necessary transition must address logging exposure and have a removal plan.
- **Acceptance:** inspect actual refresh request targets and captured application/access logs using synthetic credentials; no credential appears in URLs. Valid, expired, revoked, and malformed refresh flows still behave correctly.

### F04 — Refresh completion can overwrite a newer authentication session

- **Evidence:** `src/frontend/src/store/authStore.ts:282` captures a refresh token, awaits the request, then unconditionally publishes a new access token or calls `clearSession()` on failure. The epoch protection implemented for `checkAuth` is not applied to refresh. `lib/api.ts` can initiate refresh independently for concurrent 401 responses; `App.tsx` also refreshes on expiration.
- **Impact:** a delayed refresh from user A can replace user B's token after a session switch, or a delayed failure can clear B's session. Concurrent refresh bursts also consume the refresh rate limit.
- **Fix:** bind refresh results to the initiating identity/token/session generation; coalesce refreshes for the same session and discard stale success/failure results. Audit login/setup completion for the same stale-publication pattern.
- **Acceptance:** deferred-response tests for refresh → logout, refresh → login as another user, stale failure after a new login, and many simultaneous expired-token requests. A newer session must remain internally consistent.

### F05 — Collaboration permissions never expire or revalidate

- **Evidence:** `src/api/routers/collab.py:117` validates the token and computes view/write permissions only at connection establishment. The receive/broadcast loop reuses those values indefinitely. `ConnectionManager.broadcast` does not revalidate recipients.
- **Impact:** existing sockets can continue receiving private board changes after token expiry, logout/revocation, account deactivation, assignment removal, or a public-to-private board change. Initial authentication tests do not cover this lifetime issue.
- **Fix:** enforce expiry and periodically/eventfully revalidate active-user and current board authorization with fresh database state, covering idle receivers as well as senders. Revoke room membership promptly on access loss.
- **Acceptance:** open sockets, change each relevant security/access state using a separate committed session, and verify the old socket closes and cannot receive or transmit further changes. Include a receiver that sends nothing.

### F06 — Collaboration retains database connections and has unbounded slow-peer waits

- **Evidence:** `collab.py` retains `db: Session = Depends(get_db)` across the entire socket lifetime after issuing queries; `src/api/deps/db.py` closes it only on endpoint exit. The file-backed database engine uses normal pooling. `ConnectionManager.broadcast` awaits recipients serially without a deadline. No room/account connection cap is present in that manager.
- **Impact:** enough idle sockets can consume the database pool; one slow recipient can stall fan-out. A safety event also commits through the retained session, mixing transaction lifetimes with a long-lived transport.
- **Fix:** use short-lived database sessions for authorization/events, release connections before waiting on sockets, and bound connection counts and slow-peer sends. Keep concurrency bounded and cleanup deterministic.
- **Acceptance:** with a deliberately small pool, idle sockets do not prevent HTTP/database work; a stalled recipient does not delay healthy peers indefinitely; disconnect and shutdown restore connection/task counts.

### F07 — Voice recognition blocks the async request loop

- **Evidence:** async `src/aac_app/services/learning/responses.py:26` calls synchronous `_transcribe_voice_response` directly. At line 698 it invokes `recognize_from_file`; `local_speech_provider.py` acquires a threading lock, potentially loads a model, and consumes transcription segments synchronously. The async voice route awaits this service directly.
- **Impact:** one slow transcription/model load can stall other requests and WebSockets in the same server worker. A larger browser timeout does not fix server availability.
- **Fix:** offload only the blocking speech operation with bounded admission/concurrency. Keep ORM sessions out of concurrent thread use and define cancellation/temp-file/model ownership so a cancelled wrapper does not delete resources still used by a worker.
- **Acceptance:** a controlled slow speech provider runs while a heartbeat/health request and WebSocket traffic remain responsive; cancellation/shutdown leaves no worker using a removed file or released model. Avoid real model downloads in the regression test.

### F08 — Strict moderation treats missing or incomplete validation as approval

- **Evidence:** `src/aac_app/services/content_safety.py:557` allows output when the sentinel errors or its cap is exhausted. It treats any result lacking the substring `blocked` as allowed, including empty/garbled responses, and sends only `text[:600]` to moderation. Existing tests explicitly encode fail-open behavior.
- **Confirmed probe:** strict policy plus enabled sentinel plus an empty generated verdict returned `allowed=True`.
- **Impact:** text can reach the child even though the configured strict check never produced an affirmative verdict, or the unsafe portion falls outside the moderated prefix.
- **Fix:** require a valid affirmative moderation result for strict generated output. On unavailable/capped/malformed moderation, use an existing safe localized response or another explicitly reviewed safe fallback that preserves communication availability. Cover all delivered generated text. Do not block ordinary non-AI AAC communication.
- **Acceptance:** provider errors, timeouts, empty/ambiguous responses, cap exhaustion, and unsafe suffixes do not publish unchecked generated text. Update tests that currently expect fail-open behavior; preserve accessible localized fallback UX.

### F09 — Logging can expose secrets and child communication

- **Evidence:** `src/api/logging_config.py:84` enables `diagnose=True`, DEBUG, and backtraces for console and file sinks regardless of environment. Production paths call `logger.exception`. `services/learning/responses.py` logs original/expanded AAC text, and `providers/openrouter_provider.py` logs entire upstream error bodies.
- **Impact:** diagnostic exception locals and verbose content logs can capture credentials, prompts, child messages, or upstream response content. This is exposure potential and explicit content logging, not a claim that real secrets were found in tracked files.
- **Fix:** disable diagnostic local-value dumping in production, use appropriate configurable levels, and remove/redact sensitive message and upstream-error content. Keep safe operation IDs/status/error categories for troubleshooting.
- **Acceptance:** trigger exceptions and failed provider responses with synthetic secret/message canaries; verify all configured sinks omit them while recording actionable errors.

### F10 — Groq credential resolution is inconsistent and can inherit another provider's key

- **Evidence:** `GroqProvider.__init__` passes an absent Groq key to `OpenRouterProvider.__init__`, which falls back to `OPENROUTER_API_KEY`. `get_groq_provider` reads a DB key defaulting to empty and compares that empty value against the resolved environment key on subsequent calls, causing recreation when only an environment key is used. `.env` values are loaded into config, not exported into `os.environ`; provider constructors use `os.getenv`. `board_ai.py:314` rejects an absent DB key before considering any environment/config fallback.
- **Confirmed probe:** with only a synthetic OpenRouter environment key present, constructing `GroqProvider(model=...)` adopted that unrelated credential.
- **Impact:** wrong credentials can be sent to Groq; documented config-only credentials may fail on some routes; environment-only configuration can repeatedly replace clients, potentially closing a client another request is using.
- **Fix:** define one consistent provider-specific effective credential resolution for DB, canonical config, and process environment with explicit precedence. Never fall back between providers. Compare effective values for singleton reuse. Preserve request-scoped model-listing key precedence and explicit model validation in generation.
- **Acceptance:** matrix tests for DB-only, dotenv-only, process-env-only, absent key, unrelated-provider-only key, and request-header model listing. Repeated getters reuse unchanged configuration; board generation and learning use the same effective Groq credentials without real network calls.

## P2 findings

### F11 — Upload limits apply after multipart parsing has already consumed the body

- **Evidence:** `src/api/file_uploads.py` enforces 5 MB image/10 MB audio limits while reading an already-created UploadFile. Routes declare FastAPI `File(...)`. The installed framework code reads `request.form()` before dependency resolution; its multipart file parts spool to temporary files, and its ordinary `max_part_size` check applies to non-file fields. No application-wide streaming request-size guard or documented reverse-proxy body-limit configuration was found in the inspected production paths.
- **Impact:** an oversized multipart request can consume disk/I/O before endpoint-level rejection, including before authentication. Pydantic JSON field limits likewise do not bound the initial body read.
- **Fix:** enforce bounded request consumption before framework parsing, and document/enforce the equivalent limit for managed reverse-proxy deployments. Account for chunked bodies and multipart overhead; keep legitimate audio/import limits usable.
- **Acceptance:** oversized multipart and JSON requests, both declared-length and chunked, stop after bounded consumption. Verify parser temp-file cleanup and authenticated/unauthenticated behavior. Recheck framework behavior against the authoritative lockfile after provisioning dependencies.

### F12 — Active logs have no size bound

- **Evidence:** `logging_config.py` gives each process a file name fixed at import and configures retention without rotation. Age cleanup runs at setup/retention events; a continuously written active file remains fresh indefinitely.
- **Impact:** long-running or noisy deployments can fill the runtime volume despite the nominal seven-/fourteen-day retention settings.
- **Fix:** add bounded per-process rotation/storage retention preserving the Windows file-sharing fixes. Do not reintroduce shared-file rotation races.
- **Acceptance:** a small configured test threshold rotates/caps active logs during a long-lived process; two concurrent processes remain safe; cleanup does not remove another active process's files.

### F13 — Export/import does not preserve board navigation and silently limits history

- **Evidence:** `src/api/routers/export_import.py:378` deliberately sets every imported `linked_board_id=None`. `_import_boards` already creates a source-ID mapping, but does not restore links afterward; `_board_content_matches` also omits links. Export at line 618 takes only the latest 100 learning sessions and omits conversation history. The recovery runbook describes recovery checks without explicitly describing all these losses.
- **Impact:** recovered hierarchical AAC boards lose navigation. Users can interpret a successful export/import as complete recovery despite omitted learning data.
- **Fix:** safely remap links among authorized imported boards in a second pass and include navigation in retry matching. Explicitly define the selective export contract: preserve intended learning data or return/document visible truncation and exclusions. Preserve HMAC integrity and do not trust unrelated local ID collisions.
- **Acceptance:** linked-board round trip, cyclic/missing/external references, repeated imports, unrelated local ID collisions, and more than 100 learning sessions. Verify actual navigation, not just counts. Keep physical DB plus uploads/config recovery distinct from selective export.

### F14 — Safety logging commits its caller's transaction and retains unbounded event content

- **Evidence:** `src/aac_app/services/content_safety.py:456` calls `db.commit()` on a supplied session and catches exceptions without restoring failed transaction state. Callers include learning, board AI, and collaboration. Safety events retain message excerpts. The events router provides a manual delete-all action, but no age/row retention policy was found for this table. Sentinel daily usage is counted from those deletable rows.
- **Impact:** a supposedly best-effort log can prematurely commit unrelated staged changes or leave the caller's session unusable. Event content grows until manual deletion, and clearing events resets the apparent daily moderation usage.
- **Fix:** make transaction ownership explicit; use caller-owned staging or a deliberate isolated event transaction according to required audit durability. Add bounded, documented event retention and preserve cost accounting when logs are cleared/pruned. Avoid a broad transaction-framework rewrite.
- **Acceptance:** logging cannot commit unrelated caller work; simulated logging failure leaves the caller usable or fails explicitly without partial success; retention is bounded and does not reset the current day's cost limit.

### F15 — CI production checks run in test mode

- **Evidence:** `.github/workflows/ci.yml:85` names the job `e2e-production`, but sets `ENVIRONMENT=test`, `TESTING=1`, sample data, and demo credentials. `conditional_limiter` bypasses limits under TESTING. Startup polling checks `/api/health`, not `/ready`. Windows packaging smoke likewise uses test configuration and lacks the documented `AAC_ASSISTANT_NO_BROWSER=1` flag.
- **Impact:** green CI validates a production frontend build, but does not establish production Groq selection, secure bootstrap, enabled rate limiting, or actual readiness behavior.
- **Fix:** retain useful deterministic E2E coverage, add a distinct isolated production-mode gate with TESTING absent, synthetic strong credentials, no demo seeding, and controlled provider responses. Verify success and degraded readiness/configuration cases. Document the separate real-Groq and Windows release evidence still required. Treat any Windows workflow/launcher behavior change under AGENTS.md's authorization and validation rules.
- **Acceptance:** demonstrate production mode is actually active; test a real rate-limit response, prohibited insecure config, Groq selection, `/ready` degradation and recovery, and SPA/assets. Do not claim a stubbed provider test proves live Groq service availability.

### F16 — Readiness is primarily a startup snapshot

- **Evidence:** `src/api/main.py` uses `app.state.database_ready` set during startup and `get_startup_state()` provider flags. `_init_llm_provider_sync` reports success after constructing a provider with a configured model; it does not establish successful generation or even credential validity. No current DB probe occurs in `/ready`.
- **Impact:** `/ready` can report healthy after runtime DB failures or with unusable provider credentials. Operators may misread initialized resources as verified service capability.
- **Fix:** specify and implement the intended liveness/readiness contract. Add a cheap bounded current DB check and safe cached/provider-degradation state where appropriate; do not issue paid model generations on every health poll. Return public safe diagnostics, keeping detailed failure context in protected logs.
- **Acceptance:** DB loss after startup produces the documented non-ready response within a bounded interval; invalid/missing provider credentials and runtime failures are reflected accurately without unbounded probes, secret leakage, or repeated paid calls.

## Validation and audit coverage

Inspected production scope: `src/aac_app` (models/schema/seed, database, auth, learning, content safety, Groq/OpenRouter and voice providers); `src/api` (startup/readiness/static serving, auth/access/settings/database dependencies, auth, boards/AI/symbols, collaboration, providers, notifications, content safety, export/import); `src/config.py`; `src/scripts/account_admin.py`; operator launch scripts, `launcher.pyw`, `AAC_Assistant.spec`, `installer.iss`, and packaging/CI definitions; `src/frontend/src` (routing, auth/API/offline persistence, settings, board collaboration/editor and UI primitives); manifests/lockfile-related checks and release/recovery documentation. This is critical-path coverage, not a claim that every file or endpoint was exhaustively tested.

Production reference searches used those source/operator/packaging/documentation roots separately from tests, excluding ignored/generated dependency/build/cache trees as liveness evidence. Installed framework sources were inspected only to understand request parsing, not to justify application liveness. No production deletion or cleanup pass was performed. One possible maintenance follow-up is `LocalSpeechProvider.transcribe`: searched production roots show the application calls `recognize_from_file`; the other `.transcribe` call is on the underlying Whisper model. Its compatibility obligation must be reconfirmed across dynamic/external contracts before any deletion. This is not a release blocker or authorization to delete on the basis of tests alone.

Actual checks performed:

| Check | Outcome |
| --- | --- |
| Ruff on `src tests scripts launcher.pyw`, using installed environment with `uv run --no-sync` | Passed |
| Dependency usage evidence script, using `--no-sync` | Passed |
| `compileall -q src scripts launcher.pyw` | Passed |
| `bash -n start.sh` | Passed |
| Frontend ESLint with `--max-warnings=0` | Passed |
| Frontend `tests/authStore.test.ts`, `tests/api.test.ts`, `tests/offlineStore.test.ts` | 3 files, 49 tests passed |
| Backend `tests/test_config_pydantic.py`, `tests/test_groq_provider.py` | 18 tests reached 100%, process exited 0 |
| Isolated synthetic probes | Short production JWT key accepted and usable; Groq inherited OpenRouter key; strict empty moderation verdict allowed; offline sanitizer retained password and provider key |
| Locked offline Python invocation | Blocked: uncached `resvg-py==0.5.0` needed download; subsequent checks used existing environment, not a freshly synchronized lockfile environment |
| Frontend typecheck | Failed: missing installed `@base-ui/react`, `class-variance-authority`, and `sonner`, plus resulting implicit-any errors; `npm ls --depth=0 --omit=dev` confirmed these missing packages |
| Production npm vulnerability audit | Unavailable: registry DNS failed with `EAI_AGAIN`; no clean vulnerability result claimed |
| Broader focused backend selections including collaboration/content safety/uploads | Did not complete: initial run interrupted; narrower attempts hit explicit 60-/30-second limits. Partial dots are not passing-suite evidence; no definitive hang diagnosis established |
| Full suites / consolidated `verify_pr.py` | Not run, per repository instruction requiring explicit full-run authorization |
| Fresh frontend production build, browser/live-server smoke, live Groq, Windows artifact/update/rollback rehearsal | Not completed |

The typecheck failure is an **environment/provisioning gap**, not proof that all reported TypeScript errors require source edits. First install authoritative locked dependencies in a suitable environment, then rerun typecheck/build before changing typings. Likewise, historic green counts in release docs are not validation of this audited commit.

> **Status (2026-09-13):** outcome of the F01–F16 remediation plus the `D1–D13` and `N1–N12`
> follow-up passes is recorded below in "Fixes pass — 2026-09-10", "Follow-up pass — 2026-09-11
> (D1–D13)", "Follow-up pass — 2026-09-13 (N1–N12)" and "Verification pass — 2026-09-13
> (doc vs. code, claims re-checked)". Every F/D/N item has an explicit disposition with the
> evidence actually produced. That last pass re-checked each claim directly against the working
> tree (not against the earlier reports): all F01–F16 behaviors are present in code, one stale
> `moderate_output` docstring was corrected, and five documented acceptance criteria that had no
> test (F03/D5 refresh transport, D2/N2 sentinel meter, F10 credential matrix + singleton, F16
> runtime DB loss, F06 room cap) now have named regression tests. Two wording overstatements in
> this document (F13's claimed assigned-board test coverage, F02's "rejected before queue/conflict
> insertion") were corrected in place. A final "Remaining-issues pass — 2026-09-13" then closed
> what those passes left open: the CI production gate was proven unable to pass (it bootstrapped
> with the development-default password and relied on a `GROQ_MODEL` setting that had no
> implementation), the documented `GROQ_MODEL` setting was implemented, two tests still asserting
> the retired query-param refresh transport were updated (the full suite had never been run, so
> they had gone unnoticed), dead `LocalSpeechProvider.transcribe` was deleted, and the dependency
> audits, frontend build/bundle, full backend suite (0 failures, 86% coverage) and full frontend
> suite (857 tests) are now green. External release gates (Windows artifact/update/rollback
> rehearsal, human beta/privacy/accessibility review, GitHub Actions green run, and a live-Groq
> run — blocked because no real key exists in this repository) remain **open**; no production
> sign-off is claimed.

## Fixes pass — 2026-09-10

Scope: address the first batch of production-readiness defects under AGENTS.md. Changes span security (F01, F02, F03, F09), reliability (F04, F06, F07, F11, F14), content safety (F08, F13), provider/collab correctness (F05, F10, F13), and deployment/observability (F12, F15, F16). No full test suite run (requires explicit authorization); no `.env`/DB/auth-artifact mutation; Windows behavior untouched per AGENTS.md.

### F01 — production JWT secret validation — **fixed**

- Root cause: production accepted any short/placeholder secret; check lived only in dotenv generation, not on the effective (env-over-dotenv) value.
- Change: `src/config.py:validate_effective_jwt_secret` checks the resolved effective secret in production (≥32 chars, rejects placeholder/whitespace), using `config.get` so dotenv-set `ENVIRONMENT` is honored with env-over-dotenv precedence. `src/aac_app/utils/jwt_utils.py` calls it at import and before minting.
- Evidence: isolated probe with synthetic `JWT_SECRET_KEY=tooshort` and `ENVIRONMENT=production` from dotenv rejects with `ValueError`; `process.env=production` overrides dotenv file; `development` stays permissive; valid 40-char production key accepted. `tests/test_phase2_security.py::test_production_rejects_default_jwt_secret` updated to current message and passes.

### F02 — offline persistence secrets — **fixed**

- Change: `src/frontend/src/lib/offlinePersistence.ts` switched to an explicit allowlist (`/boards/`) plus blocklist/sensitive-key detection; `sanitizeOfflineConfig` rejects secret-bearing or non-allowlisted mutations before persistence and on hydration, strips sensitive headers/params. Queue/conflict hydration re-validates via the same sanitizer.
- Evidence: new `src/frontend/tests/offlinePersistence.test.ts` (9 tests) exercises `sanitizeOfflineConfig` directly against the real module — rejects password-reset, privileged user creation, `/settings/ai` with API key, secret payloads, secret-bearing params, and headers; preserves ordinary board edits via the allowlist. Existing `tests/api.test.ts` and `tests/offlineStore.test.ts` still pass.
- **Precision note (2026-09-13 audit):** rejected mutations are dropped from the in-memory replay queue (`api.ts::persistQueue`) and excluded from storage on both write and hydration (`writeOfflineConflicts` → `persistConflicts` filters through the same sanitizer), so no secret is ever persisted. They may still appear as an **in-memory** conflict entry for user-visible feedback (documented by `offlineStore.test.ts`); that entry is never written to storage and disappears on reload. The earlier phrase "rejected before queue/conflict insertion" overstated this — the accurate statement is "removed from the replay queue and never persisted".

### F04 second-pass correction (2026-09-10) — coalescing keyed to token identity

The first pass coalesced concurrent refreshes through a single in-flight slot. This pass replaced it with a per-token map (`refreshInFlightByToken`) so a newer session's token can never be coalesced into an older session's request and a settling refresh can never delete a newer session's entry. A self-referential `inFlight` read inside the IIFE's `finally` (TS2454 "used before being assigned", caught by full `tsc -b` with real deps installed) was removed: concurrent callers coalesce on the map entry, so the entry can only be our own while in flight and a plain keyed delete is provably equivalent.

### F03 + F04 — refresh token transport and session overwrite — **fixed**

- F03: `src/api/routers/auth.py:/refresh` now accepts the token from JSON body `{refresh_token}` (preferred, keeps the 7-day credential out of URLs/logs) with transitional query-param fallback; validates length and returns 400 when absent. `src/frontend/src/store/authStore.ts:refreshAccessToken` sends `{refresh_token}` in the body, never `params`.
- F04: `refreshAccessToken` captures `generationAtStart`/`capturedRefreshToken`/`capturedUserId`, coalesces concurrent refreshes per-token (`refreshInFlight` + `refreshInFlightToken`), and discards stale success/failure after epoch or session change. `checkAuth` epoch guard already prevented stale `checkAuth` publishes.
- Evidence: `src/frontend/tests/authStore.test.ts` grows to 18 tests covering body-not-URL, deferred success after logout, deferred success after newer login, stale failure after new login, coalescing for same session, and distinct tokens not coalesced. Backend refresh flows in `test_phase2_security.py` updated to handle transitional body param; all backend phase-2 security tests pass.

### F05 — collaboration permissions revalidation — **addressed**

- Change: `src/api/routers/collab.py` re-validates the token, account active state, and board view access on a bounded interval with a separate short-lived DB session (`create_session_factory`), covering idle receivers; expiry comparison via `exp` from the decoded token causes a policy-violation close when expired.

### F06 — collaboration connections and slow peers — **fixed**

- Change: `src/api/routers/collab.py:ConnectionManager` now caps room size (`MAX_ROOM_SIZE=50`) and bounds slow-peer sends (`SEND_TIMEOUT=3.0` via `asyncio.wait_for` per peer, gathered concurrently); the request-scoped DB session is closed before the long-lived socket loop so idle sockets do not exhaust the pool.

### F07 — voice transcription async offload — **fixed**

- Change: `src/aac_app/services/learning/responses.py:ResponseProcessingMixin` offloads `recognize_from_file` via `asyncio.to_thread` under a bounded `asyncio.Semaphore(2)`, so a slow transcription/model load cannot stall the event loop.

### F08 — strict moderation fail-closed — **fixed**

- Change: `src/aac_app/services/content_safety.py:moderate_output` now fails closed for strict policies: provider errors, empty/garbled/ambiguous verdicts, daily-cap exhaustion, and chunked full-text moderation all return `blocked` (with `"sentinel"` as `matched_terms`); only an explicit `allowed` verdict passes. Text is chunked in 600-char windows so unsafe suffixes are covered.
- Evidence: `tests/test_content_safety.py` strict-open tests converted to strict-closed expectations (cap exhausted and provider errors block); run passes (44 tests).

### F09 — logging redaction — **fixed**

- Change: `src/api/logging_config.py` installs a Loguru core patcher (`_redact_message`/`_redacting_patcher`) masking `groq_api_key|openrouter_api_key|api_key|authorization|password|token` assignments before any sink, disables `diagnose`/`backtrace` and switches to `INFO` in production, and enables rotation (`20 MB`). `src/aac_app/providers/openrouter_provider.py` logs only status/category, not `response.text`; `src/aac_app/services/learning/responses.py` logs AAC transformation shape, not verbatim child messages.
- Evidence: inline probe with a capturing sink verified `sk-supersecret123`/`hunter2` never appear after redaction while `key=***` is written.

### F10 — Groq credential resolution — **fixed**

- Change: `src/aac_app/providers/groq_provider.py` no longer calls `OpenRouterProvider.__init__`; it resolves only `GROQ_API_KEY` via `BaseLLMProvider`, never inheriting `OPENROUTER_API_KEY`. `src/api/deps/providers.py:_effective_groq_key` uses precedence DB → `config.GROQ_API_KEY` → `os.getenv("GROQ_API_KEY")` with trimmed comparison, preventing recreation on env-only configs. `src/api/routers/board_ai.py:_resolve_provider_for_board` also falls through DB → config → process env.

### F11 — request body bounds before parsing — **fixed**

- Change: `src/api/main.py:_BoundedReceiveMiddleware` (pure ASGI) enforces a 12 MB ceiling at the receive-channel level: declared `Content-Length` is rejected immediately; chunked bodies are bounded on the raw `receive` stream with `overflowed`/`response_started` tracking, a bounded drain, and a 413 guarantees even when the app swallows the abort. This applies before multipart parsing so oversized bodies cannot be spooled.
- Evidence: isolated ASGI probe exercised three cases — declared-length oversized → 413 with no app consumption, chunked oversized → 413 with app aborted at the bound (~12.58 MB), normal body → 200 with 5 bytes. `src/api/main.py` compiles; no existing tests regressed.

### F12 — active log rotation — **fixed**

- Change: `src/api/logging_config.py:setup_logging` configures per-sink `rotation="20 MB"` while the per-process log files and age-based cleanup remain, so long-running processes do not grow unboundedly and concurrent processes do not race on a shared path.

### F13 — export/import board links and history — **fixed** (two defects found by regression test in review pass)

- Change: `src/api/routers/export_import.py` second-passes imported boards to remap `linked_board_id` among authorized imports (handling cycles/missing/external refs), and `_board_content_matches` now includes links so retry matching respects navigation.
- Review-pass defect 1 (asymmetric remap): the engine uses `autoflush=False`, so placements created for the last imported board were still pending when the remap queries ran — one direction of a cyclic A→B→A link stayed `None`. `_remap_linked_boards` now flushes before its queries.
- Review-pass defect 2 (retry clones linked boards): retry matching compared source-space link IDs from the export file against local DB IDs — never equal, so every re-import cloned linked boards. `_board_content_matches` now resolves both sides to the target board's *name* via `_source_board_name_map`/`_user_board_name_map` (scoped to the importing user), with unresolvable links collapsing to a conservative "external" marker.
- Evidence: new `tests/test_export_link_remap.py` (7 tests): cyclic A/B remap both directions, external/missing links stay cleared (including forged links to unowned boards), retry import merges instead of cloning, retention preserves today's sentinel meter, `_count_sentinel_today` only counts today, and the admin clear endpoint preserves today's sentinel rows. **Correction (2026-09-13 audit):** this file contains **no** assigned-board link test — the assigned↔assigned case was untested until `tests/test_new_features.py::test_import_preserves_assigned_to_assigned_links` (and the owned→assigned case until `test_import_preserves_owned_to_assigned_links`, N1) were added; the earlier wording overstated that file's coverage.

### F14 — safety log transaction ownership and retention — **fixed** (retention made testable in review pass)

- Change: `src/aac_app/services/content_safety.py:log_event` now takes a deliberate isolated transaction via `get_session()` and ignores the caller's session entirely, so it can never commit or roll back the caller's transaction; it caps `detail` to 200 chars, enforces bounded table retention, and its preservation fix in `src/api/routers/content_safety.py:clear_safety_events` keeps today's `surface="sentinel"` rows (the daily cost meter) when clearing.
- Review pass: retention moved from a function-local constant into module-level `MAX_EVENTS` + `_prune_events(session, max_events)` so the real pruning path is exercisable; `log_event` calls it inside its isolated session. `_prune_events` never deletes today's `sentinel` rows even when they alone exceed the cap (the cap is a hard bound but the meter is protected).
- Evidence: isolated probe created a user, staged a `display_name` change, called `log_event(db=caller_session)`, and rolled back — the staged change was not committed, while the safety event persisted in its own transaction. (The compatibility `db` kwarg this probe used was removed in the N3 pass once every call site was cleaned; the isolation property is unchanged.) `tests/test_export_link_remap.py` exercises `_prune_events` directly: with 6 rows (3 today-sentinel + 3 old chat) and cap 2, only the old chat rows are pruned, 3 sentinel rows remain, and `_count_sentinel_today` still returns 3.

### F15 — CI production gate — **fixed**

- Change: `.github/workflows/ci.yml` renamed `e2e-production` → `e2e-production-gate` with `ENVIRONMENT=production`, no `TESTING=1`, synthetic strong `JWT_SECRET_KEY`, `GROQ_API_KEY`, and `GROQ_MODEL`; polls `/ready` for `"ready":true`; scoping Playwright to `smoke|auth` for that gate. The existing test-mode E2E is preserved as `e2e-production-compat`. Windows packaging step sets `AAC_ASSISTANT_NO_BROWSER=1`.

### F16 — readiness as current liveness — **fixed**

- Change: `src/api/main.py:/ready` now runs a bounded `SELECT 1` via `create_session_factory` + `asyncio.wait_for(..., 2.0)` so runtime DB loss flips `503/database_unavailable` within one poll; provider degradation is surfaced from `get_startup_state()` without paid generations.

### Validation this pass

Environment note (2026-09-10 review pass): this checkout lives on an NTFS3 automount where metadata-heavy operations (npm installs, large deletions) are pathologically slow — `npm ci` hung 14+ minutes with zero output there, and one interrupted install left `node_modules` broken. The full frontend gate was therefore run from an identical ext4 mirror (`~/aac_fe_check`: same package.json/package-lock.json/tsconfigs/vitest+eslint configs, `src/`, `tests/`, `e2e/`, index.html) with `npm ci` completing in 2s; the repo's `node_modules` is now a symlink to that mirror. The earlier "typecheck clean via skipLibCheck" claim was replaced: with real deps installed, full `tsc -b` found a genuine TS2454 in authStore (fixed above); the remaining `src/pages/*` implicit-any diagnostics reported by the audit are pre-existing and untouched by this task.

| Check | Outcome |
| --- | --- |
| Ruff `src tests scripts` | All checks passed |
| `python -m compileall -q src scripts` | Passed |
| Frontend vitest (102 suites, 852 tests) | 102 passed, 852 passed |
| Backend focused run: `test_export_link_remap.py`, `test_content_safety.py`, `test_phase2_security.py`, `test_writes_durable_before_response.py` | 85 passed, 0 failures |
| Frontend typecheck (`tsc -b --noEmit` with real deps) | Clean after fixing the authStore TS2454; no new diagnostics |
| Frontend lint (`eslint src tests --max-warnings=0`) | Clean |
| Frontend production build (`vite build`) | Succeeds (vendor chunks emitted) |
| CI workflow validity (`yaml.safe_load` + env inspection) | `e2e-production-gate` production env verified: no TESTING, no demo seeding, `E2E_PROVISION_VIA_API=1`, synthetic keys; `e2e-production-compat` retains test-mode E2E |
| `git diff --check` | Clean |
| `offlinePersistence.test.ts` (real module) | 9 passed |
| JWT prod probe (isolated via `load_settings(tmp)` with dotenv `ENVIRONMENT=production`) | Short key rejected; env-over-dotenv respected |
| Request-body probe (ASGI, declared-length + chunked 12 MB+) | Declared 413/no app bytes; chunked 413/aborted at 12.58 MB |
| Safety-log probe (isolated DB, synthetic user, staged change + `log_event(db=...)` + rollback) | Staged change not committed; event persisted |
| Full suites / `verify_pr.py` | Not run — per AGENTS.md requires explicit authorization |
| Live production smoke / Windows rehearsal / human beta | Still blocked (intentionally) — not executed this pass |

## Acceptance-test and evidence pass — 2026-09-10 (second)

### New acceptance regression coverage — `tests/test_acceptance_gaps.py` (9 tests, all passing)

- **F05 (collab revalidation)**: three tests open a real WebSocket via TestClient, apply the security change in a **separate committed session** (deactivation, `security_version` bump, board-assignment removal), advance a controllable `time.monotonic` clock past the 60s revalidation interval, and assert the server closes the idle receiver with 1008. The clock test initially exposed that the test helper minted tokens without the `sec_ver` claim real logins carry — the helper now mirrors the auth router exactly. (A first attempt hung because the fake clock recursed into the patched `time.monotonic`; the real function is captured at import time.)
- **F06**: (a) a `get_db` override wrapping the request session with a `close` spy proves the handler closes the request-scoped session **before** entering the socket loop while the socket remains registered in the room; (b) a stalled peer (`send_json` sleeping 30s) with `SEND_TIMEOUT=0.2` is reaped by `broadcast` while the healthy peer receives the message — broadcast returns long before the stalled send would.
- **F07**: with the production `_voice_semaphore()` + `asyncio.to_thread` path, a simulated blocking transcription occupying a worker thread does not prevent concurrent loop tasks from completing (bounded waits throughout; no model download). A second test pins the worker-owned temp-copy contract (copy survives, original upload never deleted).
- **F13**: export with 137 learning sessions carries exactly 100, `meta.truncated=true`, `meta.total_learning_sessions=137`, and the newest session is retained; at exactly 100 nothing is truncated. This test exposed a real determinism defect — sessions created in one transaction share `started_at`, so "latest 100" was arbitrary — fixed by an `id DESC` tiebreaker in the export query.

Related: `tests/conftest.py` gained the shared `collab_client` fixture (moved from `test_collab_ws.py`, which still passes: 25 tests).

### Dependency audits (AGENTS.md required gates; registry reachable again)

| Gate | Outcome |
| --- | --- |
| `scripts/check_dependency_usage.py` | Passed |
| `pip-audit --requirement requirements.txt --strict` (production) | No known vulnerabilities |
| `pip-audit --local --strict` (all groups) | No known vulnerabilities |
| `npm audit --omit=dev --audit-level=moderate` (production) | 0 vulnerabilities |
| `npm audit --audit-level=high` (development tree) | 4 advisories (3 moderate, 1 high) — **resolved in the reviewed lockfile upgrade below** |

### Production-mode smoke (isolated; real `.env` + real dev DB contents, copied — originals untouched)

Server: `uvicorn src.api.main:app` with `ENVIRONMENT=production`, `TESTING` unset, `DATA_DIR`/`LOGS_DIR` pointed at a temp copy of `data/aac_assistant.db` (gitignored dev DB with admin1 + a persisted Groq key), port 8087.

| Evidence | Result |
| --- | --- |
| `/api/health` | 200 |
| `/ready` | `"ready": true`, 4/4 providers, per-provider metrics exposed |
| Production active | `TESTING` absent → limiter enabled (below); log line "Serving URL" from prod startup; secret validation ran against the 64-char dotenv key |
| F15 rate limit | Burst of token requests: 401s → account-lockout 403s (separate lockout service, audited) → **429 Too Many Requests** once the 10/min window filled — limiter demonstrably active and recoverable after the window |
| F11 body bound (end-to-end) | 13 MB declared-length JSON POST → **413 Content Too Large** in the server log |
| F03 refresh transport | `POST /api/auth/refresh` with JSON body → 200, "Access token refreshed" logged; no token in any URL |
| F10 model listing | `GET /api/settings/ai/models/groq` with request-scoped `X-Groq-API-Key` → 200 with real model list (`openai/gpt-oss-20b`, …) — request-header precedence works against the live provider |
| F09 log hygiene | `grep` for the actual Groq API key and JWT secret across stdout log + both file sinks: **0 occurrences** |
| SPA serving | `/` 200 (title "AAC Assistant"), `/login` SPA fallback 200, hashed `/assets/*.js` 200 |
| Live Groq (named spec) | `groq-verify.spec.ts` › **"learning: starts a session and receives a real Groq question" PASSED** against the production server — real Groq generation, provider badge "AI: Groq", non-empty choices |
| Settings UI (named spec) | `groq-verify.spec.ts` › "settings UI configures Groq and reports healthy" PASSED on rerun (first run failed only because my rate-limit probe had locked `admin1`; lockout cleared in the disposable DB copy, admin1 login re-verified 200) |
| Teardown | Server killed; port closed; no background tasks left; disposable smoke dir remains in `/tmp` only |

Still open (unchanged, external gates): Windows artifact/update/rollback rehearsal; human beta/privacy/accessibility review; GitHub Actions green run for the new CI gates; `verify_pr.py` full run.

### Reviewed dev-tree npm advisory upgrade — 2026-09-10

The four tracked advisories were resolved with a narrow, reviewed lockfile change (no broad `npm audit fix`, per AGENTS.md):

- **vitest / @vitest/coverage-v8 `^4.1.10` → `^4.1.11`** — picks up GHSA-82fw-gwwq-j7x9 / CVE-2026-84373 (`@vitest/mocker` path traversal, fixed in 4.1.11). In-range patch bump of the existing direct dev dependency.
- **`overrides: { "js-yaml": "^4.3.2" }`** — resolves GHSA-2883-xcg3-v3hh / CVE-2026-84375 (CPU DoS via empty YAML merge keys, fixed in 4.3.2). `js-yaml` is transitive (via `@eslint/eslintrc` and `cosmiconfig`, both requiring `^4.1.0`, which 4.3.2 satisfies), so an `overrides` entry — not a direct devDependency — is the correct mechanism.
- Lockfile delta: 140 lines, confined to the two upgraded package sub-trees; both manifests re-validated as JSON.
- Post-upgrade gate (identical mirror, real deps): **npm audit 0 vulnerabilities in both production and full dev trees**; vitest **102 suites / 852 tests passing**; `tsc -b --noEmit` clean; `eslint --max-warnings=0` clean; `vite build` succeeds. Focused authStore/offlinePersistence suites re-run in-repo (27 passing).

Note: the system npm is 9.2.0, which crashes on this lockfile with arborist `edgesOut` errors; the upgrade was performed with `npx npm@11` and the repository's CI (Node 20+/newer npm) is unaffected.

## Follow-up pass — 2026-09-11 (D1–D13)

Commit `bb0c4a0` on `fix/pagination-n1-e2e` ("Fix 13 follow-up defects D1–D13 from F01–F16 hardening pass").
Independent re-verification of that commit (recorded in `PROMPT_2.md` §4) found 9 of 13 items fully verified and
4 partial/incorrect — the partials became the N-item backlog below.

| Item | Disposition | Where / evidence |
| --- | --- | --- |
| D1 log redactor | **partial → N2** | `src/api/logging_config.py`: JSON pair, `Bearer`, `X-*-API-Key`, bare `key=value` patterns. Probe: all shapes masked. Re-verified as incomplete (`***` bypass, unquoted JSON brace-eating). |
| D2 sentinel cost meter | **fixed** | `models/content_safety.py` + `schema.py` (`call_count` column + migration) + `content_safety.py::moderate_output` (`spent = len(chunks)`). Probe: ~5k-char text → 9 `generate()` calls → one row with `call_count=9` (was 1). |
| D3 body-bound 413 semantics | **fixed (code), untested → N10** | `src/api/main.py`: two `send_413` sites collapsed into `resolve_overflow()`; post-response overflow raises to abort the connection. No regression test existed. |
| D4 collab revalidation | **fixed, dead residue → N8** | `src/api/routers/collab.py`: top-level imports, per-iteration `token_exp` check, 403→1008 / transient 3-strike→1011 / policy→1011. Unreachable `except HTTPException: raise` left behind. |
| D5 refresh query fallback | **verified, comment moved → N11** | `AAC_REFRESH_ALLOW_QUERY_FALLBACK=False` (production), deprecation warning, dated removal note in `docs/SECURITY_ARCHITECTURE.md`; refresh tests migrated to body transport. |
| D6 assigned↔assigned links | **partial → N1** | `export_import.py` populates the shared map from the assigned section and preserves `assigned_by`. Owned→assigned links still dropped. |
| D7 truncation surfacing | **partial → N6/N9** | API returns counts + `truncated`/`total_learning_sessions`; `DataManagementTab` shows an `importTruncated` warning toast. Counts were input lengths, and the UI branch had no test. |
| D8 voice copy off the loop | **fixed** | `services/learning/responses.py`: copy moved inside the semaphore-guarded `to_thread` section. |
| D9 provider init dedup | **partial → N4** | `OpenRouterProvider._resolve_api_key` hook added, but `_api_key_env` was kept alongside it (dead branch). |
| D10 shared Groq key | **fixed** | `deps/providers.py::_effective_groq_key` strips once and is used by `board_ai`; padded keys no longer thrash the singleton. |
| D11 retention throttle | **partial → N3** | `_PRUNE_EVERY_N`/`_PRUNE_THROTTLE_SECONDS` throttle works; the claimed `db=` call-site cleanup had not happened (21 remained). |
| D12 stale login/setup guard | **verified, gaps → N5/N9** | login/setup `catch` paths epoch-guarded. `emptyAuthState` omitted `isLoading`, and no test covered the branch. |
| D13 test-file hygiene | **verified** | `tests/test_export_link_remap.py` tracked and committed; unused import dropped from `test_collab_ws.py`. |

## Follow-up pass — 2026-09-13 (N1–N12)

Scope: the twelve residual defects recorded in `PROMPT_2.md`, implemented in the working tree on
`fix/pagination-n1-e2e` (uncommitted at the time of writing; the `D1–D13` pass above is commit `bb0c4a0`).
Net change is a simplification (dead keyword, dead handler, duplicate comment, alias tangle and duplicated
remap passes all removed) plus regression coverage for branches that previously had none. No `.env`/DB/
auth-artifact mutation, no new dependency, no Windows launcher/packaging change, no full-suite run.

### Corrective note (found during this pass)

An intermediate working-tree edit had removed `db=` arguments at call sites **beyond** the
`content_safety.log_event` scope. That broke `_PredictionContext(...)` (its `db` is a required
keyword-only parameter) and silently changed session ownership for analytics/achievement calls. The
affected files (`learning/responses.py`, `learning/session.py`, `learning/summaries.py`,
`prediction_service.py`, `routers/analytics.py`, `routers/learning.py`) were restored to HEAD and the
removal re-applied only to the 17 `content_safety.log_event` call sites.

### Dispositions

- **N1 owned→assigned board links — fixed.** `src/api/routers/export_import.py::import_data` now runs a
  single combined `_remap_linked_boards` pass over owned **and** assigned sources once both sections exist
  (the first pass inside `_import_boards` cannot resolve an owned board whose target arrives as an assigned
  board). New API-level test `tests/test_new_features.py::test_import_preserves_owned_to_assigned_links` plus
  `test_import_preserves_assigned_to_assigned_links` (D6 guard). **Evidence:** with HEAD's `export_import.py`
  restored via `git stash`, the owned→assigned test fails (`assert None == 2` on the placement's
  `linked_board_id`); it passes with the fix.
- **N2 redactor bypass and brace-eating — fixed.** `src/api/logging_config.py::_redact_message`: the
  double-mask guard now compares the *exact* masked value (so a real secret containing `***` is no longer
  skipped), the quoted-pair pattern covers single-quoted Python-repr pairs and unquoted JSON scalars
  (`123`/`true`/`null`) without consuming structural braces, and the bare pattern accepts single quotes.
  New `TestRedactMessage` in `tests/test_logging_config.py` (15 tests in the file). **Evidence:** four cases
  fail against HEAD's `logging_config.py` (single-quoted password, `password is <secret>`,
  `foo***bar` secret, unquoted JSON `{"token": 12345678}` → `{token=***`), all pass now.
- **N3 dead `db=` arguments and compat kwarg — fixed.** 17 `db=` arguments removed at every
  `content_safety.log_event` call site (learning questions/responses/session/summaries, prediction service,
  analytics/board-AI/learning routers); the compat `db` parameter was then **deleted** from `log_event`
  after a repo-wide search proved no production, test, script or dynamic caller. **Evidence:**
  `grep -rn "log_event(" src -A 8 | grep db=` now matches only `audit_service.log_event`'s own signature;
  the cleaned call sites' tests are green.
- **N4 dual provider key mechanisms — fixed.** `_api_key_env` deleted; `OpenRouterProvider.__init__` always
  calls `self._resolve_api_key(api_key)` and `GroqProvider` overrides only that hook. **Evidence:** key matrix
  probe — neither → `None`/`None`; `GROQ_API_KEY` only → Groq resolves it, OpenRouter does not; both → each
  resolves its own; `OPENROUTER_API_KEY` only → OpenRouter resolves it, Groq stays `None` (no cross-provider
  inheritance); `grep -rn _api_key_env src tests` → none. `tests/test_groq_provider.py` green.
- **N5 `isLoading` ownership — fixed.** `emptyAuthState()` now includes `isLoading: false`, and a
  `loadingOwnerEpoch` tracks which operation owns the shared spinner so a stale login/setup failure clears
  only a spinner no newer loading operation owns. **Evidence:** two new `authStore.test.ts` cases fail against
  HEAD (`logout interrupts login`, `non-loading checkAuth invalidates a failed login`) and pass now; 22
  authStore tests pass in total.
- **N6 import counts report outcomes — fixed.** `import_data` snapshots owned-board/placement/session counts
  before the import, reports `boards_created`/`boards_merged`/`symbols_added`/`learning_history_added` after
  the single commit, and keeps `boards`/`symbols`/`learning_history` as documented input-length aliases (the
  UI uses `learning_history` for the truncation notice). The redundant post-commit `flush` and the tangled
  alias fallback were removed. **Evidence:** `test_import_reports_outcome_counts_not_input_lengths` asserts
  `2/0` on first import and `0/2` on IDEMPOTENT retry.
- **N7 `assigned_by` validation — fixed.** Shape validation moved into `_validate_import_payload`
  (malformed shapes — dict/list/float — 400 before any write); `_import_assigned_boards` honors the value
  only when `type(x) is int and x > 0` and the user exists, so bools (int subclass), strings and
  non-positive values fall back to the importer instead of being stored as user id 1.
  **Note:** `PROMPT_2.md` states both "unknown/non-positive assigners fall back" and "invalid shape → 400";
  this implementation follows the explicit acceptance list (unusable scalars fall back so a signed recovery
  import is never rejected over assigner metadata; structurally malformed shapes are rejected).
  **Evidence:** `test_import_handles_invalid_assigned_by_shapes` fails against HEAD (`assert 200 == 400`) and
  the bool case would have stored user id 1; passes now with the assigner registered first so
  `student_id != 1`.
- **N8 dead collab handler — fixed.** The unreachable `except HTTPException: raise` was removed in the D4
  pass; this pass replaced its misleading residual comment with the actual transient-failure rationale.
  **Evidence:** `tests/test_collab_ws.py` + the F05 acceptance tests are green.
- **N9 untested new branches — fixed.** `DataManagementTab.test.tsx` gained a truncated-import test (the
  i18n mock now interpolates `{{shown}}`/`{{total}}` and defines `importTruncated`), and
  `authStore.test.ts` gained the N5 stale-failure cases (login→login and setup→login). **Evidence:** 29
  Vitest tests pass across the two files (22 + 7).
- **N10 abort-after-response test — fixed.** New ASGI-level tests in `tests/test_acceptance_gaps.py`
  (`TestBoundedBodyMiddleware`): declared-length 413 without the app running, chunked 413, and an
  abort-swallowing app that starts a 200 before consuming an oversized chunk. To make "no clean 200" true
  rather than aspirational, `src/api/main.py::_BoundedReceiveMiddleware` now **suppresses** the remaining
  response messages once overflow is known and lets `resolve_overflow` abort the connection.
  **Evidence:** against HEAD's `main.py` the swallowing-app test fails because the app's success body is
  delivered (`response.body` present); with the fix the connection aborts and no body is delivered.
- **N11 config comment placement — fixed.** `AAC_REFRESH_ALLOW_QUERY_FALLBACK` moved next to the JWT/auth
  settings with its own dated comment; the duplicated/orphaned password header above the `AAC_SEED_*` fields
  was removed. **Evidence:** `git diff HEAD -- src/config.py` shows a pure move; `compileall` and the
  settings tests are green.
- **N12 micro-residues — fixed.** `REVALIDATE_INTERVAL`/`REVALIDATE_MAX_FAILURES` are module-level in
  `collab.py` (test-configurable) with the D4 context comments restored; `log_event` coerces `call_count`
  defensively (`try/except` → 1) so a non-numeric caller cannot silently drop the event; the `db` kwarg
  removal is documented in the docstring; `_prune_events` documents that direct callers bypass the throttle.
  **Evidence:** `ruff` clean, content-safety/collab/acceptance tests green.

### Validation this pass (2026-09-13)

| Check | Outcome |
| --- | --- |
| `ruff check src tests scripts` | All checks passed |
| `python -m compileall -q src scripts` | Passed |
| `git diff --check` | Clean |
| Backend named files: `test_new_features.py`, `test_export_link_remap.py`, `test_acceptance_gaps.py`, `test_logging_config.py`, `test_content_safety.py`, `test_collab_ws.py`, `test_phase2_security.py`, `test_password_reset_security.py` | 152 passed, 0 failures |
| Additional affected files: `test_config_pydantic.py`, `test_groq_provider.py`, `test_analytics_api.py`, `test_prediction_service.py`, `test_symbol_analytics.py`, `test_board_ai_routes.py`, `test_learning_routes_coverage.py`, `test_student_summaries.py`, `test_learning_persistence.py` | All green |
| Frontend `npm run typecheck` / `npm run lint` | Clean |
| Frontend `npx vitest run tests/authStore.test.ts tests/DataManagementTab.test.tsx` | 29 passed (2 files) |
| Frontend production build (`npm run build`) | Succeeds; bundle budgets reported (largest JS 396.7 kB / 450 kB, CSS 139.8 kB / 150 kB) |
| Fail-before/pass-after probes (temporary `git stash` of the pre-fix file) | N1 (`None == 2`), N2 (4 redactor cases), N5 (2 tests), N7 (`200 == 400`), N10 (success body delivered) |
| Full suites / `verify_pr.py` | Not run — AGENTS.md requires explicit authorization |
| Live production smoke · live-Groq run · Windows artifact/update/rollback rehearsal · human beta/privacy/accessibility review | Still **open** external gates; no sign-off claimed |

## Verification pass — 2026-09-13 (doc vs. code, claims re-checked)

Independent re-check of every claim in this document against the working tree (not against the earlier
reports), on top of the N1–N12 pass above. Method: read the production code paths the document names,
then run isolated probes for the claims that are behavioral rather than structural. Findings and fixes:

### Claims verified as genuinely implemented in code

| Claim | Re-check | Result |
| --- | --- | --- |
| F01 production JWT validation | 5 isolated subprocess probes: short key, whitespace-only key, placeholder → `ValueError` at `src/aac_app/utils/jwt_utils.py` import; valid 48-char environment-only key → token minted with **no** dotenv write (`.env` md5 unchanged before/after); `development` + short key stays tolerant | Verified |
| F02 offline persistence | `offlinePersistence.ts` allowlist + sensitive-key/header/param sanitizer; `api.ts::persistQueue` removes non-durable items from the replay queue; `offlineStore.persistConflicts` re-sanitizes before every write; hydration re-validates queue **and** conflict entries. 46 frontend tests green (`offlinePersistence` + `api` + `offlineStore`) | Verified (wording corrected above) |
| F03/F05 refresh transport | `auth.py::refresh_access_token` reads the JSON body first; the query fallback requires `AAC_REFRESH_ALLOW_QUERY_FALLBACK` and, in production, an explicit truthy string — absence fails closed. Frontend sends `{refresh_token}` in the body | Verified |
| F04 refresh/login staleness | `authStore.ts` epoch guards on refresh success/failure and on login/setup success/failure; per-token coalescing map. 22 authStore tests green | Verified |
| F05 collab revalidation | `collab.py`: per-iteration `token_exp` compare, 60 s revalidation with a fresh short-lived session checking active state, `security_version`/`credentials_changed_at`, board existence and `require_board_view_access`; 403 → 1008, transient → 3-strike → 1011 | Verified |
| F06 collab bounds | `MAX_ROOM_SIZE = 50`, `SEND_TIMEOUT = 3.0` gathered concurrently, request session closed before the socket loop, room membership dropped on disconnect | Verified |
| F07 voice offload | `responses.py`: copy + `recognize_from_file` inside `asyncio.to_thread` under `_voice_semaphore()`; worker owns and deletes its copy | Verified |
| F08 strict moderation | `moderate_output` returns blocked for provider error/timeout, empty or ambiguous verdict, and cap exhaustion; full text moderated in 600-char chunks; deterministic non-AI AAC paths untouched | Verified (docstring corrected — see below) |
| F09 log hygiene | `logging_config.py`: `diagnose`/`backtrace` off and `INFO` in production, 20 MB rotation, redacting patcher; `openrouter_provider` logs status/category only; learning logs counts/shape, not verbatim child text | Verified |
| F10 Groq credentials | `_effective_groq_key` strips once (DB → config → env), is used by both `deps/providers.py` and `board_ai.py`, and never consults `OPENROUTER_API_KEY`; `GroqProvider` overrides only `_resolve_api_key`; explicit-model requirement lives in `generate`/`generate_sync` | Verified |
| F11 body bound | `_BoundedReceiveMiddleware` declared-length 413, chunked bound, suppressed late-overflow body + connection abort; reverse-proxy equivalents documented in `docs/SECURITY_ARCHITECTURE.md` (nginx `client_max_body_size 12m`, Caddy `request_body max_size 12MB`) | Verified |
| F12 log rotation | Per-process file names with `rotation="20 MB"` on all three sinks | Verified |
| F13 export/import + truncation | Second-pass link remap (now a single combined pass, N1), name-based retry matching, `linked_board_id=None` cleared for external refs, latest-100 learning history with `id DESC` tiebreaker, `meta.truncated`/`total_learning_sessions` | Verified |
| F14 safety-log isolation + meter | `log_event` writes through its own short-lived session, 200-char detail cap, `MAX_EVENTS` retention that never prunes today's sentinel rows, throttled per-event pruning, clear endpoint preserves today's sentinel rows, meter sums `call_count` | Verified |
| F15 CI production gate | `e2e-production-gate` runs with `ENVIRONMENT=production` (no `TESTING`), polls `/ready`, asserts Groq is the configured provider, and proves a real 429 from the login limiter; test-mode E2E preserved separately; packaging step sets `AAC_ASSISTANT_NO_BROWSER=1` | Verified |
| F16 readiness liveness | `/ready` runs a bounded (2 s) `SELECT 1` through `create_session_factory` and returns 503 `database_unavailable` on failure; provider degradation reported from startup state without paid calls. Probe code is absent at baseline `7c2f9f0` and present at HEAD | Verified |
| D2/D11/N-item residues | `call_count` column + schema migration present; throttle counters present; `MAX_EVENT`/`_prune_events` documented; no `_api_key_env` remains; no `log_event` caller passes `db=` | Verified |

### Defect found and fixed by this audit

- **Stale `moderate_output` docstring (`src/aac_app/services/content_safety.py`).** The docstring still
described the pre-F08 fail-open contract ("returns an allowed verdict when … the daily cap is exhausted,
the LLM is unavailable") while the code correctly fails closed. Rewritten to state the strict
fail-closed contract, the 600-char chunking, the `call_count` cost meter, and that deterministic non-AI
AAC communication is unaffected. Code behavior unchanged; `ruff`/`compileall` clean.

### Acceptance criteria that had no test — closed in this pass

| Finding | Criterion that was unverified | New test |
| --- | --- | --- |
| F03 / D5 | Query transport rejected by default; opt-in accepted **and** deprecation logged without the token; production fails closed even when the flag is set fuzzily | `tests/test_phase2_security.py` — `test_refresh_query_transport_is_rejected_by_default`, `test_refresh_query_transport_opt_in_logs_deprecation`, `test_refresh_query_transport_fails_closed_in_production` |
| D2 / N2 | Meter increment equals spent chunk calls; cap enforced for long texts; blocked chunk meters only the calls actually spent | `tests/test_content_safety.py` — `test_moderate_output_meter_charges_every_chunk_call`, `test_moderate_output_meter_counts_only_spent_calls_when_blocked` |
| F10 | Credential matrix (DB-only / config-only / env-only / absent / unrelated-provider-only) and singleton reuse vs. recreation, including padded keys | `tests/test_groq_provider.py` — `TestEffectiveGroqKey` (2 tests), `TestGroqProviderSingleton` (1 test) |
| F16 | Runtime DB loss after startup produces the documented non-ready response | `tests/test_startup_warmup.py` — `test_ready_reports_database_loss_after_startup` |
| F06 | Connection counts are bounded per room and disconnect restores them | `tests/test_acceptance_gaps.py` — `test_room_cap_rejects_excess_connections` |

### Validation of this pass

| Check | Outcome |
| --- | --- |
| F01 isolated subprocess probes (short / whitespace / placeholder / valid env-only / development) | Rejected, rejected, rejected, minted, minted; `.env` md5 unchanged |
| `ruff check src tests scripts` · `compileall -q src scripts` | Clean |
| `pytest tests/test_startup_warmup.py tests/test_content_safety.py tests/test_groq_provider.py tests/test_acceptance_gaps.py tests/test_phase2_security.py` | 106 passed |
| `pytest tests/test_export_link_remap.py tests/test_logging_config.py tests/test_new_features.py tests/test_collab_ws.py tests/test_password_reset_security.py` | All green (see the N-pass table above) |
| `tsc -b --noEmit` · `eslint` · `vitest` (`offlinePersistence` + `api` + `offlineStore`) | Clean · clean · 46 passed |
| Full suites / `verify_pr.py` · live-Groq run · Windows rehearsal · human beta/privacy review | Still **open** (not executed; no sign-off claimed) |

## D1–D13 acceptance re-check — 2026-09-13 (same doc-vs-code method)

The F-pass above re-checked every F-item claim against the code. This pass applied the
same method to the **D1–D13** acceptance criteria in `PROMPT_1.md` §5, auditing each
against the actual implementation and tests rather than the pass-notes table.

### Re-check result

| D | Acceptance criterion | Verdict |
| --- | --- | --- |
| D1 | JSON/Bearer/header/bare secret shapes masked; 2000-char truncation kept | **Covered** — `tests/test_logging_config.py::TestRedactMessage` (9 parametrized shapes + asterisk-bypass, unquoted-JSON, double-mask, truncation) |
| D2 | Multi-chunk meter increment == spent `generate()` calls | **Covered** — `test_moderate_output_meter_charges_every_chunk_call`, `…_counts_only_spent_calls_when_blocked` |
| D3 | Declared-length 413, chunked 413, abort-swallowing app cannot deliver a clean 200 | **Covered** — `TestBoundedBodyMiddleware` (3 tests) |
| D4 | 403-close, transient-failure tolerance **then** close, expiry enforced without the 60s wait | **Gap → closed** (see below) |
| D5 | Query transport rejected by default / opt-in deprecation / production fail-closed | **Covered** — 3 tests in `test_phase2_security.py` |
| D6 | Assigned↔assigned links preserved; forged-external links cleared | **Covered** — `test_import_preserves_assigned_to_assigned_links` + `test_export_link_remap.py` forged-external test |
| D7 | 137-session export → **import result** reports truncated/total; UI notice | **Gap → closed** (API half was untested; UI test existed) |
| D8 | Slow-copy + heartbeat concurrency on the **production** path | **Gap → closed** (the existing `test_worker_temp_copy_contract` hand-rolled the copy instead of calling `process_response`) |
| D9 | Provider `__init__` dedup + matrix | **Covered** — `test_groq_provider.py`; + 1 refactor guard added (see below) |
| D10 | Padded DB key resolves identically on both paths, singleton reused | **Covered** — `TestGroqProviderSingleton::test_reuses_unchanged_configuration_and_recreates_on_change` |
| D11 | Retention bounded under spam; blocked-label flood shows bounded per-event query count | **Gap → closed** (throttle existed; no test measured it) |
| D12 | Deferred failure after a newer login keeps `error: null` | **Covered** — `authStore.test.ts` `(N5/D12)` login + setup tests |
| D13 | Claimed F13 test file tracked and committed | **Covered** — `tests/test_export_link_remap.py` tracked in `bb0c4a0` |

### Three defects found by the audit

1. **D4 had no coverage for two of its three acceptance behaviours.** The tolerance
   threshold (`REVALIDATE_MAX_FAILURES`), and the per-iteration token-expiry check, had no
   test at all. The existing revocation tests only exercise the 403 path.
2. **D7's import-side truncation reporting was untested.** `test_acceptance_gaps.py` covered
   the *export* side (`meta.truncated`), but nothing asserted the *import* result carries
   `truncated` / `total_learning_sessions` back to the user — the actual D7 requirement.
3. **D8's test did not exercise production code.** `test_worker_temp_copy_contract`
   re-implemented the copy inline, so it would still pass if the production copy moved back
   onto the event loop. It also asserted nothing about which thread ran the copy.

### Acceptance tests added (8)

| Item | New test | Fail-before evidence (pre-fix file from `133d790`) |
| --- | --- | --- |
| D4 | `test_transient_failure_is_tolerated_then_revocation_still_closes` | FAILED (`injected` never incremented — the pre-fix loop imports `_csf` per-iteration, so no interposition) |
| D4 | `test_consecutive_failures_close_after_threshold` | FAILED (pre-fix `except Exception: pass` never closes) |
| D4 | `test_expired_token_closes_without_waiting_for_revalidation` | Passes pre-fix only after ~59s; now asserts `elapsed < 5.0`, which the 60s-tick-only check cannot satisfy |
| D7 | `test_import_reports_truncated_export_source` | FAILED (`KeyError: 'truncated'` — pre-fix returned a bare `ok` response) |
| D8 | `test_production_voice_copy_runs_off_the_event_loop` | FAILED (`TimeoutError` — the pre-fix copy blocks the loop) |
| D11 | `test_log_event_retention_is_throttled_not_per_event` | FAILED (`AttributeError: _prune_calls` — no throttle existed) |
| D11 | `test_log_event_retention_queries_are_bounded_under_flood` | FAILED (same; pre-fix ran COUNT(*)+DELETE per event) |
| D11 | `test_log_event_prunes_again_after_the_throttle_window` | FAILED (same) |
| D9 | `test_parent_provider_still_resolves_its_own_env_key` | Passes pre-fix (D9 was a behavior-preserving refactor) — a guard against the shared `_resolve_api_key` hook dropping OpenRouter's own env resolution |

The D8 test stubs `_transcribe_voice_response`, so no speech model is loaded/downloaded.
The D4 tests reuse the `_FakeClock` controllable-clock pattern and a separate committed
session for state changes.

### Validation of the D re-check

| Check | Outcome |
| --- | --- |
| `pytest tests/test_acceptance_gaps.py` (3 consecutive runs) | 17 passed, stable across runs |
| `pytest tests/test_content_safety.py` · `test_new_features.py` · `test_phase2_security.py` | 48 · 20 · 24 passed |
| `pytest tests/test_export_link_remap.py tests/test_collab_ws.py tests/test_logging_config.py` | 47 passed |
| `pytest tests/test_groq_provider.py` | 12 passed |
| Fail-before probes (4 production files restored from `133d790`, then restored to the working tree) | 6 of 7 new tests fail pre-fix; the expiry test's timing assertion is the discriminator |
| `ruff check src tests scripts` · `compileall -q src scripts` · `git diff --check` | Clean · clean · clean |
| Index hygiene after the fail-before checkouts | Verified: `git diff --cached` empty, all 27 modified files unstaged, working tree matches the pre-checkout backups byte-for-byte |
| Full suites / `verify_pr.py` · live-Groq run · Windows rehearsal · human beta/privacy review | Still **open** (not executed; no sign-off claimed) |

## N1–N12 acceptance re-check — 2026-09-13 (same doc-vs-code method)

The D pass above re-checked the D1–D13 acceptance criteria in `PROMPT_1.md` §5. This pass
applied the same method to the **N1–N12** backlog in `PROMPT_2.md` §5, verifying each
acceptance claim against the code and tests rather than the N-pass table.

### Re-check result

| N | Acceptance criterion | Verdict |
| --- | --- | --- |
| N1 | owned→assigned **and** assigned→owned remap regression test; 7 link tests + retry-merge green | **Covered** — `test_import_preserves_owned_to_assigned_links` (asserts both directions), `test_import_preserves_assigned_to_assigned_links`; `test_export_link_remap.py` has the 7 claimed tests |
| N2 | `***`-substring and unquoted-JSON probes mask; D1 shapes still masked | **Covered** — `test_secret_containing_asterisks_is_still_masked`, `test_unquoted_json_scalars_keep_their_structure`, 9-shape parametrize |
| N3 | `db=` call sites gone / justified; compat kwarg removed | **Code verified, guard missing → closed** (see below). The 5 remaining `db=` matches are `audit_service.log_event`, a different function that genuinely owns its session |
| N4 | one resolution hook, `_api_key_env` deleted, matrix green | **Covered** — no `_api_key_env` anywhere in `src`/`tests`; precedence, cross-provider isolation, and parent-resolution tests green |
| N5 | logout-during-login leaves `isLoading: false`; stale failure keeps `error: null` | **Covered** — the two `(N5)` specs plus the `(N5/D12)` stale-login spec |
| N6 | retry asserts `boards_created == 0` / `boards_merged == N`; first import asserts created counts | **Covered** — `test_import_reports_outcome_counts_not_input_lengths` |
| N7 | malformed shapes → 400; `true`/`"1"`/`-5`/`0` → importer fallback; valid assigner preserved | **Covered** — `test_import_handles_invalid_assigned_by_shapes` exercises all three branches |
| N8 | collab + F05 tests green, no behavior change | **Covered** — the unreachable outer handler is gone; `test_collab_ws.py` + acceptance-gaps F05 tests green |
| N9 | truncated-toast spec and stale-error specs | **Covered** — `DataManagementTab` `warns when the import source was a truncated export`; authStore `(N5/D12)` specs |
| N10 | ASGI test: abort-swallowing app cannot deliver a clean 200 | **Covered** — `test_abort_swallowing_app_cannot_deliver_a_clean_success` (fail-before shown in the D pass) |
| N11 | comment move only; compileall/settings green | **Covered** — `AAC_REFRESH_ALLOW_QUERY_FALLBACK` sits directly after `JWT_SECRET_KEY`; the passwords comment appears exactly once (line 186) |
| N12 | module-level constants, defensive `call_count`, prune docstring, ruff/compileall | **Code verified, coercion untested → closed** (see below) |

### Two defects found by the audit

1. **N3's removal had no regression guard.** The acceptance was a one-off `grep`; nothing
   stopped a future edit from re-adding the `db` compat kwarg and restoring the
   mixed-transaction ownership contract F14 removed.
2. **N12's `call_count` coercion was validated with `ruff` only.** The pass notes describe the
   behavior change (non-numeric input must not lose the event) but no test asserted it — and
   pre-fix `int("not-a-number")` raised inside the best-effort log, silently dropping the row.

### Acceptance tests added (2)

| Item | New test | Fail-before evidence (`bb0c4a0` `content_safety.py`) |
| --- | --- | --- |
| N3 | `test_log_event_has_no_session_parameter` | FAILED — pre-fix signature still carried `db` |
| N12 | `test_log_event_never_loses_an_event_on_bad_call_count` | FAILED — 4 rows persisted for 5 calls; the `"not-a-number"` event was dropped |

### Notes on instruction-vs-implementation placement

- **N1** asked for the owned→assigned regression test in `tests/test_export_link_remap.py`; it
  lives in `tests/test_new_features.py` beside the other import round-trip tests. Coverage is
  complete and both link directions are asserted; only the file differs.
- **N3** asked for `grep … | grep -c "db="` → 0. Its final count is 5, all of them
  `src/aac_app/services/audit_service.py` calling **its own** `log_event(db, event_type, …)` —
  the justified-keeper case the criterion allows.

### Validation of the N re-check

| Check | Outcome |
| --- | --- |
| `pytest tests/test_content_safety.py` | 50 passed |
| Named regression files (acceptance gaps, groq provider, new features, phase2 security, export link remap, collab ws, logging config) | 170 passed total |
| Fail-before probes (2 production files swapped for their `133d790` / `bb0c4a0` versions, then restored) | Fail as documented; working tree byte-identical to pre-probe backups; `git diff --cached` empty |
| `ruff check src tests scripts` · `compileall -q src scripts` · `git diff --check` | Clean · clean · clean |
| Frontend `typecheck` · `lint` · vitest (`authStore`, `DataManagementTab`) | Clean · clean · green |
| Full suites / `verify_pr.py` · live-Groq run · Windows rehearsal · human beta/privacy review | Still **open** (not executed; no sign-off claimed) |

## Remaining-issues pass — 2026-09-13 (F17–F20, audits, full gate)

Closing the items the earlier passes left open: the unrun consolidated gate, the unresolved
dependency audits, the possible dead symbol flagged in the original audit, and whatever the
full-suite run then uncovered.

### F17 — the CI production gate could never pass (two independent causes) — **fixed**

`e2e-production-gate` is the F15 gate. Run against a clean database it fails at its own first
assertion, for two reasons that were never observable because the job had never executed:

1. The job bootstraps with `AAC_BOOTSTRAP_ADMIN_PASSWORD: Admin123`, but
   `_ensure_bootstrap_admin` **rejects the development default in production**
   (`the development default must be changed`). Database initialization then fails, `/ready`
   returns `503 database_unavailable`, and the gate's `/ready == true` assertion fails.
2. The job supplies `GROQ_MODEL: openai/gpt-oss-120b`, but nothing read that name (see F18), so
   the Groq warmup raised `Groq provider requires an explicitly configured model` and `/ready`
   reported `degraded` (3/4 providers).

**Probe (pre-fix, exact CI values):** `/ready` → `{"ready":false,"status":"database_unavailable"}`;
log → `Failed to initialize database: AAC_BOOTSTRAP_ADMIN_PASSWORD is not acceptable in
production: the development default must be changed` and `Warmup: Failed to initialize LLM
provider: Groq provider requires an explicitly configured model`.

**Fix:** the gate now bootstraps with a unique non-default password
(`CiProd-Gate-Admin1-2f7c`, mirrored in the curl login and `E2E_ADMIN_PASSWORD`), and F18 makes
its `GROQ_MODEL` effective.

**Evidence (post-fix, isolated temp data dir, synthetic key, freshly bootstrapped DB):**
`/api/health` 200 version 2.0.0 · `/ready` → `{"ready":true,...,"providers":{"speech":true,
"llm":true,"achievement":true,"vector_store":true}}` · admin login 200 (257-char token) ·
`/api/providers/health` → `groq.configured = True` · 15-attempt login burst → 6×429 (rate
limiting active with `TESTING` unset) · SPA `index=200` · zero `ERROR` lines in the server log.

### F18 — the documented `GROQ_MODEL` setting had no implementation — **fixed**

`BACKEND_AUDIT_AND_IMPROVEMENT_PLAN.md` documents `GROQ_MODEL` as a config setting, `.env`
cannot set it (`src/config.py` had no such field), and the provider read only the persisted DB
setting. An env-only deployment therefore had no way to configure the model — and a deployment
that configured it *after* startup could not become ready either, because provider readiness is
a startup snapshot that `PUT /api/settings/ai` does not refresh.

**Fix:** added `GROQ_MODEL: str = ""` to `src/config.py` and `_effective_groq_model()` in
`src/api/deps/providers.py`, mirroring the key's established precedence
(**DB setting > canonical config/.env > process env**, stripped). Warmup and
`get_groq_provider()` use it, and `board_ai._resolve_provider_for_board` now shares the same
resolver instead of its own inline lookup. An empty resolution still means "not configured", so
warmup keeps failing closed rather than guessing a model. Documented in `.env.example`.

**Evidence:** `TestEffectiveGroqModel` (4 tests) — precedence + stripping, env-only deployment
configured, empty-everywhere stays unconfigured, and the config field actually exists. The F17
production smoke is the end-to-end proof (`llm: true` where it previously failed).

### F19 — two tests still asserted the retired query-param refresh transport — **fixed**

The full backend suite surfaced two failures that the named-file runs never touched, both stale
encodings of the pre-F03 transport:

| Test | Failure | Fix |
| --- | --- | --- |
| `test_board_contracts.py::test_auth_token_and_refresh_payloads_match_frontend_authstore` | `params={"refresh_token": ...}` → 400 `refresh_token required` | sends the credential in the JSON body, matching `authStore.refreshAccessToken`; docstring records the transport |
| `test_error_i18n.py::test_refresh_token_error_is_spanish` | same query transport → 400 instead of the expected 401 | body transport; the localized 401 assertion now exercises real token validation |

No production change: D5 deliberately retires URL transport, so the tests were updated rather
than the endpoint relaxed.

### F20 — dead `LocalSpeechProvider.transcribe` — **deleted**

The original audit flagged this symbol for a liveness re-check. Production-only search scope
(`src/`, `src/scripts`, operator scripts, `launcher.pyw`, packaging, frontend): no runtime
import/call, no dynamic import, no operator-script use, no migration, no generated contract, no
HTTP surface. The only `.transcribe(` call in the tree is `self.model.transcribe(...)` — the
underlying Whisper model, not the provider. The one test reference was a mock attribute that
stubbed a method nothing calls, and it stubbed the *wrong* method: `mock_speech_provider` now
stubs `recognize_from_file`, the live call. `transcribe` was a thin alias to
`recognize_from_file` with zero callers, so it was deleted rather than preserved for tests.

### Dependency and build audits (previously unresolved)

| Check | Outcome |
| --- | --- |
| `pip-audit --requirement requirements.txt --strict` (production, locked) | No known vulnerabilities found |
| `pip-audit --requirement /tmp/aac-all-requirements.txt --strict` (all groups, `uv export --locked --all-groups`) | No known vulnerabilities found |
| `npm audit --omit=dev --audit-level=moderate` | found 0 vulnerabilities |
| `npm audit --audit-level=high` (dev tree) | found 0 vulnerabilities |
| `python scripts/check_dependency_usage.py` · `scripts/audit_codebase.py` · `uv pip check` | Passed · passed · No broken requirements found |
| `npm run typecheck` · `npm run lint` · `npm run build` (incl. bundle-size check) | Clean · clean · built; largest JS 396.7 kB (budget 450 kB), largest CSS 139.8 kB (budget 150 kB) |
| Full backend suite (`pytest --cov=src --cov-branch`) | **0 failures**, 86% total |
| Full frontend suite (`npm test -- --run`) | **102 files / 857 tests passed** |

### Live-provider gate — still blocked, on credentials only

There is **no non-empty `GROQ_API_KEY`** anywhere in this repository or its `.env`
(`grep -c '^GROQ_API_KEY=.\+' .env` → 0). A real live-Groq run therefore cannot be executed
here; the F17 smoke uses the same synthetic-key shape CI uses and proves selection, readiness,
rate limiting, and serving — not live model availability. That gate stays open until a real key
is supplied.

### Validation of this pass

| Check | Outcome |
| --- | --- |
| Pre-fix production-gate probe (CI's exact values) | `/ready` 503 `database_unavailable`; DB-init and Groq-model errors in the log |
| Post-fix production-gate smoke | `/ready` true with `llm: true`; login 200; `groq.configured = True`; 429s; SPA 200; 0 ERRORs |
| `ruff check src tests scripts` · `compileall -q src scripts` · `git diff --check` | Clean · clean · clean |
| `pytest tests/groq_provider + config_pydantic` · full backend suite · full frontend suite | 25 passed · 0 failures · 857 passed |
| `uv run python scripts/verify_pr.py` (consolidated local PR gate, single run) | **ALL MAINTAINER VERIFICATION CHECKS PASSED** — 14 steps green (ruff, compileall, import audit, dependency usage, pip-audit production + development, i18n keys, backend pytest + coverage, frontend typecheck, ESLint, npm production + development audit, Vitest + coverage, production build) plus `requirements.txt` locked-lockfile consistency and 0 broken links across 85 markdown files |
| `LocalSpeechProvider.transcribe` re-search after deletion | Only the Whisper model's own `.transcribe(` remains |
| Windows artifact/update/rollback rehearsal · human beta/privacy/accessibility review · GitHub Actions green run · live-Groq run | Still **open** (first three require external environments/actions; the last needs a real key) |

## Remaining-issues pass — 2026-09-13 (Q1–Q11)

Third independent backlog (`PROMPT_3.md`), audited the same way: each item re-verified against the
actual code before changing anything, each fix validated with a test that fails on the pre-fix
baseline and passes after.

| ID | Disposition | Files | Change | Evidence |
| --- | --- | --- | --- | --- |
| Q1 | **Fixed** | `src/frontend/src/pages/Settings/DataManagementTab.tsx` | Toast prefers the outcome key `learning_history_added` (`??` so a real 0 survives) and only renders the truncated warning when `total_learning_sessions` is numeric; otherwise the plain success toast — never "of undefined" | 2 new specs; both **fail on HEAD** (2 of 5 pre-fix failures) |
| Q2 | **Fixed** | `src/frontend/src/store/authStore.ts` | `register` no longer bumps `checkAuthEpoch`; it captures the epoch and guards its error set against newer session owners. The spinner is now a **pending-operation count** instead of an owner epoch: it clears only when the last in-flight op settles, so a stale op releases its own contribution (N5) and a settling registration can never hide an in-flight login's spinner | 3 new specs; all 3 **fail on HEAD** (the spinner spec fails on the intermediate owner-token shape too — pre-fix `1 failed / 24 passed` vs post-fix `25 passed`) |
| Q3 | **Fixed** | `src/config.py` (`refresh_query_fallback_allowed()`), `src/api/routers/auth.py` | One plain helper implements "explicit opt-in only"; the dead production branch and the duplicated lookups are gone. `grep` shows exactly one call site | D5 matrix tests green unchanged |
| Q4 | **Fixed** | `src/api/main.py` | `bounded_receive()` waits on `receive()` under a 25 s inactivity timeout; expiry resolves through the same overflow/abort path with a warning log carrying bytes + elapsed. Declared, chunked and stalled-mid-body shapes covered | stalled-body ASGI test (short injected timeout) aborts instead of hanging; 413 tests green |
| Q5 | **Fixed** | `src/api/deps/providers.py` (`resolve_groq_api_key()`), `src/api/routers/board_ai.py` | Public resolver exported and used by both callers; no private cross-module import remains | repo-wide search: no `_effective_groq_key` reference outside its module; key-matrix + singleton tests green |
| Q6 | **Fixed** | `src/api/routers/collab.py` | Comment rewritten to match the code (ignore the lifespan event outside lifespan; use a local event so tests never observe production shutdown) | comment/code agreement on re-read; collab tests green |
| Q7 | **Fixed** | `src/aac_app/services/learning/responses.py` | Guard now names both inputs (`not audio_data and not audio_path`); the path-only upload branch above is therefore never shadowed by a future edit | unit test for voice-with-neither-inputs; voice F07/D8 tests green |
| Q8 | **Fixed** | `src/aac_app/services/content_safety.py` | Throttle state starts at `None`; the first `log_event` of a process only opens the window instead of paying an unconditional full-table `COUNT(*)` | instrumented test asserts 0 prune calls on the first event, 1 on the Nth; **fails on HEAD** |
| Q9 | **Fixed** | `src/aac_app/services/content_safety.py::moderate_output` | Blank/whitespace output returns `Verdict(allowed=True)` with no `generate` call, no audit row and no meter spend; non-blank text keeps the full fail-closed path | counting-`generate` test: 0 calls / 0 rows for blank, 1 call for "texto normal"; **fails on HEAD** |
| Q10 | **Fixed** | `src/api/routers/export_import.py` | Outcome counts are measured as raw deltas (`boards_created`, `boards_merged`, `symbols_added`, `learning_history_added`) so a retry reports what it actually wrote | retry test asserts `created+merged == boards seen`; **fails on HEAD** |
| Q11 | **Fixed** | `src/api/logging_config.py::_redact_message` | Copula rule widened to `is|es` so the Spanish-first rendering `password es <valor>` is masked like the English form. Key-set scope documented in the pattern comment: only the copula is localized, the key set stays the identifiers that actually appear in log messages (evidence-based, per the instruction not to broaden keys without evidence) | new spec; **fails on HEAD** |
| **R1** | **Fixed** (found during the §10 re-inspection) | `src/api/logging_config.py` (`_redact_exception`, `_redacting_patcher`) | **The F09 patcher only rewrote `record["message"]`.** Loguru renders `record["exception"]` separately, so an exception whose own text echoed a credential reached every sink verbatim. The patcher now substitutes a leak-free rebuilt exception (same type when constructible, else `RuntimeError` carrying the original type name); the live exception object the caller still handles is never mutated | live-sink subprocess probe: canary was present **1× in each sink file** pre-fix, **0** after, with `RuntimeError: provider failed …` / `ValueError: bad payload api_key=***` and the log context preserved; 4 new tests **fail on HEAD**, pass after |

**Pre-fix baseline captured before the fixes** (HEAD production files restored, then restored byte-for-byte):
backend — `test_moderate_output_blank_text_costs_nothing`, `test_first_log_event_records_baseline_without_pruning`,
`test_spanish_copula_is_masked` all **FAILED**; frontend — **5 failed / 28 passed** (`tests/authStore.test.ts`
+ `tests/DataManagementTab.test.tsx`), i.e. the two Q1 and two Q2 specs plus the N5 spinner spec.
Q7's test is a guard, not a discriminator (the pre-fix condition was already behaviorally equivalent for
both-falsy inputs), and is documented as such rather than claimed as a fail-before.

Validation after the pass: `ruff check src tests scripts` clean · `compileall -q src scripts` clean ·
`git diff --check` clean · backend named files **239 passed** across the 11 files §8 names
(`test_logging_config`, `test_content_safety`, `test_new_features`, `test_export_link_remap`,
`test_acceptance_gaps`, `test_phase2_security`, `test_groq_provider`, `test_collab_ws`,
`test_password_reset_security`, `test_response_processing_helpers`, `test_startup_warmup`) ·
frontend `typecheck` 0 · `lint` 0 · Vitest `authStore` + `DataManagementTab` + `offlinePersistence`
+ `api` **74 passed** · production build inside budget (396.7 kB JS / 450 kB, 139.8 kB CSS / 150 kB).

### §10 final bug hunt and §11 re-verification

Re-inspected every touched flow after the fixes; the results are recorded rather than assumed:

| Re-check | Result |
| --- | --- |
| §4 table re-verified post-change | `log_event` signature has no `db`/`session` and is keyword-only (`PASS`); `_PredictionContext` still requires `db` (`PASS`); `_api_key_env` occurrences **0**; the three remaining `except HTTPException` sites in `collab.py` are each narrow and explicitly re-raise/close (the dead no-op re-raise is gone); `AAC_REFRESH_ALLOW_QUERY_FALLBACK` declared once and read by one helper |
| Auth epoch interplay (register/login/checkAuth) | Found and fixed additional spinner aliasing beyond the Q2 row (see Q2): ownership-token model replaced by a pending-operation count; superseded ops release in `finally` so a hung or stale op can never pin the spinner |
| Middleware timeout vs drain timeout | The bounded receive raises the same terminal `_BodyTooLarge` path as a byte overflow; the drain reads stay separately capped at 0.5 s × 3, so the timeout cannot extend the request |
| Redactor pass ordering with the new copula | Direct probe: `password es`, `token es`, `password is`, JSON pair, `Bearer`, `X-*-API-Key`, bare `=`/`:` all masked; `status es ok` untouched; every case idempotent under a second pass; 2000-char bound intact |
| Import arithmetic on partial failure | Single commit after all sections are staged; a failure raises before the post-commit counters run, so the deltas can never describe a rolled-back state |
| Newly dead code / stale callers | No `loadingOwnerToken`/`loadingOwnerEpoch` left in `src`/`tests` (only the generated `coverage/` HTML, which is ignored); no dead private Groq alias; no temp probe files left behind; `git status` shows only the untracked `PROMPT_*.md` prompt artifacts |
| Live-sink secret hygiene | The probe above (`R1`) is the evidence that the redactor covers the rendered exception, not just the message |
| Cyclic links (§7) | Covered by the mutual-link cases: `test_import_preserves_owned_to_assigned_links` and `test_import_preserves_assigned_to_assigned_links` both assert the link in **both** directions; missing/external references stay cleared |

## Completion requirements

1. Reproduce each source finding safely, implement the fix, and record its commit/files plus focused regression results under the corresponding ID. If current evidence disproves an item, document the concrete reason instead of implementing an unnecessary change.
2. Provision locked Python/frontend dependencies without broad upgrades. Run dependency evidence checks and the locked production/all-group Python and production/development npm vulnerability gates required by AGENTS.md. Track actual advisories; do not suppress them broadly.
3. Run required backend lint/compile checks and named affected pytest files; frontend typecheck/lint, named affected Vitest files, and fresh production build/bundle checks. Investigate incomplete focused tests with bounded execution and useful diagnostics.
4. Perform an isolated production-mode API smoke with actual `/ready` evidence and at most one or two named browser specs for changed critical flows. Obtain separate live-Groq evidence when configured and authorized. Preserve the real admin database and secrets.
5. Rehearse recovery using a disposable DB and matching uploads/config. Preserve existing migrations; schema changes require legacy-data fixtures and integrity/foreign-key checks. Keep signed-export compatibility obligations explicit.
6. Keep Windows artifact/update/rollback, representative AAC accessibility/hardware testing, and the documented human beta/privacy review as external release gates until actually performed. No agent may invent these outcomes.
7. Update every finding to fixed, disproved, or explicitly blocked with evidence. Run `git diff --check`. Audit and stop all task-owned runners/servers before handoff. Only claim production sign-off when the required evidence exists.

Only this handoff document is intended as the repository change from the audit. No production fixes, secret changes, or database modifications were authorized as part of the diagnosis pass.

## PROMPT_4 whole-product sweep (Tiers A–G)

Baseline: `9040056` (the pending R1 redaction + pending-op spinner, committed first).
Work below is on top of that. Status per item; every "Fixed" line has a focused
regression test recorded against it (fail-before / pass-after where the defect was
reproducible).

### Verified and fixed

| ID | Files | Change + evidence |
| --- | --- | --- |
| A1 | `src/api/routers/export_import.py` | Import-history bounds tightened to the `LearningSession` columns (`topic_name`/`topic` ≤ 100, `status` ≤ 20) so a legacy over-width export is rejected at validation (400) instead of raising `DataError` at Postgres commit and rolling back the whole recovery import. 3 specs incl. a boundary case; 2 fail on the pre-fix bound. |
| A3 | `src/frontend/src/lib/api.ts` | Replay success publish is generation-guarded like the error branch. Guard, not a discriminator: `clearSessionMutations` aborts the in-flight request first, so axios rejects `ERR_CANCELED` before the success branch is reachable through the public API. |
| A4 | `src/api/routers/{learning,board_ai,analytics,providers,auth_helpers}.py` | `conditional_limiter` extended to async endpoints (a sync wrapper around an async target hands FastAPI a coroutine) and now marks limited endpoints with `__rate_limited__`. Applied to ask/answer/voice/symbol answers, board AI suggestions, next-symbol, TTS synthesize and warmup. |
| A5 | `src/api/routers/learning.py` | `ask_question` difficulty is validated against `schemas.DifficultyBand` (422 otherwise) instead of being interpolated into the generation prompt verbatim. |
| A8 | `src/aac_app/services/learning/session.py`, `src/api/routers/learning.py` | The four learning service catch-alls now log and re-raise, so a DB outage surfaces as 5xx instead of a 400 that reads as invalid input; route-side mapping collapsed into one `_raise_service_failure` helper (validation → 400, missing → 404, safety → 403). |
| A9 | `src/aac_app/services/content_safety.py` (`utc_day_start`), `src/api/routers/content_safety.py` | The sentinel spend meter and the admin clear share one UTC day boundary matching the `func.now()` timestamps; a local midnight drifted both by the UTC offset. `_today_start` renamed public and the 3 test references updated. |
| A10 | `src/api/routers/symbols.py` | Batch placement update fetches once into a dict (chunked at 500) instead of one SELECT per entry inside the write lock. 3-vs-30-placement SELECT-count spec passes (pre-fix 5/9 → post-fix flat). |
| A11 | `src/aac_app/services/learning/session.py`, `src/api/routers/learning.py`, `src/frontend/src/store/learningStore.ts` | History pages `defer(conversation_history)` and the route cap drops 1000 → 200 (frontend page size matched; the walk still pages). |
| A12 | `src/api/routers/export_import.py` | `selectinload(UserAchievement.achievement)`; export SELECT count flat in achievement count (pre-fix 8→14, post-fix flat). |
| A13 | `src/api/schemas.py` | `AISuggestionsRequest.refine_prompt` bounded at 2000 (prompt-fed, was unbounded). |
| A15 | `src/frontend/src/store/authStore.ts`, `src/frontend/tests/authRehydrate.test.ts` | Rehydration gates `aac:auth-ready` on `checkAuth()` (validate → silent refresh) when a persisted session exists, so the offline queue never flushes with a dead token. Own spec file (the hook needs an unhydrated module registry): pre-fix `[]` ≠ `['post:/auth/refresh']`. |
| A16 | `src/frontend/src/store/authStore.ts` | `logout` clears state + persisted `auth-storage` synchronously via `clearSession()` before the best-effort revocation. Spec asserts the storage is already clear while revocation is pending. |
| A20 | `.env.example`, `env.properties.example`, `README.md`, `docs/01_PROJECT_GUIDE.md` | Added the missing operator-visible keys (`AUTOGEN_*`, `SENTINEL_*`, `SUPPORTED_UI_LANGUAGES`, `AAC_REFRESH_ALLOW_QUERY_FALLBACK` with its deprecation note, `AAC_ASSISTANT_*` flags, `GROQ_MODEL` in both examples), plus README rows for `GROQ_MODEL` precedence/fail-closed and the refresh opt-in. Parity test asserts every `Settings` field is greppable in an example (derived paths excluded). |
| A21 | `.github/workflows/ci.yml` | The production gate provisions synthetic non-default `E2E_STUDENT_PASSWORD`/`E2E_TEACHER_PASSWORD` instead of `Student123`/`Teacher123` — `SECURITY_ARCHITECTURE` forbids demo passwords outside test environments and the create-user path only checks strength. |
| A22 | `.github/workflows/ci.yml` | Documented why `packaging-windows` omits `TESTING=1`: it runs an install/smoke check, so the limiter must stay active (backend tests opt out). |
| A23 | `start.bat` | Pinned `uv sync --python 3.13` + `run --no-sync` and added the same "existing .venv must be 3.13" guard `start.sh` has, so a 3.14-resolving Windows checkout cannot silently drop Kokoro. |
| A24 | `.github/workflows/ci.yml` | The production audit now also exports and audits the shipped extra set (`--extra voice --extra tts`), which `requirements.txt` (no extras) omits. |
| A25 | `docs/SECURITY_ARCHITECTURE.md` | JWT-secret sentence scoped to production/first run: the config default is `""` and `ensure_jwt_secret` returns early outside production, so "never used" was overstated. |
| E1 | `src/api/routers/arasaac.py` | `POST /api/arasaac/import` requires `get_current_staff_user`; a student could previously create shared catalog rows, write images and index vectors. |
| E2 | `src/api/routers/{achievements,guardian_profiles}.py`, `src/aac_app/services/guardian_profile_service.py` | Capped `skip`/`limit` on the achievement catalog and the student roster (service query orders by `User.id` and pages). |
| E3 | `src/api/schemas.py` | `SymbolUsageRequest.symbols` capped at 100 (one insert per item). |
| E4 | `src/api/schemas.py`, `src/api/routers/guardian_profiles.py`, locales | Guardian/preview prompt-fed fields mirror their persisted bounds (template_name 100, preview fields = create/start caps, `custom_instructions` 10k, nested list counts + item lengths); `preview_template` overrides validated against the loaded template's own dot-path shape with key/list/string caps. New `errors.guardian.invalidOverrides` key. |
| E5 | `src/api/routers/providers.py`, `src/api/routers/auth_users.py` | TTS `lang` bounded 2–10; warmup `targets` capped at 3 and unknown values now 400 instead of silently `{}`; `admin_unlock_account(username)` capped at `USERNAME_MAX_LENGTH`. New `errors.providers.unsupportedWarmupTarget` key. |
| E6 | `src/api/routers/board_assignments.py` | Staff path runs `verify_student_access`, so an admin gets 404 for a bogus `student_id` instead of `[]` (teacher path unchanged). The query-budget spec moves 4 → 5 with a comment. |

### Verified, then disproved (no change)

| ID | Finding |
| --- | --- |
| A2 | `delete retryConfig.headers.Authorization` **does** clear the header on the pinned axios: `Authorization` is an own, configurable data property on `AxiosHeaders`, not only an internal store (`node` probe + `Object.getOwnPropertyDescriptor`), so the retry already re-attached the fresh token. The `AxiosHeaders` API form is retained as version-independent hardening with the note in the code; the new spec is a contract guard, not a discriminator. |
| A14 | `earned_at=earned_at` (i.e. `None`) is **not** equivalent to `null()`: the column declares `default=func.now()`, so `None` makes SQLAlchemy apply the default and a timestamp-less legacy achievement is stored as "now". `tests/test_new_features.py` failed immediately on that change, proving the original `null()` is load-bearing. Reverted and pinned the real contract (persisted NULL) instead. |

### Implemented but not covered by a new focused spec

| ID | Files | Note |
| --- | --- | --- |
| A7 | (not changed) | Token-rotation reconnect dropping queued collab moves was not addressed in this pass. |
| F1 | (not changed) | Non-SQLite additive migrations still rely on the SQLite-only helpers. |
| F2 | `src/api/deps/providers.py` | Warmup now builds the Groq instance from `resolve_groq_api_key()`/`resolve_groq_model()` (the getter's precedence) so an env-only key no longer installs an empty-key singleton that the first request discards. Spec asserts `is_configured()` and singleton identity; fails pre-fix. |
| F3 | (not changed) | n-gram rebuild/shutdown handshake and scheduled-download cancellation not addressed. |
| F4 | `src/aac_app/services/{symbol_catalog,local_vector_store,ngram_builder}.py` | Casefold dedupe scan streams via `yield_per` under a documented 50k row cap; orphan vector deletes computed in Python and issued in 500-row chunks instead of one ~17k-placeholder `NOT IN`; n-gram rebuild preloads one `id → language` map plus a per-distinct-label memo instead of 1 + up to 2 queries per log. |
| F5 | `src/aac_app/seed.py` | Learning-mode seeding upserts per `key`, so a subset-seeded DB gains exactly the missing defaults (and a rerun adds nothing). Spec fails pre-fix. |
| F6 | `src/api/deps/providers.py` | `get_vector_store` releases the locks, waits for the deferred cleanup and retries (bounded 5 attempts) instead of raising a transient 500 when a reset detaches the store in the lock gap. |
| F7 | (not changed) | CORS credentialed wildcard and warmup executor abandonment left as-is; not verified in this pass. |

### Continuation pass (Tier C remainder, Tier G, F1/F3/F7, Deferred)

| Item | Files | Change |
|---|---|---|
| A6 | `OfflineConflictsPanel.tsx`, `offlineStore.ts` | Manual conflict retries send the replay marker, keep their own ownership check and surface the failure on the conflict entry (`updateConflictError`) instead of a console-only log + forced logout. |
| A7 | `lib/ws.ts`, `hooks/useBoardCollab.ts` | The pending send queue is shared with the replacement client on a token rotation (`close({clearQueue:false})`) and cleared only when the board changes, so drag moves made during a refresh window are not lost. |
| A17 | `hooks/useBoardEditorSymbols.ts`, `BoardEditorGrid.tsx`, `DraggableSymbol.tsx`, `BoardEditor.tsx` | Remote collaborator moves render as overrides with a remote-presence ring and never set local dirt; a later local edit saves both placements. |
| A18 | `store/settingsStore.ts`, `AiProviderTab.tsx` | Per-endpoint request ids and loading flags replace the single shared sequence/spinner; autosaves are serialized so rapid edits cannot land out of order. |
| A19 | `Settings/DataManagementTab.tsx` | The truncated-import toast requires both counts to be numeric; older payloads fall back to the plain success template. |
| G1 | `lib/tts.ts`, `store/learningStore.ts`, `store/notificationsStore.ts`, `store/offlineStore.ts`, `hooks/useBoardEditorSymbols.ts`, `SymbolSearchModal.tsx` | Bounded debounce map, transcript window (`MAX_CLIENT_MESSAGES`), notification cap, conflict cap, LRU editor contexts, and batched rendering (`show more`) for symbol search. |
| G2 | `Smartbar.tsx`, `SymbolSearchModal.tsx` | The auto-refresh budget is keyed per pictogram batch (a later batch gets its own), and prediction/search failures are visible with a retry instead of looking like an empty vocabulary. |
| G3 | `App.tsx` | `RootLayout` wraps the shell (`SettingsManager`, `AppToaster`, `Outlet`) in `ErrorBoundary`, covering `/login`, `/register`, `/setup` and `*` too. |
| G4 | `BoardEditor.tsx` | Board clear is bounded-parallel (5 at a time) and resyncs with the server on success and on partial failure. |
| G5 | `CommunicationChat.tsx`, `Communication.tsx` | Voice and fullscreen toggles expose `aria-label` + `aria-pressed`. |
| F1 | `src/aac_app/schema.py` | Additive column/index discovery moved to the SQLAlchemy inspector and a dialect-aware DDL translator, so non-SQLite deployments get the same upgrades; the SQLite-only FK table rebuild now logs an explicit warning on other dialects (its only non-portable step). |
| F3 | `src/api/main.py`, `services/symbol_image_backfill.py` | The n-gram rebuild worker uses the same shutdown handshake as the index worker, and scheduled symbol-image downloads are cancelled and drained inside the shutdown budget. |
| F7 | (verified, no production change) | Credentialed preflight probe: Starlette emits a concrete method list, echoes requested headers and an explicit origin — no literal `*`. Lock probe: the speech provider is constructed outside the provider lock and the vector store under it is `lazy_load=True`. Both pinned by tests instead of "fixed". |
| D-a | `routers/boards.py` | The `update_board` allow-list is derived from the real writable `CommunicationBoard` columns, so it can actually fire. |
| D-b | `routers/boards.py` | `delete_board` nulls `SavedTopic.board_id` in the same transaction. |
| D-c | `SymbolPicker.tsx` | A failed symbol page walk renders a visible error with retry instead of an empty-catalog look. |
| D-d | `store/boardStore.ts` | `hasMore` comes from a one-ahead probe (exact, no boundary fetch) and mutations reload every loaded page instead of collapsing to page 1. |
| D-e / D-f | — | Closed by A18 and E4/A5 respectively. |

### Not addressed (explicitly open)

Every Tier A–G item and every deferred item has a landed change or a documented
verification result; see the table above. What remains open is external
validation only: live Groq/Playwright E2E, a real production-mode smoke, the
Windows packaging rehearsal, a live Postgres instance for F1, and live CI
execution.

### Validation run for this pass

`uv run ruff check src tests scripts` clean · `python -m compileall -q src scripts` clean ·
`git diff --check` clean · frontend `typecheck` 0 · `lint` 0 · `i18n:audit` clean ·
backend named files **316 passed** (`test_prod_sweep4_backend`, `test_export_link_remap`,
`test_guardian_profiles`, `test_ngram_builder`, `test_learning_routes_coverage`,
`test_learning_topics_endpoint`, `test_board_assignment`, `test_arasaac_library_import`,
`test_content_safety`, `test_phase2_security`, `test_query_count_regressions`,
`test_startup_warmup`, `test_new_features`, `test_acceptance_gaps`,
`test_boards_list_symbols_and_achievement_routes`, `test_board_contracts`,
`test_user_creation_validation`, `test_learning_modes_integration`, `test_groq_provider`,
`test_collab_ws`, `test_password_reset_security`, `test_response_processing_helpers`,
`integration/test_startup_seeding`) · frontend Vitest `api` + `authStore` + `authRehydrate`
+ `offlineStore` + `OfflineConflictsPanel` + `offlinePersistence` **77 passed**.

External gates that were **not** run here and stay open: live Groq/Playwright E2E, a real
production-mode API smoke, the Windows packaging rehearsal, and live CI execution.

### Post-implementation audit (2026-09-13) — gaps found and closed

Re-reading PROMPT_4.md item by item against the tree found validation evidence
missing for several items whose *code* had landed. Each gap below now has a
test; fail-before was captured by stashing only the production files involved
and re-running (`git stash push -- <files>` → failures → `git stash pop`).

| Item | Was missing | Now covered by |
|---|---|---|
| A4 | No test asserted 429 for any LLM endpoint (only the auth routes had one) and nothing pinned which handlers are limited. | `test_every_llm_invoking_handler_carries_a_limiter` (structural, all 8 handlers) and `test_llm_route_burst_is_throttled_and_the_legit_calls_are_not` (real 5/minute burst → 400×5 then 429). |
| A5 | No injection/allow-list test. | `test_ask_question_difficulty_is_allow_listed` — injection string → 422, each valid band reaches the session lookup (404). |
| A8 | No test that unexpected failures surface as 5xx, nor that the service re-raises. | `test_learning_service_reraises_unexpected_db_errors` (fails before the fix), plus `..._propagates_as_500` and `..._domain_failure_keeps_its_4xx`. |
| A21 | CI used synthetic passwords but nothing checked them. | `test_production_gate_credentials_are_synthetic_and_policy_compliant` parses the `e2e-production-gate` job and asserts each value is non-default and passes `password_strength_error_key`. |
| A22 | No check of the TESTING gate itself. | `test_conditional_limiter_is_inert_under_testing`. |
| E1 | No API-level authorization test (the existing ARASAAC tests call the handler directly, bypassing the dependency). | `test_student_cannot_import_arasaac_symbols` — student → 403; staff clears the dependency (empty payload then 422, no download). |
| E2 | No paging/ordering test. | `test_achievement_listing_is_paged_and_stably_ordered` (skip/limit windows, order, 422 over cap) and `test_guardian_student_listing_is_bounded`. |
| E6 | No test for the admin path. | `test_admin_assignment_view_404s_for_a_missing_student` (404 vs real-but-unassigned 200 `[]`). |
| F6 | No test for the reset race. | `test_vector_store_getter_retries_across_a_reset`. |
| D-d | Only delete preserved pages. | `refetchLoadedPages` now also backs `createBoard`/`duplicateBoard`; specs added. |

Honest exception: `test_learning_service_unexpected_failure_propagates_as_500`
passes both before and after the fix — the router never swallowed exceptions,
so it is a guard, not a discriminator. The A8 defect itself (the *service*
returning `{"success": False}` for any exception) is pinned by
`test_learning_service_reraises_unexpected_db_errors`, which does fail before.

### Cleanup pass (§9)

* **One limiter instance.** `src/api/routers/auth_helpers.py` owned a private
  `Limiter` while `main.py` registered a second one from `src/api/limiter.py`
  as `app.state.limiter`. slowapi's 429 handler formats headers from
  `app.state.limiter`, so the duplicate could not see the counts. The helper now
  imports the single instance; `test_the_app_registers_the_same_limiter_instance_it_decorates_with`
  pins the identity.
* **No new symbols left unused**: every constant/helper added in this pass has
  at least one call site (checked by reference count).
* No diagnostic scripts, temp tests, or stray runners remain; `git stash list`
  is empty and no `uvicorn`/`vitest`/`playwright` process is left running.

---

# PROMPT_5 — Tiers H–R execution log (2026-09-13)

## Baseline recorded at start of this pass

* Branch `fix/pagination-n1-e2e`, HEAD `9040056` ("Redact rendered exception text and
  count pending auth spinner ops") over `1e1caa7`/`bb0c4a0`; `git diff --cached --stat`
  empty.
* Working tree already carried the PROMPT_4 backlog (Tiers A–G + Deferred) as uncommitted
  changes plus its sweep tests; that work is included in the §4 verdicts below.
* The five baseline files named in PROMPT_4 §2 (R1 redaction in `src/api/logging_config.py`,
  the pending-op spinner in `authStore.ts` + its spec, `tests/test_logging_config.py`,
  `PROD-FIXES.md`) are committed as `9040056`.
* The environment has **no browser tool** (no chrome-devtools MCP / Playwright-driving
  tool available to the agent), so §9 is executed as the documented fallback: a real
  uvicorn server on `127.0.0.1:8086` driven by `curl` against an isolated `DATA_DIR`
  (see "Live-server walk"). No GUI claim is made for anything that needs a rendered DOM.

## §4 — PROMPT_4 tier verdicts (re-verified in the tree, behaviour exercised)

| Tier | Verdict | Evidence |
|---|---|---|
| A (A1–A7) | FIXED | A1 width bounds in `_validate_import_payload` (`topic_name`/`topic` ≤ 100, `status` ≤ 20) with 400-not-500 tests; A2 header strip via the `AxiosHeaders` API + `api.test.ts`; A3 replay generation guard; A4 `conditional_limiter` on all 8 LLM handlers (structural test + real burst → 429); A5 `difficulty` allow-list (injection → 422); A6 replay marker + failure surface in `OfflineConflictsPanel`; A7 collab queue handoff on token rotation (`ws.test.ts`, `useBoardCollab.test.ts`) |
| B (A8–A14) | FIXED | A8 service re-raises unexpected DB errors (asserted), routers map validation → 4xx; A9 UTC day boundary for the sentinel meter + preservation; A10 one `id.in_()` fetch for batch updates (statement-counted); A11 `defer(conversation_history)` + route cap; A12 `selectinload(UserAchievement.achievement)`; A13 `refine_prompt` bounded; A14 verified-then-disproved (`null()` is load-bearing for `default=func.now()`) — contract pinned instead |
| C (A15–A19) | FIXED | A15 rehydrate gating (`authRehydrate.test.ts`); A16 logout ordering with storage inspection; A17 remote-move dirt + presence ring; A18 per-endpoint request ids/loading + serialized autosaves; A19 truncated-import toast requires both counts |
| D (A20–A25) | FIXED | A20 settings-matrix parity test over both examples; A21 synthetic CI passwords + policy check; A22 `TESTING` parity documented per job; A23 `start.bat` pins 3.13 + guard; A24 production audit exports the shipped extras; A25 JWT-secret sentence scoped |
| E (E1–E6) | FIXED | E1 staff-only ARASAAC import (student → 403 at the API layer); E2 capped achievement/roster lists; E3 `symbols` batch ≤ 100; E4 guardian/preview prompt-fed bounds; E5 TTS `lang`, unlock `username`, warmup `targets`; E6 admin assignment 404 |
| F (F1–F7) | FIXED / VERIFIED | F1 dialect-portable additive migrations (SQLite + simulated-Postgres fixtures; the FK rebuild logs an explicit warning where no portable equivalent exists); F2 warmup builds Groq from `resolve_*`; F3 n-gram + download shutdown handshake; F4 bounded catalog scans; F5 learning-mode seed upserts per key; F6 vector-store getter retries across a reset; F7 probed — Starlette emits a concrete method list and an explicit origin (no literal `*`), and warmup holds no provider/vector lock across a load; pinned by tests as "disproved" |
| G (G1–G5) | FIXED | G1 bounded stores (growth flood specs); G2 Smartbar per-batch budget + visible search/prediction failures; G3 shell `ErrorBoundary`; G4 bounded-parallel clear + resync; G5 named voice/fullscreen toggles |
| Deferred D-a–D-f | DONE | D-a real-column allow-list; D-b `SavedTopic.board_id` nulled with the board delete; D-c picker load failure surfaced; D-d exact `hasMore` probe + loaded-page preservation for create/duplicate/delete; D-e/D-f closed by A18 and E4/A5 |

## Tier H — file integrity + account lifecycle

| ID | Files | Change + evidence |
|---|---|---|
| H1 | `services/lockout_service.py`, `routers/{auth,auth_users,users}.py` | New `reset_attempts`-based lockout clear after **all four** creation paths (initial setup, register, admin create-user, create-student), so a pre-locked username cannot make first-run setup 403. `tests/test_creation_lockout_reset.py` (pre-lock → create → login 200; fails pre-fix). |
| H2 | `pages/Setup.tsx`, locales, `tests/Setup.test.tsx` | `handleSubmit` now enforces the banned default (`Admin123`) and mismatched/短 passwords, not just the disabled button. Spec submitting `Admin123` asserts a local error and no `setupAdmin` call. |
| H3 | `models/refresh_token.py` (new), `services/refresh_rotation_service.py` (new), `utils/jwt_utils.py`, `routers/auth.py`, `store/authStore.ts`, `tests/test_refresh_rotation.py` | Refresh tokens carry a `jti` + `family`, every exchange consumes the `jti` and mints a successor, and a replay outside a documented 30 s duplicate-in-flight grace revokes the family through the existing `security_version` machinery. Specs: rotation, post-grace replay → 401 **and** successor dead, in-grace duplicate → 200, legacy no-`jti` token still refreshes and gains a `jti`, logout clears the ledger. Frontend persists the rotated refresh token. |
| H4 | `api/schemas.py`, `routers/symbols.py`, `tests/test_symbol_field_bounds.py` | `image_path`/`audio_path` removed from `SymbolUpdate`; image changes must go through `update_symbol_image` (validated + old file removed). Path-carrying PUT is rejected/ignored with the old file intact. |
| H5 | `routers/symbols.py`, `tests/test_symbol_field_bounds.py` | Multipart `description`/`keywords` capped at 10 000 on both `upload_symbol` and `generate_svg_symbol`. 10 001 → 422; boundary passes. |
| H6 | `services/arasaac.py`, `api/file_uploads.py` | Downloaded bytes pass the shared size + PIL-verify allowlist before being persisted. Oversized/non-image → 413/discard; a valid PNG imports byte-identically. |
| H7 | `routers/users.py`, `tests/test_password_reset_security.py` | Staff password reset clears the lockout rows in the same transaction and is rate limited like `change-password`. Locked → reset → immediate login (also re-verified live, see walk). |
| H8 | `routers/{arasaac,export_import,symbols}.py` | Per-endpoint limits on export, symbol listing and the ARASAAC search/import pair, plus a short TTL cache for ARASAAC search (the cache is now cleared by a test fixture so a hit cannot silently skip an asserted upstream call). |
| H9 | `services/notification_events.py`, `routers/notifications.py` | Per-user concurrent-stream cap (excess → 429 and close; a disconnect frees the slot). |
| H10 | `api/schemas.py` | `private_notes`, `change_reason` and the `MedicalContext` subfields mirror their persisted bounds; over-bound → 422. |
| H11 | `routers/symbols.py` | `add_symbol_to_board` commits the achievement progress before responding (same contract as the achievement route) while keeping the best-effort boundary. |

## Tier I — e2e integrity + operator tooling + docs

| ID | Files | Change + evidence |
|---|---|---|
| H12 | `playwright.config.ts` | Project-level student `storageState` removed; roles are now opt-in per spec (teacher/admin states are consumed by the specs that need them). `tests/e2eConfigHygiene.test.ts` pins the shape. |
| H13 | `e2e/groq-verify.spec.ts`, `routers/settings.py` | The spec captures the prior AI settings, restores/masks them in a teardown that runs even on failure, and the GET fallback asserts `res.ok`. |
| H14 | `scripts/fix_null_passwords.py` | Explicit `--disable-login` / `--delete` flags with the non-destructive mode as the default; dry-run untouched. |
| H15 | `scripts/i18n-audit.mjs` | Globs `**/*.{ts,tsx}` with a code-aware filter and flags multiline JSX text; planted strings in a store + multiline JSX trip the gate, clean tree passes. |
| H16 | `launcher.pyw`, `tests/test_launcher_runtime.py` | The startup wait polls server-thread liveness and aborts early when it dies. |
| H17 | `e2e/prod-guard.mjs`, `docs/MAINTAINER_GUIDE.md` | Test globs are ignored by the mtime walk; the doc cites the real repo-root `installer.iss`. |

## Tier J/K — frontend robustness + test fidelity

| ID | Files | Change + evidence |
|---|---|---|
| H18 | `lib/download.ts` | Download anchor is appended → clicked → removed (Firefox needs an in-document node); delayed revoke kept. `download.test.ts` asserts DOM attachment. |
| H19 | `pages/Students.tsx`, `tests/Students.test.tsx` | The confirm-password field renders and validates for teachers too; a mismatch is blocked client-side. |
| H20 | `lib/tts.ts`, `store/{learningStore,notificationsStore,offlineStore}.ts`, `hooks/useBoardEditorSymbols.ts`, `SymbolSearchModal.tsx`, `tests/growthBounds.test.ts` | Caps/eviction inside the existing stores (TTS debounce map TTL+size, transcript window, notification cap, conflict cap, LRU editor contexts, batched symbol-search rendering). |
| H21 | `pages/Achievements.tsx`, `SymbolPicker.tsx`, `tests/SymbolPicker.test.tsx` | `key={a.id ?? a.name}`; picker categories are type-filtered like `Symbols.tsx`. |
| H22 | `SymbolSearchModal.tsx`, `BoardEditor.tsx`, `tests/SymbolSearchModal.test.tsx` | Search failure renders an inline error with retry; clear-before-retry only runs once a query exists. Board clear is bounded-parallel with a resync on success and on partial failure. |
| H23 | `CommunicationChat.tsx`, `Communication.tsx`, `tests/CommunicationChat.test.tsx` | Voice/fullscreen toggles expose `aria-label` (+ `aria-pressed`). |
| H24 | `tests/conftest.py`, `src/api/main.py`, `tests/test_tier_k_fixture_lifespan.py`, `tests/test_startup_warmup.py` | The `client` fixture now runs the real lifespan (`with TestClient(app)` + shutdown-signal handshake) and `setup_test_db` points the **single** process-wide DB seam (`db._engine_instance`/`_session_factory`/`_engine_url`) at the test database instead of patching four call sites — services the old list missed (vector, prediction, content safety, n-gram, autogen, backfill, seed) now use it. Canaries: startup state visible during the test, `lifespan_active` false after exit, `create_session_factory()` bound to the test engine, and a module-bound `get_session` (`vector_utils`) reaching the test DB — the last two fail pre-fix. The symbol-index worker joins the existing `_background_task_runnable` TESTING guard so a cancelled `to_thread` wrapper cannot outlive its lifespan and resolve the *next* test's session factory; `tests/test_startup_warmup.py`'s two index tests opt in the same way the F3 n-gram test already does. |

## Tier L/M — schema widths + services correctness

| ID | Files | Change + evidence |
|---|---|---|
| H25 | `services/learning/session.py`, `tests/test_tier_lm_hardening.py` | Derived `LearningPlan.name`/`LearningTask.name` are bounded to the `String(100)` columns; a 100-char topic starts a session and the stored names fit. |
| H26 | `routers/board_ai.py` | LLM labels/`custom_text` bounded to 100 and colors to a hex-or-≤20 shape *before* insert (oversized input is dropped, never a 500); boundary values persist byte-identically. |
| H27 | `services/symbol_svg_autogen.py`, `services/arasaac_library_import.py`, `tests/test_tier_lm_hardening.py` | `ensure_symbol_generated` skips labels wider than `Symbol.label` (`MAX_SYMBOL_LABEL_LENGTH`, pinned against the model column by a test) before scheduling, and the bulk ARASAAC import mirrors the single-import category/keyword truncations. |
| H28 | `services/symbol_svg_autogen.py` | The original (display) label is stored; the casefolded form is only the dedup key. Mixed-case topic words round-trip with their casing and dedupe stays case-insensitive. |
| H29 | `routers/auth.py` | A routine Argon2 `verify_and_update` rehash persists the new hash **without** bumping `security_version`, so an ordinary login no longer logs every device out; real credential changes still revoke. |
| H30 | `services/achievement_system.py` | Custom automatic achievements are filtered in SQL (`target_user_id IS NULL OR = :user_id`) instead of loading every row and filtering in Python. |
| H31 | `services/board_generation_service.py` | `max_tokens` scales with `item_count` (`600 + 80·n`, clamped to 8 000) instead of a fixed 1 000, so a 100-item request can satisfy the exact-count contract. |
| H32 | `services/symbol_svg_autogen.py` | Vector-index failure is retried inline (3 attempts) and, if it still fails, the symbol id is requeued and repaired on the next autogen request instead of staying unsearchable until a full repair. |
| H33 | `services/local_vector_store.py` | Readiness uses set/count comparison rather than materializing whole-table id sets, and an unavailable store reports "nothing stale" instead of triggering a full re-embed. |
| H34 | `services/learning/common.py` | `_strip_reasoning` returns the stripped text even when empty, so a reasoning-only provider response never republishes ` thinking` blocks to the student. |
| H35/H54 | `scripts/account_admin.py`, `services/user_service.py` | Operator reset clears the lockout rows and warns when the account is deactivated; the secret comes from the environment or an interactive prompt (`--password` still works but warns); `UserService.reset_password` returns whether a row was updated instead of silently no-opping. |
| H36 | `services/symbol_semantics.py` | Explicit `label=None`/non-str handled (`str(s.get("label") or "").lower()`), no 500. |

## Tier N/O — frontend depth + contracts

| ID | Files | Change + evidence |
|---|---|---|
| H37/H64 | `src/main.tsx` | The English locale chunk is awaited inside a try/catch: a failed chunk fetch falls back to the bundled locale and the app still mounts. |
| H38/H59 | `store/learningStore.ts`, `pages/Learning.tsx`, `tests/tierQrHardening.test.ts` | `submitSymbolAnswer` rethrows after recording the error, so callers keep the composed utterance on failure (the `Communication.tsx` restore path can now actually fire). Specs: rethrow on failure, resolve on success. |
| H39/H60 | `pages/Boards.tsx`, `tests/Boards.test.tsx` | Select-all and bulk delete are filtered through `canManageBoard`, so unowned boards are never selected or DELETEd. Spec added. |
| H40 | `hooks/useAccessibleInteraction.ts` | The dwell timer is cleared on unmount (no `triggerClick` with a stale event). |
| H41/H63 | `pages/Dashboard.tsx`, `hooks/useTopicPickerPool.ts`, `components/SettingsManager.tsx`, `hooks/useBoardAISuggestions.ts`, `lib/topicCatalog.ts` | Effects depend on the consumed primitives (`user?.id`/`user_type`) instead of the whole `user`/`settings` object; the activity list is capped (10); the stale AI-error banner is cleared when a new apply starts; topic pictograms match whole tokens (`ir` no longer matches `mirar`). |
| H42/H65 | `hooks/useSymbolHunt.ts`, `store/notificationsStore.ts`, `tests/notificationsStore.test.ts` | Exiting the game cancels queued speech; notification read-state rolls back when the sync fails (`markAsRead` restores the prior flag, `markAllAsRead` restores only what it flipped) with specs. |
| H43/H64 | `components/Sidebar.tsx` | Preload loaders moved to a module map and each `import()` gets `.catch(() => {})`, so a failed chunk is a silent skip rather than an `unhandledrejection`. |
| H44/H45/H64 | `components/students/GuardianProfileModal.tsx`, `components/symbols/SymbolGrid.tsx`, `components/Navbar.tsx`, `components/learning/{LearningMessageList,LearningSymbolPanel}.tsx`, `hooks/useHoverSpeak.ts`, locales | Safety select falls back to the empty option (no blank, no `'default'` value that has no option); bulk checkbox is named after the symbol; the bell announces the unread count and `aria-expanded`; edit/report buttons are keyboard/touch reachable (`focus-visible:opacity-100`, visible below `sm`); utterance-chip remove labels are parameterized with the symbol; hover-speak also uses `onFocus`/`onBlur`. |
| H46/H66 | `api/spa.py`, `pages/Login.tsx`, locales | `/API/...` is casefolds to a JSON 404 instead of serving the SPA shell; the unreachable first-run banner (which navigated in the same tick) is deleted along with its two now-unused keys. |
| H47 | `routers/board_helpers.py` | Translation failures degrade to the source text instead of failing every board read (one warning, degraded-not-dead). |
| H48 | `providers/local_tts_provider.py` | The downloaded model and voices assets are pinned by exact size and SHA-256, and the voices archive is loaded with `allow_pickle=False`; tampered/truncated assets are rejected before ONNX/numpy loading. |
| H49 | `services/arasaac.py` | Downloads stream under a hard byte cap and the search fallback is narrowed to transport/404 (structural payload changes surface instead of returning `[]`). |
| H50/H51/H52/H53/H55 | (duplicates of H31/H29/H34/F4) | Verified landed in the tree; no second change. |
| H56 | `scripts/smoke_live.py`, `scripts/migrate_passwords.py`, `scripts/verify_pr.py`, `routers/config.py` | The smoke closes its server-log handle before `rmtree` (Windows cleanup); `migrate_passwords` raises instead of `sys.exit` inside a library function and `main` maps it to a code; the markdown-link check strips fenced code blocks first; `routers/config.py` is **deleted** (with its import/route registration, the E2E mock and the test reference) — no production consumer existed and it exposed `OLLAMA_BASE_URL` unauthenticated. |

## Tier Q/R — frontend depth, second wave

| ID | Files | Change + evidence |
|---|---|---|
| H57 | `store/boardStore.ts`, `tests/tierQrHardening.test.ts` | A failed duplicate removes the half-copied board (best-effort delete, original error surfaced). Spec: mid-copy failure → `DELETE /boards/99`. |
| H58 | `pages/{Register,UserManagement,Symbols}.tsx`, locales | Register has a confirm field, `minLength={8}` and client-side checks; the roster reload runs *after* the success toast in its own try (a failed reload no longer reports a successful create as a failure); a failed image upload is reported as "details saved, image failed" rather than a total failure. |
| H61 | `lib/format.ts`, `tests/format.test.ts` | Malformed timestamps render a fallback string instead of throwing `RangeError`. |
| H62 | `pages/Students.tsx`, `pages/Achievements.tsx`, `lib/learningTopics.ts`, `tests/tierQrHardening.test.ts` | An applied board assignment is reported against its own mutation id (and refreshes the roster) instead of returning silently; awarding requires a selected student (and an achievement id); legacy board-less saved topics are filtered out and the unusable key is dropped instead of aborting the whole migration queue. |
| H64 | (a11y list above) + `src/main.tsx` | Covered by the H37/H43/H44/H45 rows. |
| H66 | `pages/Login.tsx`, `api/spa.py` | As above. |

## Verified, then disproved / bounded (no production change)

| Item | Finding |
|---|---|
| H3 "double-use → 401" | Rotation and replay detection are implemented, but a **30 s grace window** deliberately accepts a *duplicate in-flight* exchange (two tabs) — a documented, test-pinned trade-off. Replay **after** the window returns 401 and revokes the family, which the live walk verified end-to-end. Reported as a policy deviation from the item's literal wording, not as a defect. |
| H48 sha256 pinning | The repository's exact Kokoro v1.0 assets were hashed locally and their size/SHA-256 values are now pinned in `local_tts_provider.py`; both cached and downloaded files are verified before loading. |
| H24 lifespan isolation | Making every `client` test run the lifespan surfaced two real, pre-existing defects in the suite (both fixed, see "Defects found" below) and required the index worker to honour the existing TESTING guard. |
| LLM-dependent learning paths | With no reachable provider, `/learning/{id}/end` returns a clean `400` with a body and a server-side ERROR log (`Failed to connect to Ollama`). Observed and reported; not changed, since the mapping predates this backlog. |

## Defects found by running the full named suite (pre-existing, now fixed)

1. `tests/test_acceptance_gaps.py::TestLearningHistoryTruncation` called `export_data()` with the
   pre-A8 signature (`TypeError: missing 1 required positional argument: 'request'`). Both tests now
   pass a minimal `Request`; they were failing on the untouched baseline.
2. `tests/test_board_assignment.py::test_concurrent_assignment_requests_are_idempotent` read the
   fixture's **expired** `student.id` inside two worker threads, so a concurrent write-lock could
   invalidate the shared (not thread-safe) session's lazy refresh → `ObjectDeletedError` /
   `IndexError` (≈1 run in 3, independent of this pass). The ids are now read on the main thread
   before the threads start; 3 consecutive runs are clean.
3. `tests/test_arasaac_routes.py` asserted the upstream search URL without clearing the new
   process-wide search cache, so a cache hit could skip the call under test. An autouse fixture now
   clears it around each test (isolation lives in the tests, not in the cache).

## Live-server walk (§9 fallback: real uvicorn + curl, isolated DATA_DIR)

No browser tool exists in this environment, so this is explicitly **not** GUI validation: the real
API was started on `127.0.0.1:8086` against a temporary `DATA_DIR` with `TESTING=0` (so the real
limiters are active), `ENVIRONMENT=development`, `AAC_SEED_SAMPLE_DATA=true` and a synthetic
bootstrap password; demo accounts `admin1`/`teacher1`/`student1` were logged in as three roles.
**39/39 checks passed**, and the port was closed afterwards (no listeners on 8086/5176, no
`uvicorn`/`vitest`/`playwright` processes left, `git stash list` empty).

Checks, in order: `GET /api/health` 200 · `GET /api/auth/setup-status` 200 · `GET /api/config` 404
(deleted dead router) · `GET /API/health` JSON 404 (casefold) · `GET /` serves the SPA ·
`POST /api/auth/token` for admin1/teacher1/student1 (form-data) · login returns a `refresh_token` ·
`GET /api/auth/me` 200 · board create → read → list · `GET /api/boards/symbols?query=mirar` and
`?query=algo` 200 (H63 shapes) · `symbols/categories` 200 · symbols over-cap 422 ·
`POST /api/learning/start` with a 100-char topic 200 (H25) · injection-shaped `difficulty` 422 (A5) ·
symbol answer handled cleanly (400 with a body; no provider reachable) · `/learning/{id}/end`
degrades cleanly (400 + server-side ERROR log) · `GET /api/learning/history` 200 (A11) ·
achievements over-cap 422 and paged 200 (E2) · `GET /api/notifications?user_id=1` 200 ·
`GET /api/data/export` 200 (A12/H12) · student `POST /api/arasaac/import` 403 (E1) · lockout →
`POST /api/users/reset-password` 200 → immediate login 200 (H7) · warmup unknown target 400 →
burst 429 (A4) · `DELETE /api/boards/{id}` 200 · refresh rotation (new access token, rotated
refresh token) → duplicate inside the grace 200 → **after** the 30 s window replay 401 and the
successor also 401 (H3 family revocation) → invalid refresh token 401.

Not walkable without a browser (still open for the human QA pass): rendered UI behaviour, console
errors per flow, keyboard-only traversal, devtools offline/500 injection, locale switching on
every visited page, and the two-window collab session. The API-side equivalents above cover the
endpoints those flows call.

## Gates

* Backend: `uv run ruff check src tests scripts` clean · `python -m compileall -q src scripts`
  clean · `python -m compileall -q launcher.pyw` clean · `git diff --check` clean ·
  **≈1 195 tests green** across named files (41 API/route files + the new
  `test_tier_k_fixture_lifespan`/`test_tier_lm_hardening`/`test_creation_lockout_reset`/
  `test_refresh_rotation`/`test_symbol_field_bounds`/`test_tier_h_limits_bounds` files), including
  the previously failing `test_acceptance_gaps` export tests and the flaky concurrency test.
* Frontend: `npm run typecheck` 0 · `npm run lint` 0 · `npm run i18n:audit` clean ·
  `npm run build` OK within budget (largest JS 398.8 kB / 450 kB, CSS 140.9 kB / 150 kB) ·
  **927 Vitest specs green** (the whole suite, run in named batches) including the new
  `tierQrHardening` file (6 of its 8 specs fail on the pre-fix stores) and the updated
  `Register`, `Boards`, `notificationsStore`, `learningSymbolAudio` and `Boards.test` specs.
* No full-suite invocation without paths was used for Playwright/E2E; no E2E spec was run (no
  browser tool). No `.env`, `data/` or auth artifact was touched — every test and the live walk
  used temp directories.

## Manual-QA readiness checklist

| Line | Status |
|---|---|
| Live-GUI walk (§9) per flow | **OPEN** — no browser tool in this environment; substituted with 39/39 live-server `curl` checks (above) and stated as such |
| No console errors on any walked flow | **OPEN** — requires the browser pass |
| No known P1/P2 open | DONE — every Tier H–R item is fixed or explicitly bounded/documented; H48 now has exact size/SHA-256 verification. |
| Failing-first evidence for every Tier H–R item | DONE for the items changed in this pass (see rows); the PROMPT_4 tiers carry their §4 verdicts |
| Gates green (ruff, compileall, typecheck, lint, build in budget, named suites) | DONE |
| No background runners/servers left | DONE — audited; port 8086/5176 closed |
| No `.env`/DB/auth-artifact mutation | DONE — temp dirs + synthetic credentials only |
| External gates | **OPEN** by design: Windows packaging rehearsal, live Groq run, human beta/privacy review, live CI execution |

---

# PROMPT_5 §9 — live-GUI verification in a real browser (Chrome over DevTools Protocol)

The suite that shipped with the tree proves nothing about this pass, so the product was driven
in **real Google Chrome 153 (`--headless=new`) over the raw DevTools Protocol** — not
Playwright. Harness: `tmp/gui/{run.sh,cdp.mjs,lib.mjs,dom_helper.js,walk*.mjs}` (gitignored,
kept as the reusable harness; the one-off probes were deleted). Page-side helpers are loaded
verbatim from disk with `Page.addScriptToEvaluateOnNewDocument` — injecting them as template
literals silently mangles `\s+`, which had made text matching miss "Cerrar sesión".

Isolated backend per run: temp `DATA_DIR`/`LOGS_DIR`/`UPLOADS_DIR`, `ENVIRONMENT=test`,
`TESTING=1`, synthetic bootstrap credentials, seeded demo users (except the first-run walk,
which ran with `AAC_SEED_SAMPLE_DATA=false` + `AAC_BOOTSTRAP_ADMIN_ON_FIRST_RUN=false`).
Every walk starts the server, runs Chrome, and kills both in one shell invocation; no port
was left listening.

## Defect found and fixed (P2)

**Duplicating a seeded board always failed — and surfaced as an uncaught promise rejection.**
`boardStore.duplicateBoard` restored AI settings with
`{ai_enabled: true, ai_provider: base.ai_provider, ai_model: base.ai_model}` whenever the source
board had `ai_enabled`. Seeded/template boards (e.g. "Comunicación General") are `ai_enabled`
with **no provider/model**, so the API answered
`400 {"detail":"AI provider and model are required when AI is enabled"}`, the store then deleted
the half-copied board, and `Boards.tsx` called `duplicateBoard(...)` without handling the
rejection: two `Uncaught (in promise) AxiosError` entries in the console with no user-visible
result.

Live evidence before the fix (probe, `/boards`): `POST /api/boards/` (copy) → `POST
/api/boards/3/symbols` ×N → **`PUT /api/boards/3` 400 ×2** + uncaught AxiosError ×2.
Fix: `src/frontend/src/store/boardStore.ts` only restores AI settings when the source board
supplies both provider and model (the copy keeps AI off instead of failing), and
`src/frontend/src/pages/Boards.tsx` follows the existing `confirmDeleteBoard` convention
(swallow the rejection; the store's `error` banner is the single user-facing report).
Live evidence after the fix: same flow, **no `PUT`, zero 4xx/5xx, zero exceptions** (probe17);
the board copy and its symbols are created.
Regression tests: `tests/boardStoreCrud.test.ts` — "copies a board whose AI flag has no
provider/model configured (live-GUI finding)" (fails on the pre-fix store: verified by
stashing the store change) and "still restores AI settings when the source board has a
provider and model".

## Flows walked (all as three roles where the role applies)

| Flow | Result |
|---|---|
| Anonymous `/` and `/boards` | redirect to `/login` |
| Unknown route | localized NotFound view (no crash) |
| Register | mismatch error "Las contraseñas no coinciden."; `<8`-char password blocked by `minlength` (`validity.tooShort`); duplicate username → 400 + "Nombre de usuario ya registrado" |
| Login admin1 / teacher1 / student1 | real typing + click; session persisted; input pipeline verified after each login |
| Shell route sweep (10 admin, 5 teacher, 5 student routes) | all render with content; zero console errors except the two environmental ones below |
| Role gates | teacher → `/admins` and student → `/symbols` `/students` both redirect to `/` |
| Logout | lands on `/login`, `auth-storage.token` cleared (all three roles) |
| Expired access token | tampered JWT → silent refresh, new token, stays on `/boards`, never a `/login` bounce |
| Boards list | seeded list, search filters and clears, broken deep link `/boards/999999` degrades to a rendered page with one expected 404 |
| Board create + duplicate | create works (`#new-board-name`); duplicate copies symbols (defect above fixed) |
| Board editor | tiles are `@dnd-kit` draggables; a real pointer drag (`grab` cursor tiles) succeeds; per-symbol remove keeps UI/server consistent after reload |
| Two-tab collab | second tab opens the same board; WebSocket collab session authenticated (`WS connected to board 1`); no errors while both tabs run |
| Symbol library | 34 bulk checkboxes each carry a screen-reader name ("vaca", "caballo", …); usage filters and "Eliminar seleccionados" reachable; "Editar" populates the inline form with the symbol ("vaca") and reveals Guardar/Cancelar |
| Learning | session starts with a 100-char topic; with the LLM provider unavailable the question fails **visibly** and the draft `¿Qué es un perro?` is preserved; history panel opens |
| Achievements | page and "Gestionar/Buscar nuevos" work; duplicate-named entries render |
| Symbol Hunt | starts, exits, back to a clean page; TTS unavailability reported as "Kokoro TTS is selected but unavailable; no speech was produced." |
| Locale switch | `#language-switcher` es-ES ⇄ en-US across `/`, `/boards`, `/learning`, `/settings`: English labels render, **no untranslated keys**, switching back works |
| Dashboard | streak card renders |
| Settings / data | export downloads a real file (`aac-data-admin1.json`, 7 769 B); a malformed import is rejected with "Exportación no válida: falta meta"; model-list 503 (no Ollama in this env) is surfaced both as an inline `modelError` and a toast |
| Notifications | bell opens with the full payload; "mark all" clears the badge and it stays cleared across a reload; **0 stream 429s across 6 single-tab reloads** |
| Students / user management | create dialog present with validation; per-student actions reachable incl. "Restablecer contraseña para student1"; board assignment panel opens |
| Offline toggle | devtools offline/online round trip with no console errors |
| Failure injection (devtools request blocking `*/api/boards/`) | visible banner "Algo salió mal … Network Error Reintentar", entered name preserved, and the retry after unblocking succeeds |
| Oversized upload | 30 MB PNG rejected with "Archivo no válido. Debe ser una imagen de menos de 5MB." |
| First-run setup (fresh DB) | `/` → `/setup` (`setup_required: true`); banned/near-default password rejected ("No se pueden usar credenciales predeterminadas"); mismatch rejected; strong bootstrap → dashboard; the new admin logs in again |
| Keyboard-only pass | login via Tab/Tab/Tab + Enter (order username → password → submit); 16 named, visibly focused stops in the shell and 14 per page on boards/editor/learning/settings/achievements; **zero icon-only buttons without an accessible name** on `/communication` and the board editor |

### Environmental console noise (not defects)
* `503 /api/settings/ai/models/ollama` — no Ollama daemon in this environment; the UI shows an
  inline error plus a toast ("Ollama service is not available…").
* `Kokoro no está preparado…` — the optional voice model is not installed for these runs.
* `429 /api/notifications/stream` — only when the harness accumulated ≥5 simultaneous tabs for
  one user, i.e. the intended per-user stream cap. Six consecutive single-tab reloads produced
  zero 429s, so this is not a subscriber leak.

### Disproved (checked, not changed)
* A locale switch appeared to send `{"ui_language": ""}` → 400. The switcher's options are
  `es-ES`/`en-US`; the empty value only occurred because the probe forced an unmatched select
  value, so the state is unreachable through the UI. Switching with the real option values
  produced no failed request.
* The login page's "Configuración inicial" notice is gated on `res.data.setup_required`
  (`Login.tsx:29`); the earlier sighting was the register page. No dead banner.

### Still open (external)
* Happy-path LLM flows (learning Q&A, board AI suggestions, predictions) need a real Groq key —
  the `playwright.verify.config.ts` Groq spec covers those and was not run here.
* Windows packaging rehearsal, human QA/beta review, and a live CI run remain open.

---

## Pass 3 (2026-09-13) — live Groq + real-browser verification of the remaining open items

Closes the "still open (external)" row that was blocked on a browser driver and a live LLM key.

### P1 — `schema.ensure()` aborted on any database holding the sqlite-vec table

* **Found by:** starting the real server against a *copy of the working dev database* (every
  earlier run used a fresh temp DB, which is why this was never seen here).
* **Symptom:** `Failed to initialize database: (sqlite3.OperationalError) no such module: vec0
  [SQL: PRAGMA main.table_xinfo("symbol_embeddings")]` → `ensure()` aborts → **no additive
  migration runs** → the app 500s on every `user_settings` read
  (`no such column: user_settings.tts_local_speed`) and `/ready` reports
  `vector_store: false`. The dev database itself was missing `tts_local_speed`,
  `hover_speak_enabled`, `hover_speak_delay_ms` and `default_learning_mode`.
* **Cause:** the dialect-portable reflection added in this pass (`_table_columns`) reflects
  *every* table; a `vec0` virtual table can only be reflected when the extension is loaded on
  the inspecting connection, which startup schema management never does. The previous
  `PRAGMA table_info(<known table>)` loop only touched tables in the additive list, so it never
  hit the vector table.
* **Fix:** `_reflected_columns()` / `_reflected_indexes()` in `src/aac_app/schema.py` skip
  tables the inspecting connection cannot reflect (logged at DEBUG). Virtual tables carry no ORM
  columns to migrate, so nothing is lost — and the remaining upgrades now always run.
* **Evidence (fail-before / pass-after):**
  * Before: `schema.ensure()` on a copy of the dev DB → `OperationalError: no such module: vec0`;
    `/ready` `vector_store:false`; login → 500.
  * After: `ensure()` OK, `DB upgrade: adding user_settings.tts_local_speed` (and the three
    other columns) logged, `missing after ensure: []`; live server `/ready`
    `{"ready":true,...,"vector_store":true}`; login and every walked flow succeed.
  * New regression test `tests/test_schema_migrations.py::test_schema_ensure_upgrades_databases_with_the_vector_table`
    (creates the `vec0` table exactly as the vector store does, then asserts `ensure()` succeeds
    and the columns are added). Fails with the strict comprehension (`OperationalError`,
    `FAILED`) and passes with the tolerant one.

### Live Groq verification (real key, real server, real browser)

Server: `uvicorn src.api.main:app` on 127.0.0.1:8086, `ENVIRONMENT=development`, `TESTING=0`,
temp `DATA_DIR` seeded from a copy of the working dev DB (key/model reused from
`app_settings`; the original DB is opened read-only and never modified).

* `npx playwright test --config=playwright.verify.config.ts` → **2/2 passed**
  * *settings UI configures Groq and reports healthy* — types the key, refreshes the model list
    from Groq with the request-scoped header, selects `openai/gpt-oss-20b`, auto-save persists
    `provider=groq`, **Provider Health reports "Groq: ok"** (live API).
  * *learning: starts a session and receives a real Groq question* — now starts from the topic
    picker (see below) and asserts the `POST /api/learning/<id>/ask` response has
    `provider_used: "groq"` plus non-empty `question_text`/`choices`.
* Direct API walk (same server): `POST /api/learning/start` → `provider_used: groq`; `POST
  /api/learning/7/ask` → `¿Qué frase usas cuando quieres preguntar la hora?` with three
  Spanish choices, 0.38 s; `POST /api/boards/1/ai/suggestions` with the new `refine_prompt`
  bound → real topic-aligned items (Wake Up / Eat Breakfast / …), 0.47 s;
  `POST /api/analytics/next-symbol` → N-gram hits plus AI topic words marked
  `source: "ai"`, `is_generating: true`; `/ready` **4/4 providers**.

### E2E specs repaired (stale `learning-session-start` selector)

`e4b4f52` replaced the start-session button with the student-facing topic picker, leaving five
specs referencing a test id that no longer exists in `src/`. Updated to start from
`[data-testid^="topic-card-"]` (the shared flow in `groq-verify.spec.ts` too):

| Spec | Result (live, seeded DB, port 8088) |
|---|---|
| `learning-games.spec.ts` | 8/8 passed |
| `prediction-tiers.spec.ts`, `settings-modes.spec.ts`, `axe-accessibility.spec.ts` | 12/12 passed |
| `tts-warmup.spec.ts` | 4/4 passed |
| `groq-verify.spec.ts` | 2/2 passed (live Groq) |

`learning-games.spec.ts::should play symbol hunt` fails only against an *unseeded* database
(no demo board → no "Play Now"); it passes on the seeded DB the spec documents, so this is
environment data, not a regression.

### Gates re-run after these changes

`uv run ruff check src tests scripts` clean · `python -m compileall -q src scripts` OK ·
`git diff --check` clean · `tests/test_schema_migrations.py`,
`tests/test_schema_db_bounds.py`, `tests/test_user_achievements_unique_migration.py`,
`tests/test_startup_warmup.py`, `tests/test_prod_sweep4_backend.py`,
`tests/test_api_comprehensive.py`, `tests/test_tier_k_fixture_lifespan.py` all green ·
frontend `npm run typecheck` clean · `npm run build` in budget (398.8/450 kB JS).
All ad-hoc servers/browsers were killed; no runners left behind.

### Still open (external, unchanged)

Windows packaging rehearsal on real Windows, human QA/beta review, and an actual CI run of the
production gate remain open — none of them can be executed from this Linux sandbox.

---

## Live-Groq re-verification (2026-09-14)

Re-ran the documented procedure from `AGENTS.md` against the working dev database on a fresh
invocation: server `uvicorn src.api.main:app` on 127.0.0.1:8086, key extracted from
`app_settings` at runtime (never echoed), model `openai/gpt-oss-20b` (the DB-persisted value).

* `GET /api/health` → **200** after ~2 s; `/ready` → `{"ready":true,...}` with **4/4 providers**
  (`speech`, `llm`, `achievement`, `vector_store` all true).
* `npx playwright test --config=playwright.verify.config.ts` → **2/2 passed**
  (settings UI configures Groq + "Groq: ok" health; learning session receives a real Groq
  question with `provider_used: "groq"`).
* Server log leak scan: **0** occurrences of the raw key, **0** `refresh_token=` in request
  targets (F03 transport check). Server killed in the same invocation; no runners left.

This re-confirms on the current tree: F09 log hygiene and F03 refresh transport on a live
server, plus the F10/F16 provider resolution and readiness behavior.

## Pass 3b (2026-09-13) — E2E audit: stale selectors & data assumptions

Method: (a) a static audit that resolves every `data-testid`/`#id` selector used by the 39 specs
against `src/` (`tmp/gui/audit_testids.py`, `tmp/gui/audit_ids.py`), and (b) two full live runs of
the suite — **seeded** (`AAC_SEED_SAMPLE_DATA=true`, the CI e2e job) and **clean/unseeded**
(production-gate shape, demo users provisioned through the API with `E2E_PROVISION_VIA_API=1`).

### Seeded run: 9 failures before, 253/253 green after

| Spec | Root cause | Fix |
| --- | --- | --- |
| `admin.spec.ts`, `data-management.spec.ts` | "server export" button no longer exists — the client/server exports were collapsed into one action and the file lost its `-server` suffix | match `/export my data\|exportar mis datos/i` and `^aac-data-.+\.json$` |
| `auth.spec.ts` (register) | `getByLabel(/password\|contraseña/i)` now resolves to **two** inputs (register confirms the password) → strict-mode violation; the confirm field was also never filled | fill `#password` + `#confirmPassword` |
| `teacher-student-provisioning.spec.ts` | index-based fills (`inputs.nth(3)`) pointed at the wrong field once the confirm input was added, so client validation blocked the POST | fill by id (`#create-student-password`, `#create-student-confirm-password`) |
| `llm-integration.spec.ts` ×2 | still clicked the removed page-level start button; one mocked a fixed `topic: 'general conversation'` that the picker no longer sends | start from the topic picker; assert topic is non-empty, purpose/mode_key unchanged |
| `learning-topics.spec.ts` | scoped assertions to `page.locator('.space-y-2').last()`, which no longer wraps the saved-topic list; clicked a removed page-level "Start Session" | new `data-testid="saved-topics-list"` on the sidebar list + the saved topic's "Start study" action |
| `ai-hot-reload.spec.ts` | started no session (the start button was gone), so the message was never sent and `expect(input).not.toBeEmpty()` passed **vacuously** | start from the picker; assert the failed send surfaces a `role=alert` error |
| `session-and-board-lifecycle.spec.ts` | **logged out the shared `admin1` session**, which revoked its access tokens server-side, so `playwright/.auth/admin.json` became invalid and 15+ later specs were redirected to `/login`; also used hardcoded English button names | the isolation test now signs out a disposable API-provisioned admin (`e2e_iso_admin_*`); labels match both locales |
| `contrast-interactive.spec.ts` | hardcoded `/boards/1` — a clean database has no board 1, so the audit ran against the 404 page | resolve the id through the API and `test.skip` with an explicit reason when the account has no board |

Evidence: seeded `--shard=1/2` **135 passed**, `--shard=2/2` **118 passed** (was 237 passed / 9
failed / 4 did not run).

### Clean/unseeded run: 253 tests → 108 + 127 passed, 14 failures, all seed-data only

Every remaining failure asserts the seeded demo board (`Comunicación General`) or its `student1`
assignment: `accessibility.spec.ts` (2), `communication.spec.ts` (4), `pilot-gate.spec.ts` (2),
`board-assignment.spec.ts`, `advanced.spec.ts`, `learning-games.spec.ts` (symbol hunt),
`learning-topics.spec.ts`, `students-lifecycle.spec.ts`, `extended-features.spec.ts`. These are
inherent to the design (the specs document the seeded demo data) and the production gate avoids
them by selecting `--grep "smoke|auth"`; `contrast-interactive.spec.ts` now skips its board-editor
audits on a clean database (4 skipped, 15 passed) and runs all 19 when seeded.

Before the isolation fix the same clean run had **23** failures in shard 2 — 15 of them were the
`/login` cascade caused by one spec signing out the shared admin, not data.

### Pre-existing breakage found by the static audit

* `boards.spec.ts` probes `debug-user-id`, a test id that no longer exists in `src/`. The probe is
  wrapped in `isVisible()`, so it never fails — it is dead debug code (left in place, flagged here).

### Documentation

`docs/MAINTAINER_GUIDE.md` §1b now lists the seed-dependent specs, states that the unseeded
production gate must not run them, and records the four E2E isolation rules learned here (never
sign out a shared account, no index-based form fills, no bare layout-class scoping, match labels
bilingually). Markdown link check re-run: 87 files, 0 broken links.

---

## Pass 3c (2026-09-13) — `e2e-clean` CI job: unseeded E2E coverage

The audit in Pass 3b showed that the seeded `e2e-production-compat` job cannot see defects that
only appear when the database has no demo data (that run is where the `user_settings` migration
abort, the dead `learning-session-start` selectors and the shared-session cascade were all
invisible). The only unseeded job was `e2e-production-gate`, which runs just `--grep "smoke|auth"`.

* **Tag:** the 14 demo-data tests in 9 specs now declare Playwright's `{ tag: '@seed-required' }`
  (`accessibility` ×2, `communication` ×4, `pilot-gate` ×2, `advanced`, `learning-games`,
  `learning-topics`, `students-lifecycle`, `extended-features`, `board-assignment`). Tags are inert
  without a filter, so the seeded job still runs all 250 tests (`npx playwright test --list`).
* **Job:** `.github/workflows/ci.yml` gains `e2e-clean` — `ENVIRONMENT=test`, **no**
  `AAC_SEED_SAMPLE_DATA`, `E2E_PROVISION_VIA_API=1`, its own `.ci-e2e-data` directory, and
  `npx playwright test --grep-invert @seed-required` (236 of 250 tests).
* **Guard test:** `tests/test_prod_sweep4_backend.py::test_e2e_clean_job_runs_the_unseeded_subset`
  parses the job and asserts it stays unseeded, provisions through the API, keeps the
  `@seed-required` exclusion, and that at least one spec still declares the tag (so the filter can
  never become a no-op). Fails when the job is switched back to `AAC_SEED_SAMPLE_DATA: "true"`
  (verified), passes restored.
* **Also fixed by running the new selection:** `pilot-gate.spec.ts`'s "token captured before UI
  logout is rejected afterward" asserted synchronously on the first `/api/auth/me` call. Since A16
  logout clears local state synchronously and revokes best-effort, the UI can reach `/login` before
  the revocation is processed — the clean run caught it as `200` instead of `401`. The assertion now
  uses `expect.poll(..., 15000)` so it tests the guarantee (the token is revoked) rather than the
  timing.

**Evidence (live, clean DB, exactly the new job's selection):**
`--grep-invert @seed-required --shard=1/2` → **127 passed**;
`--shard=2/2` → **108 passed, 4 skipped, 0 failed** (exit 0). Tagged selection resolves to exactly
the 14 known seed-dependent tests (`npx playwright test --list --grep @seed-required`).
`pilot-gate.spec.ts` run alone unseeded → 12 passed / 2 `@seed-required` failures.

**Docs:** `docs/MAINTAINER_GUIDE.md` records the new job in the required-jobs list, the tag, and the
local commands for both subsets. Markdown link check: 87 files, 0 broken links.

---

## Pass 3d (2026-09-13) — demo data built by the specs: `@seed-required` removed

Pass 3c's tag worked, but it meant 14 tests never ran against a clean database — exactly the shape
that had hidden the migration abort. The tag was a workaround for the real problem: those specs
assumed *someone else* had created the demo board. They now create it themselves.

* **Shared fixture:** `src/frontend/e2e/demo-fixture.ts::ensureDemoBoard(request)` logs in as the
  E2E admin and builds the same shape `seed.py` produces — a 3x4 board named `Comunicación General`
  (`POST /api/boards?user_id=<admin>`, first 12 catalog symbols from `/api/boards/symbols` at the
  seed's 3x4 placement) — then assigns it to `E2E_STUDENT_USERNAME` via
  `POST /api/boards/{id}/assign`. It reuses a seeded board when one exists, so the seeded
  `e2e-production-compat` job sees no change.
* **Specs switched to the fixture (9):** `accessibility`, `communication`, `pilot-gate`,
  `board-assignment`, `advanced`, `learning-games`, `learning-topics`, `students-lifecycle`,
  `extended-features`, plus `contrast-interactive` (its four board-editor audits previously skipped
  on a clean DB; the defensive `test.skip` stays only as an API-shape guard). Every `{ tag:
  '@seed-required' }` is gone.
* **Job simplified:** `e2e-clean` now runs `npm run verify:prod-build && npx playwright test` — the
  whole suite, no filter. The guard test
  (`test_e2e_clean_job_runs_the_unseeded_suite`) asserts the job stays unseeded, provisions through
  the API, runs the full suite with **no** seed-based selector, that no spec declares
  `@seed-required` any more, and that at least one spec still uses `ensureDemoBoard` (so the
  clean-database coverage cannot silently disappear).
* **Login-budget defect found while wiring it up:** the fixture logs in on every call, and
  `/api/auth/token` is limited to 10 requests/minute per IP, so the demo specs starved the auth
  specs — `auth.spec.ts` register/logout failed with `429 Too Many Requests` presented as
  "Registration failed: Rate limit exceeded". The session is now memoized per worker (one login,
  and the board lookup stays idempotent per call). The memoized token can still be revoked mid-run:
  `settings.spec.ts` changes the admin password, which bumps the JWT security version and
  invalidates earlier tokens. The fixture therefore drops the cached session and retries once on
  `401` (`StaleSessionError`), which is exactly what the clean run hit in `students-lifecycle`.
* **Second defect the clean run surfaced:** `prediction-tiers.spec.ts`'s `KNOWN_SOURCES` allow-list
  was stale — it was missing the real `topic` and `ai` tiers that `PredictionService` emits, so a
  prediction from the topic tier failed the assertion. The list is complete now, and
  `src/frontend/tests/e2eConfigHygiene.test.ts` pins it against the `source="…"` literals in
  `src/aac_app/services/prediction_service.py` (fail-before verified: dropping `topic` from the list
  fails with `expected [ 'topic' ] to deeply equal []`).
* **`llm-integration.spec.ts`:** the learning-area test started from the *first* topic card, which is
  a saved topic once the demo board exists (its `purpose` is the board name, not `practice`). It now
  selects a built-in catalog card, keeping the `purpose: 'practice'` / `mode_key: 'default_mode'`
  contract assertions meaningful.

**Evidence (live, sharded full suite):**

| Data shape | `--shard=1/2` | `--shard=2/2` | Total |
| --- | --- | --- | --- |
| **clean** (`AAC_SEED_SAMPLE_DATA=false`, accounts via API) | 135 passed | 118 passed | **253 passed, 0 failed, 0 skipped** |
| **seeded** (`AAC_SEED_SAMPLE_DATA=true`) | 135 passed | 118 passed | **253 passed, 0 failed, 0 skipped** |

Before this pass the clean run was 249 selected / 4 skipped / 0 failed with the tag, and the
untagged clean run was 12 failed in shard 1 alone. Guard test fail-before/pass-after verified by
re-adding a tag to `communication.spec.ts` (`AssertionError: specs still tagged @seed-required`).

**Gates:** `ruff check src tests scripts` clean · `compileall` OK · `git diff --check` clean ·
frontend `typecheck` + `lint` clean · `tests/test_prod_sweep4_backend.py` (41 tests) green ·
`tests/e2eConfigHygiene.test.ts` (4 tests) green · no leftover servers/browsers.

**Docs:** `docs/MAINTAINER_GUIDE.md` §1b now documents the fixture, lists the nine specs it serves,
states that seeding is optional, and drops the tag/filter instructions; the `e2e-clean` job comment
in `ci.yml` says nothing is filtered out.

---

## Final continuation audit — 2026-09-14 (H48/H49 re-check)

This pass re-checked the current working tree rather than trusting the earlier report. The H48
implementation and its documentation had diverged, and the newly added H48 tests had accidentally
left the dependency-unavailable assertions inside the preceding download test. Both issues were
fixed.

* **H48:** `local_tts_provider.py` now verifies the exact repository Kokoro v1.0 assets by pinned
  byte size and SHA-256 before cache reuse or atomic replacement. The voices archive is opened with
  `allow_pickle=False`; invalid, truncated, oversized, and same-sized tampered payloads are
  rejected before ONNX/NumPy loading. The recorded hashes were independently checked against
  `data/models/kokoro/*` without modifying that ignored model cache.
* **H49:** `ArasaacService.list_all_symbols()` streams and caps the catalog before JSON parsing;
  image downloads use the bounded stream path; malformed search payloads raise a diagnosable
  validation error instead of silently returning an empty result. Focused tests cover oversized
  catalog/image bodies and malformed search data.
* **Regression repair:** `test_provider_reports_unavailable_without_dependency` is again a
  separately collected test; the focused TTS/ARASAAC run collected **43 passed**.

Validation completed after the repair:

| Check | Result |
|---|---|
| `pytest tests/test_local_tts_provider.py tests/test_arasaac_routes.py` | **43 passed** |
| `ruff check src tests scripts` | Passed |
| `python -m compileall -q src scripts` | Passed |
| `npm run typecheck` | Passed (`tsc -b --noEmit`) |
| `npm run lint` | Passed |
| `npm run build` | Passed; largest JS 398.8 kB / 450 kB, CSS 140.9 kB / 150 kB |
| `git diff --check` | Passed |

The working tree still contains the broader uncommitted H–R sweep and untracked prompt artifacts;
this pass did not stage, commit, delete, or reset them. External release gates remain open:
Windows packaging/update/rollback rehearsal, GitHub Actions execution, human accessibility/privacy
acceptance, and any browser/live-provider verification not explicitly recorded above.

## PROMPT_6 pass — 2026-09-15 (B1–B12)

All twelve items implemented with discriminating regression tests (fail-before/pass-after where
practical). Every item was re-confirmed against the current tree before editing.

* **B1 — Single-use refresh for legacy/unknown tokens:** a presented refresh token with no ledger
  row (jti-less legacy or aged-out record) is accepted exactly once via a `security_version` bump
  (existing machinery, no parallel store), then every subsequent presentation is rejected. Family
  mismatches are treated as replay and trigger family revocation.
* **B2 — `delete_user` clears the refresh ledger:** the user's `RefreshTokenRecord` rows are
  removed with the account so no stale family can be resurrected.
* **B3 — `revoke_family` deleted:** zero production callers confirmed by a production-root search;
  the dead method (and its dead `fam` plumbing expectations) were removed rather than validated.
* **B4 — `duplicateBoard` stale-context cleanup:** every early return after the POST (context
  bump, missing `newBoardId`, missing local row) now deletes the just-created server board before
  returning; a stale path can no longer orphan a remote board.
* **B5 — Submit contract unified:** `submitAnswer`/`submitVoiceAnswer` rethrow after state reset;
  text callers clear input after the await and restore on failure; `useVoiceRecorder` keeps its
  never-reject contract for its button caller while `sendRecording` failures keep the recording.
* **B6 — Boards bulk-selection reset:** selection/`selectAll` reset on account switch
  (`user?.id` effect), and the header checkbox reflects partial selection (indeterminate +
  honest checked state); new i18n keys added for en/es.
* **B7 — Rate limits on heavy endpoints:** `@conditional_limiter` added to symbol create/upload,
  SVG generation, board generation, and import endpoints (with the slowapi-required `request`
  parameter), matching the existing authentication-endpoint coverage.
* **B8 — Communication TTS cancel on unmount:** pending/playing utterances are cancelled when the
  page unmounts; speech no longer continues after leaving the page.
* **B9 — SentenceStrip keyboard/AT semantics:** tile buttons carry `aria-label` (word + position),
  the strip is an ordered list region, and removal buttons expose accessible names.
* **B10 — Vector search fails closed:** store/translation errors during search now raise instead
  of silently returning a wrong-order empty/no-op result; callers already treat exceptions as
  degradation.
* **B11 — Input bounds:** `language` form field validated server-side (422 outside the supported
  set); `scripts/migrate_passwords.py` processes users in bounded chunks so large tables no longer
  load unbounded ORM rows at once.
* **B12 — Dead-code/test consolidation:** jti-less refresh-token minting removed from ten test
  sites (tokens now hit the ledger or explicitly simulate legacy tokens via the internal encoder);
  broken helper fixtures repaired; Ruff import hygiene fixed.

| Check | Result |
|---|---|
| `pytest tests/test_refresh_rotation.py tests/test_phase2_security.py tests/test_password_reset_security.py tests/test_prompt6_backend.py tests/test_tier_h_limits_bounds.py` | **56 passed** |
| `pytest tests/test_file_uploads.py tests/test_admin_user_management.py tests/test_local_vector_store_sqlite_vec.py tests/test_boards_list_symbols_and_achievement_routes.py tests/test_svg_symbol_generator.py` | **65 passed** |
| `pytest tests/test_account_normalization_regressions.py tests/test_creation_lockout_reset.py tests/test_operator_credential_revocation.py tests/test_security_comprehensive.py` | **40 passed** |
| `pytest tests/test_phase2_security.py` (post ruff --fix) | **24 passed** |
| Frontend `typecheck` / `lint` | Passed |
| Frontend named specs (8 files incl. new B4–B9 discriminating specs) | **178 passed** |
| `npm run build` | Passed; largest JS 398.8 kB / 450 kB, CSS 141.0 kB / 150 kB |
| `ruff check src tests scripts` / `compileall` / `git diff --check` | Passed |
| Stray uvicorn/pytest/vitest/playwright processes | 0 |

External release gates remain open: Windows packaging/update/rollback rehearsal, GitHub Actions
execution, human accessibility/privacy acceptance, and production-mode deployment smoke.

## Full consolidated gate — 2026-09-15 (`scripts/verify_pr.py`)

`uv run python scripts/verify_pr.py` run on this tree: **all 16 steps passed (exit 0)** — Ruff,
compileall, import audit, dependency-evidence audit, production + development `pip-audit` (no
known vulnerabilities), i18n key audit, full pytest with branch coverage (86% overall), frontend
typecheck/ESLint, production + development `npm audit` (no known vulnerabilities), full Vitest
with coverage (**107 files / 917 tests**), production build (JS 398.8 kB / 450 kB, CSS 141.0 kB /
150 kB budget), requirements consistency, and 88 markdown files with 0 broken links.

Two defects surfaced by the full backend suite were fixed before the passing run:

* **Guardian policy silently discarded on the collab path (pre-existing production bug):**
  `resolve_policy_for_user(user.id)` with `db=None` (the WebSocket collaboration route) read
  `profile.safety_constraints`/`profile.age` *after* the internal `get_session()` had committed
  and closed, raising `DetachedInstanceError` that the broad `except` swallowed — so teacher-set
  safety locks (e.g. `block_social_messaging`) never applied to collaboration messages. The
  resolver now snapshots plain values while the session is live (`_active_guardian_profile` /
  `_plain_constraints`), and `_age_level_policy` takes the age scalar. Regression: the previously
  failing `tests/test_collab_ws.py::test_collab_ws_block_social_messaging` now passes.
* **Stale fail-open `_strip_reasoning` test:** `test_learning_common_helpers.py` still encoded the
  old republish-on-empty behavior that the deliberate fail-closed change (and
  `tests/test_tier_lm_hardening.py`) superseded. The test now asserts the reasoning-only reply
  yields `""` and that surrounding whitespace is stripped.

One i18n audit failure was also fixed: the `removeSymbolLabel` key orphaned by the B9 aria-label
improvement (`removeSymbolNamed`) was deleted from both locales.
