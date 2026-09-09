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

## Completion requirements

1. Reproduce each source finding safely, implement the fix, and record its commit/files plus focused regression results under the corresponding ID. If current evidence disproves an item, document the concrete reason instead of implementing an unnecessary change.
2. Provision locked Python/frontend dependencies without broad upgrades. Run dependency evidence checks and the locked production/all-group Python and production/development npm vulnerability gates required by AGENTS.md. Track actual advisories; do not suppress them broadly.
3. Run required backend lint/compile checks and named affected pytest files; frontend typecheck/lint, named affected Vitest files, and fresh production build/bundle checks. Investigate incomplete focused tests with bounded execution and useful diagnostics.
4. Perform an isolated production-mode API smoke with actual `/ready` evidence and at most one or two named browser specs for changed critical flows. Obtain separate live-Groq evidence when configured and authorized. Preserve the real admin database and secrets.
5. Rehearse recovery using a disposable DB and matching uploads/config. Preserve existing migrations; schema changes require legacy-data fixtures and integrity/foreign-key checks. Keep signed-export compatibility obligations explicit.
6. Keep Windows artifact/update/rollback, representative AAC accessibility/hardware testing, and the documented human beta/privacy review as external release gates until actually performed. No agent may invent these outcomes.
7. Update every finding to fixed, disproved, or explicitly blocked with evidence. Run `git diff --check`. Audit and stop all task-owned runners/servers before handoff. Only claim production sign-off when the required evidence exists.

Only this handoff document is intended as the repository change from the audit. No production fixes, secret changes, or database modifications were authorized as part of the diagnosis pass.
