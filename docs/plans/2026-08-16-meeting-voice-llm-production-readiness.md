# Meeting, Voice, and LLM Production-Readiness Plan

**Date:** 2026-08-16  
**Status:** Ready for implementation  
**Scope:** Local-first AAC Assistant deployment; Windows packaged application and supported source checkouts

## Goal

Make the existing learning-conversation, voice-transcription, and LLM-assisted
features production-ready without introducing distributed infrastructure or a
new provider framework.

The product does not currently have a production `Meeting` domain. What users
experience as a meeting/conversation is implemented as a persisted
`LearningSession`. Real-time board collaboration is a separate, process-local
WebSocket room. Preserve that terminology and architecture unless product
requirements explicitly call for durable scheduled meetings.

## Current architecture

- `POST /api/learning/start` creates a `LearningPlan`, `LearningTask`, and active
  `LearningSession`.
- Questions, text answers, voice answers, symbol answers, progress, history, and
  completion are exposed by `src/api/routers/learning.py`.
- Conversation and transcript text is retained in the
  `LearningSession.conversation_history` JSON column, bounded to the newest 50
  entries by `src/aac_app/services/learning/history.py`.
- Browser voice capture uses `MediaRecorder`; the API streams a MIME/signature
  checked upload to a temporary file; faster-whisper transcribes locally; the
  temporary audio file is deleted after processing.
- Learning LLM calls generate questions, grade answers, create conversational
  replies, and summarize completed sessions.
- Board LLM calls generate boards and non-mutating suggestions; applying a
  suggestion is a separate mutation.
- Smartbar next-symbol prediction is a lightweight N-gram/statistical path, not
  an LLM path.
- LLM providers are Ollama, LM Studio, and optional OpenRouter. Model choice is
  application configuration and is unrelated to Codex's Sol/Luna agent models.

## Constraints

- Follow the repository `AGENTS.md`, especially its production-only reference
  rules and required validation commands.
- Inspect every production root at least once before changes and repeat the
  production-only reference/hotspot scan after each cleanup pass:
  `src/aac_app`, `src/api`, `src/config.py`, `src/scripts`, launch/packaging
  files, and `src/frontend/src`.
- Preserve external API and persisted-data compatibility unless production and
  documented external use have been ruled out.
- Keep optional voice, vector, and ML dependencies lazy and outside startup's
  critical path.
- Do not modify Windows launcher or installer behavior for this work.
- Prefer local fixes and deletion of verified dead code over new abstractions.

## Phase 1: Session and voice correctness

### 1.1 Enforce session lifecycle

Files:

- `src/api/deps/access.py`
- `src/api/routers/learning.py`
- `src/aac_app/services/learning/questions.py`
- `src/aac_app/services/learning/responses.py`
- `src/aac_app/services/learning/summaries.py`

Work:

- Add a shared active-session check used by question generation and all answer
  mutations. A completed session must not accept new questions or text, voice,
  or symbol answers.
- Keep progress/history readable after completion.
- Make repeated completion state-safe: it must not call the LLM again, change
  `ended_at`, or trigger achievements again. The lean compatible behavior is a
  stable `409 Conflict`/localized "already completed" response. Do not add a
  summary column migration merely to replay the first response unless product
  requirements demand replayable summaries.
- Make the completion transition concurrency-safe. Two simultaneous end
  requests must not both observe `active` and invoke the provider. Use a narrow
  per-session lock or atomic status claim/recheck; do not introduce a general
  job or locking framework.
- Recheck status inside the service mutation as well as at the route boundary,
  so internal callers cannot bypass the invariant.

Acceptance criteria:

- Ask/answer endpoints reject completed sessions without changing history or
  counters.
- A second end request leaves `ended_at`, counters, history, and achievement
  state unchanged and makes no provider call.
- Two concurrent end requests produce one completion/provider call and one
  stable already-completed response.
- Owner/admin authorization behavior is unchanged.

### 1.2 Correct and bound transcription

Files:

- `src/api/file_uploads.py`
- `src/api/routers/learning.py`
- `src/aac_app/providers/local_speech_provider.py`
- `src/aac_app/services/learning/responses.py`
- `src/api/schemas.py`
- `src/frontend/src/components/learning/useVoiceRecorder.ts`
- `src/frontend/src/store/learningStore.ts`

Work:

- Resolve the user's normalized locale before transcription and pass it to
  faster-whisper. Support at least `en` and `es`; fall back to automatic
  detection for unsupported/unknown language codes rather than forcing English.
