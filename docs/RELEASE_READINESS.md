# Release readiness and recovery runbook

This runbook is for a local or managed AAC Assistant installation. It is an
operational safety checklist, not a substitute for clinical or user-acceptance
validation.

## Current working-tree validation (2026-08-12)

The current continuation working tree has not been committed yet and contains
pending tracked and untracked changes. The complete current gates pass: backend Ruff, compileall, and pytest
(**629 passed, 2 optional `faster-whisper` skips, 0 failed**); frontend
typecheck, ESLint, **42 Vitest files / 211 tests**, production build, and
bundle budgets (338.8 kB JS / 450 kB and 96.7 kB CSS / 150 kB). `uv lock
--check`, production `npm audit` (0 vulnerabilities), `bash -n start.sh`, and
`git diff --check` also passed.

After that baseline, a production-build regression exposed and fixed a static
`api.ts` ↔ `authStore.ts` import cycle that emitted four browser
`ReferenceError: Cannot access 'et' before initialization` errors during the
forged-token flow. The fix uses the cycle-free `src/frontend/src/lib/authState.ts`
reader bridge. Post-fix focused API/auth tests passed **33/33**, typecheck and
ESLint passed, the production build passed, and `maintenance.spec.ts` passed
**5/5** against an isolated server with all four providers ready and no page
errors. A fresh production build and isolated backend then passed **107/107
Playwright E2E tests**, with 0 skips/failures and no unexpected page/server
errors. The server reached readiness with all four providers and shut down
cleanly. Interactive browser automation was not repeated separately because
the delegated browser agent returned a temporary rate-limit response; this
headless Playwright run is the available GUI evidence for the current tree.
These are technical repository checks only and do not replace the
clinical/beta gate below.

A focused follow-up also exercised the authenticated legacy `/play/1` route
against a fresh production build: `advanced.spec.ts` passed **8/8** including
setup, and the route redirected to `/communication?boardId=1`. Frontend
typecheck and ESLint passed afterward. The full-suite result above remains the
last complete run; this focused check was added to close the route-coverage gap.

## Before every release

1. Confirm the release version in `installer.iss`, `README.md`, and the build
   output is the same.
2. Run the backend and frontend gates from the README, including Ruff,
   compilation, pytest, TypeScript checks, ESLint, Vitest, and the production
   build.
3. Build both artifacts with `build_package.bat`:
   - `dist\AAC_Assistant\AAC_Assistant.exe`
   - `dist\AAC_Assistant_Setup_<version>.exe`
4. Keep the previous installer artifact. A same-version filesystem snapshot is
   useful for recovery, but it is not a versioned rollback test.
5. Record the SHA-256 of each installer and store it with the release notes. Automated or managed launcher checks must set `AAC_ASSISTANT_NO_BROWSER=1` so
validation never opens a user's default browser. Normal desktop launches omit
this flag and retain the expected browser opening.

The installer detects an existing installation from the wizard-selected
directory, the registered previous install (per-user and per-machine uninstall
keys), and the standard default locations. When one is found, the wizard shows
an update flow instead of a fresh install: the window caption, welcome heading,
and body text say "Update/Actualizar AAC Assistant to version 2.0.0" in both
English and Spanish. During an update it signals the running copy through a
private, installation-scoped Windows event. The launcher asks Uvicorn to shut
down normally and the installer waits up to 25 seconds for the matching
executable to exit. A path-filtered force termination is only the last
fallback; if the process still remains, installation aborts rather than
continuing with an unknown running process.

## Automated readiness evidence (2026-08-12)

The local automated release-safety rehearsal was repeated with an isolated
port/data directory and `AAC_ASSISTANT_NO_BROWSER=1`:

- Cold start through the supported `scripts/start_server.py` launcher reached
  `/api/health` in 4.24 seconds and `/ready` in 9.60 seconds.
- `CTRL_BREAK_EVENT` caused the wrapper to request graceful child shutdown;
  the wrapper exited with code 0 in 0.27 seconds.
- The log contained `Application shutdown complete` and no traceback,
  connection-reset, or proactor diagnostics when probes used
  `Connection: close` and stopped before shutdown.
