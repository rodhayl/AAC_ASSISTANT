# Changelog

All notable changes to this project are documented here. The project follows
[Keep a Changelog](https://keepachangelog.com/) formatting. Versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Cross-browser end-to-end validation: the full Playwright suite (127 tests)
  now passes in Chromium, Firefox, and WebKit, and both Firefox and WebKit run
  in CI.
- Live e2e coverage for partner speech input: a Playwright spec opens the
  partner overlay and asserts transcription through the real local
  `/api/providers/transcribe` endpoint (faster-whisper), with a fallback-skip
  when the optional voice extra is not installed.
- Reusable `Portal` component (`createPortal` → `document.body`) for modal
  overlays, fixing WebKit/Safari overlay and click-interception bugs.
- Linux launcher (`start.sh` / `scripts/start_server.py`) now auto-opens the
  default browser once the server is ready (matching the Windows launcher),
  handles Ctrl+C/SIGTERM gracefully during startup warmup, and ships a
  `.desktop` entry for application menus.
- Frontend unit/component tests for Dashboard, LoadingState, NotFound, Register,
  SymbolGrid, and ToastContainer, plus per-role backend journey tests.
- Frontend coverage thresholds (statements/branches/functions/lines) and a
  widened, honest `src/**` coverage scope.
- Local faster-whisper speech-to-text for the partner microphone overlay, which
  works in every browser (including Firefox on Linux) and falls back to the
  browser's `SpeechRecognition` API only when the optional voice extra is
  missing. Backed by a new `POST /api/providers/transcribe` endpoint.
- Symbol search now reports semantic-search status via an `X-Semantic-Search`
  response header and the UI shows when it degrades to keyword-only matching
  instead of failing silently — both in the board search modal and on the
  Symbols management page.
- Learning questions, answer feedback, and session summaries now expose a
  `source` field (`llm`/`fallback`) and the UI notes when a deterministic
  local template is used because the LLM is unavailable. The source is
  persisted in the conversation history, so the badge also appears on
  assistant messages in the chat (live and when reloading a past session).

### Fixed

- WebKit/Safari AAC speech: `speechSynthesis.speak()` was invoked from the
  previous utterance's `onend` handler (via a microtask), leaving the speak
  button stuck; the next utterance is now deferred to a macrotask and the
  redundant `cancel()` before `speak()` was removed.
- Signed data export could no longer be re-imported when a whole-number float
  field (e.g. `comprehension_score` `0.0`/`1.0`) round-tripped as an integer
  through the browser, breaking the checksum; export now normalizes canonical
  numeric values.
- WebKit e2e harness races (navigation `waitUntil` and forged-token redirect
  page errors).
- Local neural TTS (Kokoro) is now initialized eagerly at app startup and its
  toggle is persisted, so speech reliably uses the natural neural voice instead
  of falling back to the browser's robotic `speechSynthesis` voice (espeak on
  Linux) on the first utterance.

### Removed

- Dead `learning_companion_service.py` facade that re-exported the learning
  service with an identical session-scope override.
- Legacy migration/seed scripts (`migrate_achievements_schema.py`,
  `migrate_arasaac_category.py`, `seed_core_vocabulary.py`).

## [2.0.0] - 2026-08-14

### Security

- Bind the backend to `127.0.0.1` by default instead of `0.0.0.0`, so the
  application is not reachable from the network unless the operator explicitly
  opts in.
- Replace predictable default bootstrap credentials with an interactive
  first-run administrator web setup flow (`/setup`), ensuring packaged and
  development installations require strong operator-chosen credentials.
- Eliminate plaintext password storage in `.env` and stop printing bootstrap
  credentials to the console.

### Added

- `.github/SECURITY.md`, `docs/THREAT_MODEL.md`, `docs/SECURITY_ARCHITECTURE.md`,
  `docs/PRIVACY_AND_DATA.md`, `docs/ACCESSIBILITY.md`, `.github/CONTRIBUTING.md`,
  `.github/CODE_OF_CONDUCT.md`, `.github/SUPPORT.md`, `docs/ROADMAP.md`, `docs/README.md`, issue/PR templates.

### Fixed

- `PUT /api/auth/users/{user_id}` now validates role, email format/uniqueness,
  and the active flag (previously accepted arbitrary values).
- Seeded demo board is fully populated (12/12 symbols) and assigned to the demo
  student, so it is playable rather than "Board Locked".
- Slow preference/filter fetches no longer overwrite newer user edits.

## Earlier history

Earlier development history leading up to the initial `v2.0.0` public release is
recorded in the git commit log.
