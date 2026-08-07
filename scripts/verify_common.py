"""Shared helpers for local API verification scripts."""

from __future__ import annotations

import os
import sys
from typing import Any

import requests

BASE_URL = os.environ.get("AAC_BASE_URL", "http://localhost:8086/api").rstrip("/")
USERNAME = os.environ.get("AAC_VERIFY_USERNAME", "").strip()
PASSWORD = os.environ.get("AAC_VERIFY_PASSWORD", "").strip()


def require_credentials() -> None:
    if not USERNAME or not PASSWORD:
        raise SystemExit(
            "Set AAC_VERIFY_USERNAME and AAC_VERIFY_PASSWORD before running this script."
        )


def login() -> str:
    """Authenticate the configured verification user and return its bearer token."""
    require_credentials()
    response = requests.post(
        f"{BASE_URL}/auth/token",
        data={"username": USERNAME, "password": PASSWORD},
        timeout=5,
    )
    if response.status_code != 200:
        print(f"Login failed: {response.text}")
        sys.exit(1)
    return response.json()["access_token"]


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def ensure_ok(response: requests.Response, operation: str) -> Any:
    if not 200 <= response.status_code < 300:
        print(f"{operation} failed: {response.status_code} {response.text}")
        sys.exit(1)
    if response.status_code == 204 or not response.content:
        return None
    return response.json()