- Run synchronous model inference outside the event loop using a bounded worker
  path. Retain the provider's existing model-use lock; do not introduce a job
  queue.
- Add a configurable maximum recording duration with a conservative default
  such as 120 seconds. Enforce it in the browser and server. Server validation
  should reuse PyAV to inspect/decode only as much as needed to establish the
  bound, with the transcription wall-time bounded as a backstop. Do not add an
  ffmpeg subprocess, polling API, or job infrastructure for this check.
- Keep the existing 10 MB upload, MIME allowlist, signature validation, and
  temporary-file cleanup.
- Add an explicit response field such as
  `transcription_status: "ok" | "unavailable" | "failed"`. Preserve existing
  response fields for compatibility.
- On unavailable/failed transcription, retain the localized graceful feedback
  but do not count an answer or schedule the next automatic question. Offer an
  explicit retry in the frontend.
- Request microphone permission before creating a new voice learning session.
  If later session creation fails, stop all acquired media tracks.
- Give the voice request a deliberate timeout longer than the generic 30-second
  Axios timeout, bounded consistently with the server's duration/inference
  budget. Do not add polling or asynchronous jobs.

Acceptance criteria:

- Spanish audio is submitted to Whisper with `es`, English with `en`, and an
  unsupported locale uses auto-detection.
- A long/invalid audio upload cannot occupy transcription indefinitely.
- Other API requests remain responsive during transcription.
- Denying microphone permission creates no learning session and leaves no live
  media track.
- Failed transcription does not advance question state or achievement counts.

## Phase 2: Provider and secret hardening

### 2.1 Make OpenRouter credentials write-only

Files:

- `src/api/routers/settings.py`
- `src/frontend/src/pages/Settings/AiProviderTab.tsx`
- `src/frontend/src/pages/Settings/AiProviderFields.tsx`
- related settings types/store and tests

Work:

- Never return a raw OpenRouter API key from GET or PUT responses, including to
  administrators. Return a boolean/configured marker or the fixed mask
  `********`.
- Replace the raw dictionary update body with a typed request model.
- Treat a missing key as "leave unchanged" and provide an explicit clear action
  if clearing is supported. Never persist the mask as the credential.
- Return a sanitized settings response after update rather than echoing the
  submitted body.
- Keep process-environment credential fallback working.

Acceptance criteria:

- No authenticated API response contains the stored secret.
- Editing unrelated AI settings cannot replace the secret with `********`.
- Logs, validation errors, and upstream failures do not contain the key.

### 2.2 Make provider support consistent and leak-free

Files:

- `src/api/routers/board_ai.py`
- `src/api/deps/providers.py`
- `src/aac_app/providers/base_provider.py`
- `src/aac_app/providers/lmstudio_provider.py`
- `src/aac_app/providers/ollama_provider.py`
- `src/aac_app/providers/openrouter_provider.py`

Work:

- Support LM Studio consistently in board creation and board suggestions, using
  `LMStudioProvider` and the configured LM Studio URL/model. Do not silently map
  LM Studio to Ollama.
- Use managed singleton providers where the global provider/model applies.
  Where a board-specific model requires a request-scoped client, close it in an
  awaited `finally` block on success, validation error, provider error, and
  client cancellation.
- Do not close shared singleton providers from request handlers.
- Stop logging raw upstream response bodies and prompt fragments. Log provider,
  model, status class, latency, and a request/correlation ID instead.
- Cap configurable `max_tokens` to a documented range, for example 64-4096.

Acceptance criteria:

- LM Studio board creation and suggestion calls target the LM Studio endpoint.
- Repeated board suggestion calls do not accumulate open HTTP transports.
- Provider errors exposed to clients are localized/sanitized and preserve the
  upstream status category without raw content.

## Phase 3: Bounded LLM contracts

Files:

- `src/api/schemas.py`
- `src/aac_app/services/learning/questions.py`
- `src/aac_app/services/board_generation_service.py`
- related tests

### 3.1 Bound user-controlled prompt inputs

Use conservative limits aligned with current database columns and UI needs:

- session topic: 1-100 characters, matching `LearningSession.topic_name`
- purpose: at most 1,000 characters
- difficulty/mode key: at most 50 characters and existing supported values
- text answer and enriched/raw gloss: at most 4,000 characters
- symbol label: at most 100 characters; symbol sequence count bounded
- context hint: at most 1,000 characters
- board refinement prompt: at most 2,000 characters
- suggestion description: at most 1,000 characters
- learning-mode prompt instruction: retain the existing 10,000-character limit
  unless representative prompts justify lowering it

