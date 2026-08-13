# Execute All Test Scenarios — Current Validation Guide

> **Updated 2026-08-12.** The former Chrome DevTools Protocol (CDP) harness and
> its executable scripts were removed. The ten scenario files in this directory
> are retained as historical role-oriented coverage maps and are explicitly not
> executable procedures. Do not start Chrome with remote debugging on port 9222,
> copy their old CDP snippets, or run destructive cleanup against a real user
> profile.

## Current repeatable validation

Use the production frontend build served by the backend. The current automated
browser suite is under `src/frontend/e2e` and is configured by
`src/frontend/playwright.config.ts`. It must run against a production server,
not the Vite development server.

The following is the isolated POSIX-shell/Git-Bash flow used by CI. Run it from
the repository root. It uses only `.ci-e2e-data`, never a user's existing data,
and always stops the exact server it started. The `AAC_ASSISTANT_NO_BROWSER=1`
flag is included as a safety guard for managed/frozen launchers; this direct
uvicorn command does not open a browser itself.

```bash
set -euo pipefail
export PLAYWRIGHT_BASE_URL="http://127.0.0.1:8086"
export E2E_ADMIN_USERNAME="admin1"
export E2E_ADMIN_PASSWORD="Admin123"
export E2E_TEACHER_USERNAME="teacher1"
export E2E_TEACHER_PASSWORD="Teacher123"
export E2E_STUDENT_USERNAME="student1"
export E2E_STUDENT_PASSWORD="Student123"
export AAC_ASSISTANT_NO_BROWSER=1

rm -rf .ci-e2e-data
mkdir -p .ci-e2e-data
cleanup() {
  if [[ -n "${SERVER_PID:-}" ]]; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  rm -rf .ci-e2e-data
}
trap cleanup EXIT
trap 'exit 130' INT TERM

npm --prefix src/frontend run build

ENVIRONMENT=test \
ALLOWED_ORIGINS=http://127.0.0.1:8086 \
JWT_SECRET_KEY=ci-e2e-secret-key-with-at-least-32-characters \
TESTING=1 BACKEND_HOST=127.0.0.1 BACKEND_PORT=8086 \
DATA_DIR=.ci-e2e-data APP_VERSION=2.0.0 \
AAC_SEED_SAMPLE_DATA=true AAC_BOOTSTRAP_ADMIN_ON_FIRST_RUN=true \
AAC_BOOTSTRAP_ADMIN_USERNAME=admin1 AAC_BOOTSTRAP_ADMIN_PASSWORD=Admin123 \
AAC_SEED_ADMIN1_PASSWORD=Admin123 AAC_SEED_STUDENT1_PASSWORD=Student123 \
AAC_SEED_TEACHER1_PASSWORD=Teacher123 AAC_ENABLE_SYMBOL_IMAGE_BACKFILL=false \
uv run uvicorn src.api.main:app --host 127.0.0.1 --port 8086 \
  > /tmp/aac-e2e-server.log 2>&1 &
SERVER_PID=$!

ready=0
for attempt in $(seq 1 60); do
  if curl --fail --silent http://127.0.0.1:8086/api/health > /tmp/aac-e2e-health.json \
    && curl --fail --silent http://127.0.0.1:8086/ready > /tmp/aac-e2e-ready.json; then
    cat /tmp/aac-e2e-health.json
    cat /tmp/aac-e2e-ready.json
    ready=1
    break
  fi
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    break
  fi
  sleep 1
done
if [[ "$ready" != 1 ]]; then
  cat /tmp/aac-e2e-server.log
  exit 1
fi

npm --prefix src/frontend exec playwright test
```

The suite's global setup rejects a missing/stale frontend build or a Vite
server. On Windows, use an isolated PowerShell process with the same environment
values and stop that exact process after the run; do not use the desktop launcher
for this validation because it may open a browser.

These are test-fixture values only. Never use them for a shared or production
installation. Record the commit/build identity, isolated data directory, roles
and fixture accounts, routes/API flows, expected and actual results, console
errors, failed network responses, cleanup result, and final process/port status.

## Current scenario coverage

| Scenario | Current browser/API coverage |
|---|---|
| 01 Admin user management | `admin.spec.ts`, `settings.spec.ts`, user-management tests |
| 02 Admin system settings | `settings.spec.ts`, `settings-modes.spec.ts`, `admin.spec.ts` |
| 03 Teacher board creation/sharing | `boards.spec.ts`, `board-editor.spec.ts` |
| 04 Teacher learning-mode configuration | `settings-modes.spec.ts`, learning E2E specs |
| 05 Teacher student progress | `admin.spec.ts`, `dashboard.spec.ts`, student-management tests |
| 06 Student communication board | `communication.spec.ts`, `boards.spec.ts` |
| 07 Student learning games | `learning-games.spec.ts`, `learning-topics.spec.ts` |
| 08 Student voice mode | `voice-mode.spec.ts` |
| 09 Cross-role board collaboration | `boards.spec.ts`, `board-editor.spec.ts`, communication specs |
| 10 Cross-role achievements | `achievements.spec.ts`, learning and dashboard specs |

Check the current route and component names in source before extending a
scenario. The application currently uses page modules such as
`src/frontend/src/pages/Boards.tsx`, `BoardEditor.tsx`, `Communication.tsx`,
`Learning.tsx`, `Achievements.tsx`, `Students.tsx`, and `UserManagement.tsx`,
with focused child components under `src/frontend/src/components/`.

## Evidence and safety requirements

Technical automation does not establish clinical suitability, accessibility for
switch or eye-gaze users, screen-reader support, audio-hardware compatibility,
or therapeutic appropriateness. Those require review by AAC professionals and
representative users.

For data recovery or release testing, follow `docs/RELEASE_READINESS.md`.
Use physical SQLite backups and authenticated export/import in disposable test
copies only; do not delete real user data as part of a scenario.

## Historical source

The original CDP walkthroughs were intentionally removed from this execution
guide because they referenced unavailable tooling and could open or clear a
user's browser state. The individual scenario files remain historical
checklists; their current-state notices mark all credentials, URLs, commands,
and cleanup snippets as non-executable provenance.
