# Release notes

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
- Optional LLM-dependent learning questions require an operator-configured local service (Ollama / LM Studio) or an optional OpenRouter API key.
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
