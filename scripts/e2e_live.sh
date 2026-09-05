#!/usr/bin/env bash
# Directed Playwright harness (never touches the dev database).
#
# Mirrors scripts/smoke_live.py: the server runs against a throwaway SQLite
# database inside tempfile.mkdtemp() via the real Settings keys
# DATA_DIR/DATABASE_NAME (no AAC_-prefixed path variables; Settings has no
# env prefix, so AAC_* path variables are silently ignored). The port is
# ephemeral, and both the server and the temp directory are always cleaned up
# in this same invocation.
#
# Usage (from repository root):
#   uv run bash scripts/e2e_live.sh <spec-filter> [extra playwright args...]
#
# Example:
#   uv run bash scripts/e2e_live.sh students-lifecycle
#
# The helper expects the production dist to already be current (the Playwright
# prod-guard refuses to run against a missing or stale build) and prints E2E
# LIVE OK on success.
set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "usage: scripts/e2e_live.sh <spec-filter> [extra playwright args...]" >&2
    exit 2
fi

SPEC_FILTER="$1"
shift

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SMOKE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/aac_e2e_XXXXXX")"
E2E_ADMIN_PASSWORD="Admin123"
E2E_STUDENT_PASSWORD="Student123"
E2E_TEACHER_PASSWORD="Teacher123"

cleanup() {
    if [[ -n "${SERVER_PID:-}" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
        kill "$SERVER_PID" 2>/dev/null || true
        wait "$SERVER_PID" 2>/dev/null || true
    fi
    if [[ "${KEEP_TEMPDIR:-0}" != "1" ]]; then
        rm -rf "$SMOKE_DIR"
    else
        echo "tempdir kept for debugging: $SMOKE_DIR"
    fi
}
trap cleanup EXIT

export DATA_DIR="$SMOKE_DIR"
export DATABASE_NAME="e2e.db"
export AAC_BOOTSTRAP_ADMIN_PASSWORD="$E2E_ADMIN_PASSWORD"
export AAC_ENABLE_SYMBOL_IMAGE_BACKFILL="false"
export AAC_ENABLE_NGRAM_REBUILD="false"
# Seed the same demo users, board, assignments, symbols, and achievements that
# the existing directed specs assert. Passwords are explicit only inside this
# throwaway process environment and are never written to the repository.
export AAC_SEED_SAMPLE_DATA="true"
export AAC_SEED_ADMIN1_PASSWORD="$E2E_ADMIN_PASSWORD"
export AAC_SEED_STUDENT1_PASSWORD="$E2E_STUDENT_PASSWORD"
export AAC_SEED_TEACHER1_PASSWORD="$E2E_TEACHER_PASSWORD"

PORT="$(python3 - <<'PY'
import socket
with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    print(s.getsockname()[1])
PY
)"
export PLAYWRIGHT_BASE_URL="http://127.0.0.1:$PORT"

echo "[e2e-live] bootstrapping throwaway database in $SMOKE_DIR"
(
    cd "$ROOT"
    AAC_BOOTSTRAP_ADMIN_PASSWORD="$E2E_ADMIN_PASSWORD" \
    uv run python scripts/ensure_bootstrap_admin.py
) >"$SMOKE_DIR/bootstrap.log" 2>&1 || {
    echo "[e2e-live] bootstrap failed; log tail:"
    tail -20 "$SMOKE_DIR/bootstrap.log"
    exit 1
}

echo "[e2e-live] starting uvicorn on port $PORT"
(
    cd "$ROOT"
    exec uv run python -m uvicorn src.api.main:app --host 127.0.0.1 --port "$PORT"
) >"$SMOKE_DIR/server.log" 2>&1 &
SERVER_PID=$!

for _ in $(seq 1 120); do
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
        echo "[e2e-live] server exited early; log tail:"
        tail -30 "$SMOKE_DIR/server.log"
        exit 1
    fi
    if curl -fsS "$PLAYWRIGHT_BASE_URL/api/health" >/dev/null 2>&1; then
        break
    fi
    sleep 1
done
if ! curl -fsS "$PLAYWRIGHT_BASE_URL/api/health" >/dev/null 2>&1; then
    echo "[e2e-live] server did not become healthy; log tail:"
    tail -30 "$SMOKE_DIR/server.log"
    exit 1
fi
echo "[e2e-live] server healthy"

# The auth setup project logs admin1/student1/teacher1 in through the UI, so
# those accounts must exist in the throwaway database.
(
    cd "$ROOT"
    DATA_DIR="$SMOKE_DIR" DATABASE_NAME="e2e.db" \
    AAC_BOOTSTRAP_ADMIN_PASSWORD="$E2E_ADMIN_PASSWORD" \
    uv run python - <<'PY'
import os
import sys

sys.path.insert(0, os.getcwd())

from src.aac_app.db import create_session_factory
from src.aac_app.models import User
from src.aac_app.services.auth_service import get_password_hash

factory = create_session_factory()
passwords = {
    "admin1": os.environ["AAC_BOOTSTRAP_ADMIN_PASSWORD"],
    "student1": "Student123",
    "teacher1": "Teacher123",
}
with factory() as db:
    for username, password in passwords.items():
        existing = db.query(User).filter(User.username == username).first()
        if existing is None:
            db.add(
                User(
                    username=username,
                    display_name=username.title(),
                    user_type="admin" if username == "admin1" else (
                        "student" if username == "student1" else "teacher"
                    ),
                    password_hash=get_password_hash(password),
                    is_active=True,
                )
            )
    db.commit()
print("[e2e-live] e2e accounts ready")
PY
)

echo "[e2e-live] running playwright spec filter: $SPEC_FILTER"
(
    cd "$ROOT/src/frontend"
    npx playwright test "$SPEC_FILTER" "$@"
)
echo "E2E LIVE OK"