Reject oversized input before invoking a provider.

### 3.2 Validate generated questions strictly

- Require a non-empty bounded question string.
- Require exactly three non-empty bounded string choices.
- Require `correct` to be an integer, not a boolean, in the range `0..2`.
- Reject extra nesting or incompatible types.
- Send invalid provider output through the existing strict retry and translated
  fallback path; never persist malformed question data.
- Keep parsing/retry logic local to the learning question module rather than
  introducing a general output framework.

### 3.3 Validate board-generated items strictly

- Require bounded non-empty `label` and `symbol_key` strings.
- Accept only a valid `#RRGGBB` color or replace it with the existing safe
  default.
- Deduplicate normalized labels and cap results to the requested item count.
- Any permissive recovery path must run through the same validator. Arbitrary
  prose or oversized bullet lines must not become symbols.
- Preserve partial valid responses; do not retry solely to fill every cell.

### 3.4 Validate other learning-model output

- Grading output must contain a real boolean `is_correct`, numeric finite
  `confidence` clamped or rejected outside `0..1`, and a bounded non-empty
  feedback string. A boolean must not be accepted as a numeric confidence.
- Bound the final conversational reply and session-summary strings before
  persistence/response. Invalid or empty output must use the existing localized
  fallback.
- Keep provider reasoning/prose stripping behavior, but never persist an
  unbounded raw provider response when parsing fails.

Acceptance criteria:

- Invalid/oversized user input returns `422`/`400` without a provider call.
- Malformed provider JSON cannot cause an index error or persist invalid data.
- Malformed grading, conversational, or summary output uses a bounded localized
  fallback and cannot persist incompatible types.
- Existing valid Ollama, LM Studio, and OpenRouter output remains supported.

## Phase 4: Resource controls and privacy-safe operations

### 4.1 Add local-process concurrency and rate budgets

Files:

- `src/api/limiter.py`
- learning, board AI, and provider routes
- provider dependency/lifecycle module as appropriate

Work:

- Add per-user/IP limits to voice transcription, question generation, answer
  generation/grading, completion summaries, and board AI generation.
- Add small in-process capacity limits for STT and LLM work so requests queue
  predictably rather than creating unbounded workers. Use the existing single
  process/local-first deployment assumption; do not add Redis.
- Return `429` or `503` with a localized retryable response when capacity is
  exhausted.
- Keep authentication's existing limiter behavior unchanged.

Suggested initial budgets should be documented and tested, not treated as
permanent tuning. Favor generous local-user limits with strict concurrency
bounds.

### 4.2 Shorten the clearest long transaction

- In board creation, perform provider generation and output validation before
  adding/flushing the new board and symbols. Recheck authorization/configuration
  immediately before the write transaction and commit the board atomically.
- Do not broadly rewrite learning persistence in this pass. If concurrent
  learning mutations are reproducibly losing updates, address them with a
  focused per-session serialization/optimistic check and a migration plan;
  otherwise defer that expansion.

### 4.3 Make production logging safe by default

Files:

- `src/config.py`
- `.env.example`
- `src/api/logging_config.py`

Work:

- Add a documented `LOG_LEVEL`, defaulting to `INFO`.
- Disable Loguru variable diagnostics and extended backtraces in production.
- Preserve existing process-safe file naming and 7/14-day log retention.
- Record timings, provider/model identifiers, result status, fallback reason,
  safe token counts/cost metadata where available, byte/duration counts, and
  request IDs without raw prompt, transcript, bearer token, API key, or upstream
  response content.

### 4.4 Clarify readiness

- Keep process readiness independent of optional voice/LLM availability so the
  core AAC application can run offline.
- Expose provider/model capability status separately and accurately: configured,
  reachable, model present, or unavailable. Avoid a mandatory network call on
  every health request; cache a short-lived probe result or expose an explicit
  authenticated diagnostic action.

## Phase 5: Documentation and regression coverage

### 5.1 Correct privacy documentation

Files:

- `docs/PRIVACY_AND_DATA.md`
- `docs/voice.md`
- `docs/THREAT_MODEL.md`
- `docs/RELEASE_READINESS.md`
- README/configuration reference where needed

Document accurately that:

