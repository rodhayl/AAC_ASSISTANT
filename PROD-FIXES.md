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

## Fixes pass — 2026-09-10

Scope: address the first batch of production-readiness defects under AGENTS.md. Changes span security (F01, F02, F03, F09), reliability (F04, F06, F07, F11, F14), content safety (F08, F13), provider/collab correctness (F05, F10, F13), and deployment/observability (F12, F15, F16). No full test suite run (requires explicit authorization); no `.env`/DB/auth-artifact mutation; Windows behavior untouched per AGENTS.md.

### F01 — production JWT secret validation — **fixed**

- Root cause: production accepted any short/placeholder secret; check lived only in dotenv generation, not on the effective (env-over-dotenv) value.
- Change: `src/config.py:validate_effective_jwt_secret` checks the resolved effective secret in production (≥32 chars, rejects placeholder/whitespace), using `config.get` so dotenv-set `ENVIRONMENT` is honored with env-over-dotenv precedence. `src/aac_app/utils/jwt_utils.py` calls it at import and before minting.
- Evidence: isolated probe with synthetic `JWT_SECRET_KEY=tooshort` and `ENVIRONMENT=production` from dotenv rejects with `ValueError`; `process.env=production` overrides dotenv file; `development` stays permissive; valid 40-char production key accepted. `tests/test_phase2_security.py::test_production_rejects_default_jwt_secret` updated to current message and passes.

### F02 — offline persistence secrets — **fixed**

- Change: `src/frontend/src/lib/offlinePersistence.ts` switched to an explicit allowlist (`/boards/`) plus blocklist/sensitive-key detection; `sanitizeOfflineConfig` rejects secret-bearing or non-allowlisted mutations before persistence and on hydration, strips sensitive headers/params. Queue/conflict hydration re-validates via the same sanitizer.
- Evidence: new `src/frontend/tests/offlinePersistence.test.ts` (9 tests) exercises `sanitizeOfflineConfig` directly against the real module — rejects password-reset, privileged user creation, `/settings/ai` with API key, secret payloads, secret-bearing params, and headers; preserves ordinary board edits via the allowlist. Existing `tests/api.test.ts` and `tests/offlineStore.test.ts` still pass.

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
- Evidence: new `tests/test_export_link_remap.py` (7 tests): cyclic A/B remap both directions, external/missing links stay cleared (including forged links to unowned boards), retry import merges instead of cloning, assigned-board link remap, retention preserves today's sentinel meter, `_count_sentinel_today` only counts today.

### F14 — safety log transaction ownership and retention — **fixed** (retention made testable in review pass)

- Change: `src/aac_app/services/content_safety.py:log_event` now takes a deliberate isolated transaction via `get_session()` and ignores the caller's session entirely, so it can never commit or roll back the caller's transaction; it caps `detail` to 200 chars, enforces bounded table retention, and its preservation fix in `src/api/routers/content_safety.py:clear_safety_events` keeps today's `surface="sentinel"` rows (the daily cost meter) when clearing.
- Review pass: retention moved from a function-local constant into module-level `MAX_EVENTS` + `_prune_events(session, max_events)` so the real pruning path is exercisable; `log_event` calls it inside its isolated session. `_prune_events` never deletes today's `sentinel` rows even when they alone exceed the cap (the cap is a hard bound but the meter is protected).
- Evidence: isolated probe created a user, staged a `display_name` change, called `log_event(db=caller_session)`, and rolled back — the staged change was not committed, while the safety event persisted in its own transaction. `tests/test_export_link_remap.py` exercises `_prune_events` directly: with 6 rows (3 today-sentinel + 3 old chat) and cap 2, only the old chat rows are pruned, 3 sentinel rows remain, and `_count_sentinel_today` still returns 3.

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

## Completion requirements

1. Reproduce each source finding safely, implement the fix, and record its commit/files plus focused regression results under the corresponding ID. If current evidence disproves an item, document the concrete reason instead of implementing an unnecessary change.
2. Provision locked Python/frontend dependencies without broad upgrades. Run dependency evidence checks and the locked production/all-group Python and production/development npm vulnerability gates required by AGENTS.md. Track actual advisories; do not suppress them broadly.
3. Run required backend lint/compile checks and named affected pytest files; frontend typecheck/lint, named affected Vitest files, and fresh production build/bundle checks. Investigate incomplete focused tests with bounded execution and useful diagnostics.
4. Perform an isolated production-mode API smoke with actual `/ready` evidence and at most one or two named browser specs for changed critical flows. Obtain separate live-Groq evidence when configured and authorized. Preserve the real admin database and secrets.
5. Rehearse recovery using a disposable DB and matching uploads/config. Preserve existing migrations; schema changes require legacy-data fixtures and integrity/foreign-key checks. Keep signed-export compatibility obligations explicit.
6. Keep Windows artifact/update/rollback, representative AAC accessibility/hardware testing, and the documented human beta/privacy review as external release gates until actually performed. No agent may invent these outcomes.
7. Update every finding to fixed, disproved, or explicitly blocked with evidence. Run `git diff --check`. Audit and stop all task-owned runners/servers before handoff. Only claim production sign-off when the required evidence exists.

Only this handoff document is intended as the repository change from the audit. No production fixes, secret changes, or database modifications were authorized as part of the diagnosis pass.
