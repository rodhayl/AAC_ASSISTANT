# Changelog

All notable changes to this project are documented here. The project follows
[Keep a Changelog](https://keepachangelog.com/) formatting. Versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed

- The release version now has a single source, `pyproject.toml`: the backend
  reads it from that file (which the spec also bundles into the frozen app),
  the frontend build injects it into `VITE_APP_VERSION`, `build_package.bat`
  passes it to Inno Setup with `/DMyAppVersion`, and the workflows derive it at
  run time. The shipped `.env.example` and `env.properties.example` templates no
  longer pin `APP_VERSION`, which is how a fresh 2.0.1 install could still
  report `2.0.0`. `tests/test_config_pydantic.py` now fails if the literal
  reappears in any of those layers.

## [2.0.1] - 2026-09-18

### Security

- Logout now awaits server-side token revocation before clearing local auth
  state, so a captured token can no longer be reused after sign-out.
- Release artifacts can now be Authenticode-signed: `build_package.bat` gains
  an optional signing step and a tag-triggered workflow signs and verifies the
  installer before publishing.

### Fixed

- Data export/import checksum now normalizes whole-number floats so a browser
  JSON round-trip no longer fails re-import with `400`.
- Voice-mode toggle color contrast and the learning-mode delete button's
  accessible name (Axe `button-name`).
- Windows launchers resolve `uv` installed by winget without requiring a new
  terminal, pin the project venv to Python 3.13, and survive Smart App
  Control's blocking of runtime-generated venv launchers (os error 4551) by
  pre-seeding the venv with the standard library.
- The shipped configuration templates (`.env.example`,
  `env.properties.example`) still pinned `APP_VERSION=2.0.0`, and the installer
  ships that template as the file a fresh install copies on first run. New
  installs therefore reported `2.0.0` from `/api/health` and the auth payload
  while running the 2.0.1 build.

### Added

- Optional free Authenticode code signing for the packaged exe and installer
  (`scripts/sign_release.ps1`, `AAC_SIGN_RELEASE=1`), with a tag-triggered
  release workflow that verifies signatures and publishes the installer,
  portable zip, and SHA256 checksums to GitHub Releases.
- `scripts/publish_release.py` publishes a release without GitHub Actions by
  creating it for an existing tag and uploading the installer, portable zip,
  and checksums under the same asset names the release workflow uses.

### Changed

- Symbol-usage analytics consolidated onto the canonical `/analytics/usage`
  endpoint instead of split across `/analytics/log` and `/analytics/usage`.
- Overlapping backend test suites consolidated by domain: `test_api_basic`
  folded into `test_api_comprehensive`, duplicate JWT-acceptance and
  preference-mapping cases merged, frozen-runtime cases folded into
  `test_packaging_improvements`, and the legacy `test_utils_auth` helper
  renamed to `tests/auth_helpers.py` (no longer collected as a test module).
- The three Smartbar Vitest suites merged into one file with shared mocks.
- Frontend page/store coverage expanded with real-case Vitest suites for
  `Dashboard`, `Students`, `Symbols` and `Achievements` (previously 0%) plus
  `learningStore` resilience/history-reconstruction and `notificationsStore`
  read-state cases; application-only line coverage raised 53.5% → 65.9% and
  the `vitest.config.ts` regression gate raised to lines ≥ 62%.
- The six core pages (`Dashboard`, `Achievements`, `Symbols`, `Students`,
  `Register`, `NotFound`) are now at 100% statement/line coverage with 52 new
  real-case tests: student empty/loading states, editor/award modal open-close
  and cancel paths, automatic-criteria achievement creation, symbol
  create/edit with image upload, invalid-file rejection, ARASAAC search and
  import failures, batch-delete failure reporting, stale-fetch guards,
  pagination, admin student edit/create, board assignment success/failure,
  preferences/reset/delete modal error and cancel paths, and the guardian
  profile modal. Unreachable defensive guards removed (see Removed).
- Remaining defensive branches in the `achievements`, `providers` and
  `symbols` routers closed with real-case tests (permission/404/duplicate
  award paths, install support limits, TTS/voice install failure mappings,
  image/upload cleanup on commit failure, best-effort progress and
  board-symbol partial updates), raising those routers to 95%+ coverage.
  Also removed an unreachable `update_achievement` branch: system
  achievements (created_by=None) always fail the ownership check for
  teachers first, so the separate "system achievements are admin-only"
  guard could never fire.
- Frontend Vitest coverage is now scoped to application code and enforced as
  a regression gate (`src/frontend/vitest.config.ts`: lines ≥ 52%,
  statements ≥ 53%, functions ≥ 47%, branches ≥ 46%). New real-case tests
  cover the settings store (12% → 100%), toast store (54% → 100%),
  board store CRUD (47% → 83%), and the Appearance/Data/Security settings
  tabs, raising total application coverage from 51% to 54% lines.
- Backend coverage raised to 82% combined lines+branches with new real-case
  API tests for the AI-board router (43% → 82%), settings (56% → 90%),
  providers (56% → 84%), symbols (71% → 88%), learning (77% → 95%),
  learning modes (67% → 94%), users (66% → 90%), achievements (66% → 81%),
  collaboration WebSocket access paths, password-policy rules, translation
  fallbacks, and the request-scoped DB session lifecycle.

### Removed

- Unreachable defensive guards in the three core pages, verified by
  coverage-intersection analysis (the UI can never reach them): the
  `loadManagementData` teacher-only early return and the `handleUpdate`/
  `handleAward` null-guards in `Achievements`; the `submitEdit`/`submitCreate`
  early returns and the unreachable batch-delete outer-catch branch in
  `Symbols`; and the assign/preferences/reset/delete null-guards plus the
  already-assigned duplicate check in `Students` (assigned boards are
  disabled in the modal, so the branch could never fire).
- The test-only `learning_companion_service` module and other unreferenced
  production symbols.
- 22 unreferenced translation keys from the `es` and `en` locales.
- Dead store actions (`authStore.updatePreferences`/`updateProfile`,
  `boardStore.unassignBoardFromStudent`, `localeStore.initFromDetected`,
  `themeStore.toggleDarkMode`, `notificationsStore.setItems`).
- Orphaned operator scripts with zero references
  (`migrate_achievements_schema.py`, `migrate_arasaac_category.py`,
  `seed_core_vocabulary.py`).

### Maintainability

- `scripts/verify_pr.py` now runs the internal-import audit
  (`scripts/audit_codebase.py`) and a new dead-translation-key guard
  (`scripts/check_i18n_keys.py`) so dead code cannot silently regress.
- `docs/MAINTAINER_GUIDE.md` documents the deterministic seed-password
  requirement for the local E2E run.

### Testing

- Added GUI end-to-end coverage for board drag-and-drop, real-time
  notification push (SSE), and real-time board collaboration across two
  browser sessions (WebSocket), closing previously untested interaction paths.
- Added GUI end-to-end coverage for symbol image fallback (broken image
  degrades to placeholder), symbol library create/edit/delete, and the
  first-run onboarding flow on a fresh database.

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
