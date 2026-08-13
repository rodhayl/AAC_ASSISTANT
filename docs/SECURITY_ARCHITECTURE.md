# Security Architecture

This document describes how AAC Assistant implements authentication,
authorization, and data protection. It complements
[docs/THREAT_MODEL.md](THREAT_MODEL.md).

## 1. Authentication

- **Password hashing** uses Argon2 via `pwdlib`'s recommended configuration.
  Legacy bcrypt hashes are verified for migration and transparently upgraded to
  Argon2 on successful login (`verify_password_and_update`).
- **Password policy** requires at least 8 characters with uppercase, lowercase,
  and a digit (`password_strength_error`).
- **Tokens** are signed JWTs. A separate short-lived access token and a
  refresh token are issued by `POST /api/auth/token`.
- **JWT secret** is generated once (`secrets.token_hex(32)`) and persisted to
  `.env` by `ensure_jwt_secret`. A placeholder or empty value is never used.
- **Session revocation** — every password mutation calls
  `mark_credentials_changed`, which bumps `security_version` and records
  `credentials_changed_at`. Access tokens carry the version and issuance time;
  tokens issued before a credential change are rejected (`src/api/deps/auth.py`).
- **Rate limiting** — the login endpoint is limited to 10 attempts/minute/IP
  (`slowapi`), and accounts lock after 5 consecutive failures
  (`lockout_service`).

## 2. First-run bootstrap

- On first run, `AAC_BOOTSTRAP_ADMIN_ON_FIRST_RUN` (default `true`) creates an
  administrator only if none exists.
- If no `AAC_BOOTSTRAP_ADMIN_PASSWORD` is configured, a cryptographically
  random one-time credential is generated and stored in `.env`
  (`resolve_bootstrap_password`). The operator must change it after first login.
- In `ENVIRONMENT=production`, bootstrap refuses to run without an explicit
  strong password; the legacy development default is rejected.
- The password is never printed to logs or stdout.

## 3. Authorization

- **Role checks live at the API layer**, not only in the UI. Dependencies such
  as `get_current_admin_user` and `get_current_active_user` gate every protected
  endpoint.
- Roles are constrained to `student`, `teacher`, `admin`. `update_user`
  validates `user_type` against this fixed allowlist and validates email format
  and uniqueness, preventing privilege escalation via mass assignment.
- Horizontal access: board, learning, and preference endpoints resolve records
  against the authenticated user's identity; cross-user access requires an
  explicit teacher/admin relationship where applicable.

## 4. File and upload handling

- All `UploadFile` endpoints route through `src/api/file_uploads.py`, which:
  - reads in bounded 1 MB chunks and rejects empty or oversized bodies
    (`413`), without trusting `Content-Length`;
  - validates declared content type against an allowlist and checks file
    signatures (`RIFF`, `OggS`, WebM, MP3, MP4);
  - decodes images with Pillow, enforcing a pixel limit and rejecting
    decompression bombs;
  - writes audio to a temporary file and removes it on failure.
- Deletion of owned uploads verifies the resolved path stays inside the
  uploads directory (`remove_owned_upload`).
- Default limits: 5 MB images, 10 MB audio.

## 5. Network exposure

- `BACKEND_HOST` defaults to `127.0.0.1`. Binding `0.0.0.0` is an explicit
  operator decision and is documented as requiring strong credentials and
  reviewed CORS origins.
- CORS uses an explicit allowlist. `*` is rejected when credentialed CORS is
  enabled, and non-development environments must provide explicit origins.
- `ALLOW_DB_RESET` defaults to `false`.

## 6. Data storage

- SQLite database, logs, and uploads live under a writable runtime root. On
  Windows, an installed copy under Program Files uses the per-user
  `%APPDATA%\AACAssistant` directory so standard users need no write access to
  the installation folder.
- The database uses WAL mode, foreign-key enforcement, and a bounded page cache.

## 7. Audit logging

- Authentication events (login failures, lockouts) and password changes are
  recorded via `audit_service` in the local database. No communication content,
  tokens, or passwords are written to logs.

## 8. Supply chain

- Python dependencies are pinned via `uv.lock`; frontend dependencies via
  `package-lock.json`.
- CI runs dependency auditing (`pip check`, `npm audit` where configured),
  linting, type checking, and static analysis (`scripts/audit_codebase.py`).