- Isolated data was removed and the test port was closed afterward.
- Focused lifecycle/packaging tests passed: 56 passed, 1 expected skip
  (`faster-whisper` optional dependency unavailable), 0 failed; Ruff and
  `git diff --check` also passed.

A direct Uvicorn process also shut down cleanly, but returned signal-specific
exit code 3 when sent `CTRL_BREAK_EVENT`; this is not the supported launcher
exit path, which normalizes a user-requested shutdown to exit code 0.

These checks establish technical local evidence only. They do not replace a
clean Windows VM update/rollback rehearsal, AAC hardware testing, or clinical
and user-acceptance review described in the beta gate below.

## Physical SQLite backup

Stop the application before making a production backup whenever practical.
For a live SQLite database, use SQLite's backup API rather than copying a file
while it is being written. A minimal Python example is:

```python
import sqlite3
from pathlib import Path

Path("backup").mkdir(parents=True, exist_ok=True)
with sqlite3.connect("data/aac_assistant.db") as source:
    with sqlite3.connect("backup/aac_assistant-before-release.db") as target:
        source.backup(target)

backup_uri = "file:backup/aac_assistant-before-release.db?mode=ro"
with sqlite3.connect(backup_uri, uri=True) as check:
    assert check.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
```

Protect the backup with the same filesystem access controls as the database.
Do not place backups in the web-served uploads directory. Verify that the
backup opens read-only and record its creation time and source release.

## Export/import recovery

For user-selective recovery, use the authenticated administrator data export
and import endpoints. Keep the signed export private. Schema-2 exports are
bound to the configured `JWT_SECRET_KEY` and require a compatible symbol
catalog; they are not interchangeable between installations with different
secrets. Verify after import:

- the expected board count and names;
- board-symbol relationships and labels;
- assignments and user ownership;
- learning and achievement records when included;
- absence of duplicate restored boards.

Use a disposable copy of the database for recovery rehearsal. Never rehearse
with a real user's only copy of their data.

## Offline mutation recovery

Offline board mutations are retained in a bounded, session-scoped queue and
restored after a page reload only for the same authenticated user. Tokens,
non-serializable uploads, and authentication requests are never persisted.
Failed replays appear in the conflict panel and are not silently retried after
a session change.

Replay is deliberately FIFO and **at-least-once**, not exactly-once: a crash
immediately after a server accepts a mutation but before the browser removes its
local queue entry can cause a duplicate replay. Do not treat offline POST
operations as exactly-once until the API provides idempotency keys or the
operation is otherwise made idempotent. The release rehearsal must include
interrupted replay and verify the affected endpoint's duplicate behavior.

## Versioned rollback

The installer preserves `.env`, `data`, and `uploads` during replacement, but
it does not automatically roll back a failed upgrade. A supported rollback is
an operator action using two independently built, versioned installers:

1. Stop the current application and make a physical SQLite backup.
2. Preserve the current `.env`, `data`, `uploads`, and logs outside the install
   directory.
3. Verify the target older installer and its SHA-256 against the release
   record.
4. Install the older artifact into the existing application directory.
5. Start it on a maintenance port or with the normal launcher and check
   `/api/health` and `/ready`.
6. Verify the database opens, authentication works, assigned boards load, and
   representative symbol images/uploads remain available.
7. If the older release cannot read the database, stop immediately and restore
   the physical backup rather than attempting ad-hoc schema edits.

A rollback is not complete until the health/readiness checks and a data
verification pass succeed. Database schema compatibility must be confirmed
for every release pair; installer file preservation alone does not guarantee
application compatibility.

## Beta gate

Do not distribute broadly until all of the following have an owner and an
outcome:

- a speech-language pathologist or AAC specialist reviews core vocabulary,
  labels, sentence-strip behavior, and safety wording;
- representative users test keyboard, touch, switch, eye-gaze, and zoom flows;
- screen-reader and high-contrast checks are performed on supported browsers;
- audio output is verified on the actual target hardware;
- backup/restore and versioned rollback are rehearsed on a disposable copy;
- crash, failed-update, and interrupted-write recovery are recorded;
- privacy review confirms data location, retention, access, and support policy;
- a support contact, issue triage process, release owner, and stop criteria are
  published;
- beta starts with a small cohort and a tested recovery path.

Automated tests establish technical evidence. They do not provide clinical
approval or replace testing with people who use AAC.
