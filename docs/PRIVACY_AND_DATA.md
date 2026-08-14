# Privacy and Data

AAC Assistant is designed to keep communication data under the operator's
local control. This document explains what data exists, where it is stored, and
how to manage it. It is not a legal privacy policy.

## 1. Local-first by design

- The core AAC experience (boards, symbols, sentence building, learning
  sessions) works entirely offline after installation.
- Data is stored in local files on the operator's machine. The application does
  not upload communication content to a cloud service as part of its core flow.
- The application binds to `127.0.0.1` by default and is not reachable from the
  network unless the operator explicitly opts in.

## 2. What is stored

| Data | Location |
| ---- | -------- |
| Accounts, roles, password hashes | SQLite database (`data/aac_assistant.db`) |
| Communication boards, symbols, sentences | SQLite database |
| Learning sessions, achievements | SQLite database |
| User preferences | SQLite database |
| Uploaded images and audio | `uploads/` directory |
| JWT secret, configuration | `.env` |

## 3. Optional network features

Some features are opt-in and may send data off-device:

- **Speech-to-text (faster-whisper)** — the model is bundled in the packaged
  installer and runs locally. Source checkouts may download the model on first
  use. No audio leaves the machine.
- **Text-to-speech** — uses the browser's local speech synthesis by default.
- **LLM learning questions** — `Ollama` and `LM Studio` are local services.
  `OpenRouter` is a third-party API used only if the operator configures an API
  key and selects it. Content sent to `OpenRouter` is governed by its terms.
- **ARASAAC symbol images** — fetched from `static.arasaac.org` when symbol
  image backfill is enabled (off by default).

Core communication never depends on these services.

## 4. What is not collected

- No analytics or telemetry.
- No crash reporting that uploads data.
- No advertising identifiers or tracking.

## 5. Backups and deletion

- Back up the `data/`, `uploads/`, and `.env` files to preserve the
  installation.
- Deleting a board, user, or upload through the UI removes the corresponding
  record; uploaded files for removed symbols are cleaned up best-effort.
- The uninstaller deliberately preserves `data/` and `uploads/` so user content
  is not destroyed by an upgrade or reinstall.

## 6. Operator responsibilities

- Use a strong, unique administrator password and change it after first login.
- Use full-disk encryption on devices holding sensitive communication content.
- Review third-party terms before enabling `OpenRouter` or other remote
  services, because content sent to those services is processed under their
  policies.
- Do not expose the application to the network unless you understand the risks.

## 7. Reporting

For security or privacy concerns, see [SECURITY.md](../.github/SECURITY.md).
