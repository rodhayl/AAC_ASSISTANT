"""Reusable live-server smoke test (never touches the dev database).

Hard rules baked into this harness:
- The server runs against a throwaway SQLite database inside
  ``tempfile.mkdtemp()`` via ``DATA_DIR``/``DATABASE_NAME`` (the real
  Settings names; ``Settings`` has **no** ``AAC_`` env prefix, so ``AAC_*``
  path variables are silently ignored — setting them made a previous smoke
  run hit the dev database and leak rows into it).
- The port is ephemeral (bound to 0), never the fixed dev port 8086.
- The server process is always killed in a ``finally`` block within this
  single invocation; the temp directory is removed afterwards.

What it verifies (the F3 smoke contract):
- ``GET /api/health`` -> 200
- ``GET /ready``      -> 200 with ``"ready": true``
- ``POST /api/auth/token`` (OAuth2 **form-data**, not JSON) -> token
- ``POST /api/boards/{id}/assign`` twice -> ``{"ok": true}`` both times and
  exactly **one** ``board_assignments`` row (idempotency + uniqueness)
- ``GET /api/auth/me`` with the token -> 200 (protected resource)

Usage:
    uv run python scripts/smoke_live.py

Exit code 0 prints ``SMOKE OK``; any failure prints diagnostics and exits 1.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STARTUP_TIMEOUT_SECONDS = 120.0
READY_TIMEOUT_SECONDS = 120.0
SMOKE_ADMIN_PASSWORD = "Admin123"
# Real Settings keys (no AAC_ prefix): real environment variables take
# precedence over .env in pydantic-settings, so the temp database is used.
PATH_ENV = {"DATA_DIR": None, "DATABASE_NAME": "smoke.db"}
# Real optional-feature switches to keep warmup light and offline.
FEATURE_ENV = {
    "AAC_BOOTSTRAP_ADMIN_PASSWORD": SMOKE_ADMIN_PASSWORD,
    "AAC_ENABLE_SYMBOL_IMAGE_BACKFILL": "false",
    "AAC_ENABLE_NGRAM_REBUILD": "false",
    "AAC_SEED_SAMPLE_DATA": "false",
}


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _http(
    method: str,
    url: str,
    *,
    form: dict[str, str] | None = None,
    json_body: dict | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, str]:
    data = None
    request_headers = dict(headers or {})
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        request_headers.setdefault(
            "Content-Type", "application/x-www-form-urlencoded"
        )
    elif json_body is not None:
        data = json.dumps(json_body).encode()
        request_headers.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(url, data=data, method=method)
    for key, value in request_headers.items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode(errors="replace")


def _wait_for(url: str, predicate, timeout: float, what: str) -> str:
    deadline = time.monotonic() + timeout
    last_status, last_body = 0, ""
    while time.monotonic() < deadline:
        try:
            last_status, last_body = _http("GET", url)
            if predicate(last_status, last_body):
                return last_body
        except (urllib.error.URLError, ConnectionError, OSError):
            pass
        time.sleep(0.5)
    raise RuntimeError(
        f"timed out waiting for {what}: last status={last_status} body={last_body[:200]}"
    )


def main() -> int:
    smoke_dir = tempfile.mkdtemp(prefix="aac_smoke_")
    env = dict(os.environ)
    env["DATA_DIR"] = smoke_dir
    env["DATABASE_NAME"] = PATH_ENV["DATABASE_NAME"]
    env.update(FEATURE_ENV)
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    log_path = Path(smoke_dir) / "server.log"
    server: subprocess.Popen | None = None
    try:
        # Bootstrap the throwaway database (schema + admin user) exactly like
        # scripts/start_server.py does before launching uvicorn.
        bootstrap = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "scripts" / "ensure_bootstrap_admin.py")],
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
        )
        if bootstrap.returncode != 0:
            print("bootstrap failed:", bootstrap.stdout, bootstrap.stderr)
            return 1

        log_file = log_path.open("w", encoding="utf-8")
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "src.api.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=PROJECT_ROOT,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )

        _wait_for(
            f"{base_url}/api/health",
            lambda status, _body: status == 200,
            STARTUP_TIMEOUT_SECONDS,
            "/api/health",
        )
        print(f"health OK on port {port}")
        ready_body = _wait_for(
            f"{base_url}/ready",
            lambda status, body: status == 200 and '"ready":true' in body.replace(" ", ""),
            READY_TIMEOUT_SECONDS,
            "/ready",
        )
        ready = json.loads(ready_body)
        if not ready.get("ready"):
            print("server reported not ready:", ready_body)
            return 1
        print("ready OK:", ready.get("status"))

        status, body = _http(
            "POST",
            f"{base_url}/api/auth/token",
            form={"username": "admin1", "password": SMOKE_ADMIN_PASSWORD},
        )
        if status != 200:
            print("token login failed:", status, body)
            return 1
        token = json.loads(body)["access_token"]
        print("token login OK (form-data)")

        auth = {"Authorization": f"Bearer {token}"}
        status, body = _http(
            "POST",
            f"{base_url}/api/auth/admin/create-user",
            headers=auth,
            json_body={
                "username": "smoke_student",
                "display_name": "Smoke Student",
                "user_type": "student",
                "password": "Student123",
                "confirm_password": "Student123",
            },
        )
        if status != 200:
            print("student creation failed:", status, body)
            return 1
        student_id = json.loads(body)["id"]

        status, body = _http(
            "POST",
            f"{base_url}/api/boards?user_id=1",
            headers=auth,
            json_body={"name": "SmokeBoard", "grid_rows": 2, "grid_cols": 2},
        )
        if status != 200:
            print("board creation failed:", status, body)
            return 1
        board_id = json.loads(body)["id"]
        print(f"student id={student_id}, board id={board_id}")

        for attempt in (1, 2):
            status, body = _http(
                "POST",
                f"{base_url}/api/boards/{board_id}/assign",
                headers=auth,
                json_body={"student_id": student_id},
            )
            if status != 200 or json.loads(body) != {"ok": True}:
                print(f"assign #{attempt} failed:", status, body)
                return 1
        print('double assign OK (both {"ok": true})')

        database_path = Path(smoke_dir) / PATH_ENV["DATABASE_NAME"]
        with sqlite3.connect(database_path) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM board_assignments WHERE board_id = ? AND student_id = ?",
                (board_id, student_id),
            ).fetchone()[0]
        if count != 1:
            print(f"expected exactly 1 assignment row, found {count}")
            return 1
        print("assignment idempotency OK (exactly 1 row)")

        status, body = _http("GET", f"{base_url}/api/auth/me", headers=auth)
        if status != 200:
            print("protected GET failed:", status, body)
            return 1
        print("protected GET OK (/api/auth/me 200)")

        print("SMOKE OK")
        return 0
    except RuntimeError as exc:
        print("SMOKE FAILED:", exc)
        if log_path.exists():
            print("--- server log tail ---")
            print("\n".join(log_path.read_text(encoding="utf-8").splitlines()[-25:]))
        return 1
    finally:
        if server is not None and server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=15)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=10)
        if server is not None:
            log_file = None
        shutil.rmtree(smoke_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
