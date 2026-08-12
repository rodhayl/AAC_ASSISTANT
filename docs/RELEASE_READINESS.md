# Release readiness and recovery runbook

This runbook is for a local or managed AAC Assistant installation. It is an
operational safety checklist, not a substitute for clinical or user-acceptance
validation.

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

The installer displays an explicit update message when the selected directory
already contains `AAC_Assistant.exe`. During an update it signals the running
copy through a private, installation-scoped Windows event.
 The launcher asks
Uvicorn to shut down normally and the installer waits up to 25 seconds for the
matching executable to exit. A path-filtered force termination is only the
last fallback; if the process still remains, installation aborts rather than
continuing with an unknown running process.

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