- Raw learning voice uploads are temporary and removed after processing.
- Transcript text is stored inside learning-session conversation history in
  SQLite.
- Only the newest 50 conversation entries are retained per session by the
  application history helper, but the session itself persists until the user is
  deleted or data is explicitly reset/imported according to existing tools.
- OpenRouter receives the applicable prompt/context only when explicitly
  configured; the key is write-only in the UI/API.
- Operators remain responsible for backups, filesystem protection, cloud
  provider terms, and any required legal retention policy.

### 5.2 Required regression tests

Backend tests must cover:

- completed-session ask/answer rejection
- repeated end with no second provider/achievement call and unchanged timestamp
- STT locale propagation and unknown-locale auto-detection
- event-loop responsiveness during mocked slow transcription
- audio duration rejection and temporary-file cleanup
- explicit failed/unavailable transcription response
- OpenRouter secret masking on GET/PUT and masked-placeholder handling
- LM Studio board provider resolution
- request-scoped provider closure on success and failure
- prompt-field maximum lengths
- strict question and board-output validation/fallback
- strict grading, conversational-reply, and summary validation/fallback
- concurrent completion produces only one provider call
- LLM/STT concurrency/rate rejection
- production logging diagnostics disabled and sensitive strings absent

Frontend tests must cover:

- microphone denial before session creation
- media-track cleanup after later failures/unmount
- failed transcription does not auto-request the next question
- voice-specific timeout/error presentation
- masked API key is not resubmitted

Add production E2E coverage for one text learning session and one mocked or
deterministic voice session. A real faster-whisper test may remain opt-in, but
the release candidate must also be manually exercised with representative
English and Spanish audio on target hardware.

## Explicit non-goals

- No microservices or distributed task queue.
- No Redis-backed rate limiter for the supported single-process deployment.
- No streaming or partial transcription.
- No provider-framework rewrite or generic agent abstraction.
- No circuit breaker beyond bounded concurrency, timeouts, one transient retry,
  and deterministic fallbacks.
- No durable scheduled-meeting feature.
- No multi-worker WebSocket coordination.
- No deletion of `LearningPlan`, `LearningTask`, or `CollaborationSession` in
  this hardening pass. Their production/persisted-data compatibility requires a
  separate audited decision.
- No launcher/installer changes.

## Implementation sequence

1. Implement Phase 1 and its focused tests.
2. Run the backend and frontend checks relevant to Phase 1.
3. Repeat the production-only hotspot/reference scan.
4. Implement Phases 2 and 3 with focused provider/contract tests.
5. Repeat the production-only hotspot/reference scan.
6. Implement Phase 4 and its resource/logging tests.
7. Update documentation and add the remaining regression/E2E tests.
8. Run the complete validation gate and independently review the final diff.

Keep commits or review units aligned with these phases so failures can be
isolated and reverted without mixing unrelated provider, voice, and lifecycle
changes.

## Validation commands

Backend after each backend phase:

```bash
UV_CACHE_DIR=/tmp/aac-uv-cache uv run ruff check src tests scripts
UV_CACHE_DIR=/tmp/aac-uv-cache uv run python -m compileall -q src scripts
UV_CACHE_DIR=/tmp/aac-uv-cache uv run pytest -q <relevant-test-files>
```

Frontend after each frontend phase, from `src/frontend`:

```bash
npm run typecheck
npm run lint
npm test -- --run
npm run build
```

Final local PR gate:

```bash
UV_CACHE_DIR=/tmp/aac-uv-cache uv run python scripts/verify_pr.py
git diff --check
```

Also inspect production references separately from tests after every cleanup
pass. Do not claim browser, real-provider, real-microphone, or packaged-runtime
validation unless it was actually run.

## Definition of done

- Every acceptance criterion above has direct test or runtime evidence.
- The full backend/frontend/documentation gate passes.
- Production-only reference and hotspot rescans are recorded after changes.
- Logs and API responses contain no raw OpenRouter key, transcript, prompt, or
  upstream response body.
- Optional provider/STT failures leave the core AAC application usable.
- No background server, test runner, subagent, or native-model worker remains
  after validation.
- An independent reviewer verifies the final diff against this plan and reports
  no unaddressed must-fix item.

## Baseline validation note

At plan creation, the repository worktree was clean and `git diff --check`
passed. Earlier focused pytest attempts produced no result before a 60-second
hard timeout, so the implementing agent must diagnose test startup/runtime and
must not treat that attempt as a passing or failing functional result.
