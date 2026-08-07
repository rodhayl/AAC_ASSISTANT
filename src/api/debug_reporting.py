"""Optional debug reporting for local investigations.

Production requests must not perform synchronous calls to an investigation
server. Reporting is disabled unless ``AAC_DEBUG_REPORTS`` is explicitly true,
and each location is emitted at most once per process.
"""

from __future__ import annotations

import contextlib
import json
import os
import threading
import time
from pathlib import Path
from urllib import request

from src import config

_reported_locations: set[tuple[str, str]] = set()
_report_lock = threading.Lock()


def _enabled() -> bool:
    """Return whether investigation reporting is allowed in this process.

    The explicit opt-in remains required in development, while production is
    always fail-closed even if a stale environment variable enables reports.
    """
    environment = os.environ.get("ENVIRONMENT", config.ENVIRONMENT).strip().casefold()
    if environment == "production":
        return False
    return os.environ.get("AAC_DEBUG_REPORTS", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _settings() -> tuple[str, str]:
    url = os.environ.get("AAC_DEBUG_SERVER_URL", "http://127.0.0.1:7777/event")
    session_id = os.environ.get("AAC_DEBUG_SESSION_ID", "server-shutdown-hang")
    env_path = Path(".dbg/server-shutdown-hang.env")
    if env_path.is_file():
        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("DEBUG_SERVER_URL="):
                    url = line.split("=", 1)[1].strip() or url
                elif line.startswith("DEBUG_SESSION_ID="):
                    session_id = line.split("=", 1)[1].strip() or session_id
        except OSError:
            pass
    return url, session_id


def report_debug(
    hypothesis_id: str,
    location: str,
    msg: str,
    data: dict | None = None,
) -> None:
    """Queue one best-effort debug report without blocking application code."""
    if not _enabled():
        return

    key = (hypothesis_id, location)
    with _report_lock:
        if key in _reported_locations:
            return
        _reported_locations.add(key)

    url, session_id = _settings()
    payload = json.dumps(
        {
            "sessionId": session_id,
            "runId": os.environ.get("AAC_DEBUG_RUN_ID", "investigation"),
            "hypothesisId": hypothesis_id,
            "location": location,
            "msg": f"[DEBUG] {msg}",
            "data": data or {},
            "ts": int(time.time() * 1000),
        }
    ).encode()

    def send() -> None:
        with contextlib.suppress(Exception):
            request.urlopen(
                request.Request(
                    url,
                    data=payload,
                    headers={"Content-Type": "application/json"},
                ),
                timeout=1,
            ).read()

    threading.Thread(target=send, name="debug-report", daemon=True).start()
