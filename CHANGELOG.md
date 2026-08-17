# Changelog

All notable changes to this project are documented here. The project follows
[Keep a Changelog](https://keepachangelog.com/) formatting. Versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Security

- Logout now awaits server-side token revocation before clearing local auth
  state, so a captured token can no longer be reused after sign-out.

### Fixed

- Data export/import checksum now normalizes whole-number floats so a browser
  JSON round-trip no longer fails re-import with `400`.
- Voice-mode toggle color contrast and the learning-mode delete button's
  accessible name (Axe `button-name`).

### Changed

- Symbol-usage analytics consolidated onto the canonical `/analytics/usage`
  endpoint instead of split across `/analytics/log` and `/analytics/usage`.

### Removed

- The test-only `learning_companion_service` module and other unreferenced
  production symbols.
- 22 unreferenced translation keys from the `es` and `en` locales.

### Maintainability

- `scripts/verify_pr.py` now runs the internal-import audit
  (`scripts/audit_codebase.py`) and a new dead-translation-key guard
  (`scripts/check_i18n_keys.py`) so dead code cannot silently regress.
- `docs/MAINTAINER_GUIDE.md` documents the deterministic seed-password
  requirement for the local E2E run.

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
