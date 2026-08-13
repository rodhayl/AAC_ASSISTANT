# Changelog

All notable changes to this project are documented here. The project follows
[Keep a Changelog](https://keepachangelog.com/) formatting. Versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Security

- Bind the backend to `127.0.0.1` by default instead of `0.0.0.0`, so the
  application is not reachable from the network unless the operator explicitly
  opts in.
- Replace the predictable `admin1`/`Admin123` development bootstrap credential
  with a cryptographically random one-time password generated on first run and
  stored in `.env`. Production refuses to bootstrap without an explicit strong
  password.
- Stop printing the bootstrap admin password to the console.

### Added

- `SECURITY.md`, `docs/THREAT_MODEL.md`, `docs/SECURITY_ARCHITECTURE.md`,
  `docs/PRIVACY_AND_DATA.md`, `docs/ACCESSIBILITY.md`, `CONTRIBUTING.md`,
  `CODE_OF_CONDUCT.md`, `SUPPORT.md`, `ROADMAP.md`, issue/PR templates.

### Fixed

- `PUT /api/auth/users/{user_id}` now validates role, email format/uniqueness,
  and the active flag (previously accepted arbitrary values).
- Seeded demo board is fully populated (12/12 symbols) and assigned to the demo
  student, so it is playable rather than "Board Locked".
- Slow preference/filter fetches no longer overwrite newer user edits.

## Earlier history

Earlier development history is recorded in the git log and the repository
documentation. No tagged releases have been published yet.
