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
| Q2 | **Fixed** | `src/frontend/src/store/authStore.ts` | `register` no longer bumps `checkAuthEpoch`; it captures the epoch and guards both its success-spinner and error sets against newer session owners | 2 new specs; both **fail on HEAD** |
| Q3 | **Fixed** | `src/config.py` (`refresh_query_fallback_allowed()`), `src/api/routers/auth.py` | One plain helper implements "explicit opt-in only"; the dead production branch and the duplicated lookups are gone. `grep` shows exactly one call site | D5 matrix tests green unchanged |
| Q4 | **Fixed** | `src/api/main.py` | `bounded_receive()` waits on `receive()` under a 25 s inactivity timeout; expiry resolves through the same overflow/abort path with a warning log carrying bytes + elapsed. Declared, chunked and stalled-mid-body shapes covered | stalled-body ASGI test (short injected timeout) aborts instead of hanging; 413 tests green |
| Q5 | **Fixed** | `src/api/deps/providers.py` (`resolve_groq_api_key()`), `src/api/routers/board_ai.py` | Public resolver exported and used by both callers; no private cross-module import remains | repo-wide search: no `_effective_groq_key` reference outside its module; key-matrix + singleton tests green |
| Q6 | **Fixed** | `src/api/routers/collab.py` | Comment rewritten to match the code (ignore the lifespan event outside lifespan; use a local event so tests never observe production shutdown) | comment/code agreement on re-read; collab tests green |
| Q7 | **Fixed** | `src/aac_app/services/learning/responses.py` | Guard now names both inputs (`not audio_data and not audio_path`); the path-only upload branch above is therefore never shadowed by a future edit | unit test for voice-with-neither-inputs; voice F07/D8 tests green |
| Q8 | **Fixed** | `src/aac_app/services/content_safety.py` | Throttle state starts at `None`; the first `log_event` of a process only opens the window instead of paying an unconditional full-table `COUNT(*)` | instrumented test asserts 0 prune calls on the first event, 1 on the Nth; **fails on HEAD** |
| Q9 | **Fixed** | `src/aac_app/services/content_safety.py::moderate_output` | Blank/whitespace output returns `Verdict(allowed=True)` with no `generate` call, no audit row and no meter spend; non-blank text keeps the full fail-closed path | counting-`generate` test: 0 calls / 0 rows for blank, 1 call for "texto normal"; **fails on HEAD** |
| Q10 | **Fixed** | `src/api/routers/export_import.py` | Outcome counts are measured as raw deltas (`boards_created`, `boards_merged`, `symbols_added`, `learning_history_added`) so a retry reports what it actually wrote | retry test asserts `created+merged == boards seen`; **fails on HEAD** |
| Q11 | **Fixed** | `src/api/logging_config.py::_redact_message` | Copula rule widened to `is|es` so the Spanish-first rendering `password es <valor>` is masked like the English form | new spec; **fails on HEAD** |

**Pre-fix baseline captured before the fixes** (HEAD production files restored, then restored byte-for-byte):
backend — `test_moderate_output_blank_text_costs_nothing`, `test_first_log_event_records_baseline_without_pruning`,
`test_spanish_copula_is_masked` all **FAILED**; frontend — **5 failed / 28 passed** (`tests/authStore.test.ts`
+ `tests/DataManagementTab.test.tsx`), i.e. the two Q1 and two Q2 specs plus the N5 spinner spec.
Q7's test is a guard, not a discriminator (the pre-fix condition was already behaviorally equivalent for
both-falsy inputs), and is documented as such rather than claimed as a fail-before.

Validation after the pass: `ruff check src tests scripts` clean · `compileall -q src scripts` clean ·
`git diff --check` clean · backend named files **252 passed** (`test_response_processing_helpers`,
`test_acceptance_gaps`, `test_content_safety`, `test_new_features`, `test_phase2_security`,
`test_groq_provider`, `test_logging_config`) · frontend `typecheck` 0 · `lint` 0 · Vitest
`authStore` + `DataManagementTab` + `offlinePersistence` + `api` **73 passed**.

## Completion requirements

1. Reproduce each source finding safely, implement the fix, and record its commit/files plus focused regression results under the corresponding ID. If current evidence disproves an item, document the concrete reason instead of implementing an unnecessary change.
2. Provision locked Python/frontend dependencies without broad upgrades. Run dependency evidence checks and the locked production/all-group Python and production/development npm vulnerability gates required by AGENTS.md. Track actual advisories; do not suppress them broadly.
3. Run required backend lint/compile checks and named affected pytest files; frontend typecheck/lint, named affected Vitest files, and fresh production build/bundle checks. Investigate incomplete focused tests with bounded execution and useful diagnostics.
4. Perform an isolated production-mode API smoke with actual `/ready` evidence and at most one or two named browser specs for changed critical flows. Obtain separate live-Groq evidence when configured and authorized. Preserve the real admin database and secrets.
5. Rehearse recovery using a disposable DB and matching uploads/config. Preserve existing migrations; schema changes require legacy-data fixtures and integrity/foreign-key checks. Keep signed-export compatibility obligations explicit.
6. Keep Windows artifact/update/rollback, representative AAC accessibility/hardware testing, and the documented human beta/privacy review as external release gates until actually performed. No agent may invent these outcomes.
7. Update every finding to fixed, disproved, or explicitly blocked with evidence. Run `git diff --check`. Audit and stop all task-owned runners/servers before handoff. Only claim production sign-off when the required evidence exists.

Only this handoff document is intended as the repository change from the audit. No production fixes, secret changes, or database modifications were authorized as part of the diagnosis pass.
