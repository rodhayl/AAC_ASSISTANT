# Release notes

## v2.0.1 (2026-09-17)

Maintenance release focused on Windows launch reliability, release
infrastructure, and accumulated security, accessibility, and test-suite
improvements from the `main` line.

### Highlights

- **Windows launchers fixed** — `start.bat` / `install_dependencies.bat` now
  find `uv` installed by winget without a new terminal, pin the project venv
  to Python 3.13, and survive Smart App Control blocking uv's runtime-generated
  venv launcher (os error 4551) by pre-seeding the venv with the standard
  library.
- **Signed releases** — the packaged executable and installer can be
  Authenticode-signed for free (`AAC_SIGN_RELEASE=1`); pushing a `v*` tag
  triggers a workflow that builds, signs, verifies, smokes, and publishes the
  installer, portable zip, and SHA256 checksums to GitHub Releases.
- **Verified quality** — 253/253 Playwright end-to-end tests, the full
  packaging suite, and a frozen-environment check that every offline
  capability (Kokoro TTS, faster-whisper, fastembed, sqlite-vec) loads from
  the bundled models.

### Security

- Logout awaits server-side token revocation before clearing local auth
  state, so a captured token can no longer be reused after sign-out.
- Release artifacts are Authenticode-signed with a self-signed certificate.
  The signature is trusted on machines where the certificate was imported;
  Smart App Control still requires a paid CA certificate for unconditional
  trust, which remains a documented limitation.

### Fixed

- Data export/import checksum normalizes whole-number floats so a browser
  JSON round-trip no longer fails re-import with `400`.
- Voice-mode toggle color contrast and the learning-mode delete button's
  accessible name (Axe `button-name`).

### Changed

- Symbol-usage analytics consolidated onto the canonical `/analytics/usage`
  endpoint instead of split across `/analytics/log` and `/analytics/usage`.
- Overlapping backend test suites consolidated by domain; frontend Vitest
  suites merged and coverage gates raised.

### Upgrading

Run `AAC_Assistant_Setup_2.0.1.exe`. The installer detects the existing
installation and preserves your database, settings, and uploads. Portable
users should replace the `AAC_Assistant` folder, keeping `data/`, `logs/`,
and `uploads/`.

## v2.0.0 (2026-08-14)

The repository has carried version `2.0.0` throughout its configuration,
installer, and API. This release marks the first public, packaged release.

### Highlights

- **Local-first communication platform** — boards, symbols, sentence building,
  learning sessions, achievements, and browser speech.
- **Offline voice and search** — the Windows installer bundles the `tiny`
  faster-whisper model and the fastembed semantic-search model.
- **Security hardening** — loopback-only network binding by default, secure
  first-run administrator web setup flow, and validated user updates.

### Security

- Bind to `127.0.0.1` by default instead of `0.0.0.0`.
- First run provides an interactive web setup screen (`/setup`) to configure a strong
  administrator password; predictable default credentials are eliminated across
  packaged and production installations.
- `PUT /api/auth/users/{user_id}` validates role, email, and active flag.

### Known issues and external services

- Core AAC communication, symbols, boards, speech, and learning operate fully offline.
- Optional LLM-dependent learning questions require an operator-configured local service (Ollama / LM Studio) or an optional cloud provider (OpenRouter / Groq) API key.
- Optional ARASAAC symbol backfill (`AAC_ENABLE_SYMBOL_IMAGE_BACKFILL=true`) makes external HTTP lookups to the ARASAAC public API when explicitly enabled (disabled by default).
- See [Accessibility Guide](ACCESSIBILITY.md) for known accessibility limitations.

### Installation and upgrade

Run `AAC_Assistant_Setup_2.0.0.exe`. Existing installations are detected and
updated in place; the uninstaller preserves the database and uploads.

### Compatibility

- Windows 10/11.
- Requires no separate Python or Node.js installation for the packaged build.

### Checksums and SBOM

- `SHA256SUMS.txt` — SHA-256 checksums for release artifacts.
- `SBOM.json` — CycloneDX 1.4 bill of materials generated from lockfiles.

### Rollback

The installer preserves user data but does not perform automatic cross-version
rollback. Keep a physical SQLite backup and the previous installer to roll
back manually. See [Release Readiness Runbook](RELEASE_READINESS.md).
