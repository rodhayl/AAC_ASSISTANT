"""PROMPT_6 backend regressions.

- B7: the heavy write/import/AI endpoints carry ``conditional_limiter`` (marker
  check, mirroring the H8/A4 pattern) and a burst over the import budget is
  cut off with 429 while the first calls pass validation.
- B10: a vector-store inspection failure must not fail open into a full
  re-embed — ``get_stale_symbol_ids`` returns an empty set instead of every
  expected id.
- B11: the multipart ``language`` field is bound (2..10) like its JSON
  sibling; oversized values answer 422 before any work happens.
"""

import os
from contextlib import contextmanager
from unittest.mock import patch

import pytest

from tests.auth_helpers import create_test_headers


@contextmanager
def _production_limiter():
    """Run with TESTING=0 so ``conditional_limiter`` is live."""
    with patch.dict(os.environ, {"TESTING": "0"}):
        yield


def test_heavy_write_endpoints_carry_a_rate_limiter():
    """B7: import, AI board creation and symbol mutations are bounded."""
    from src.api.routers import board_ai, export_import, symbols

    handlers = (
        (export_import, "import_data"),
        (board_ai, "create_board"),
        (symbols, "create_symbol"),
        (symbols, "upload_symbol"),
        (symbols, "generate_svg_symbol"),
    )
    unlimited = [
        f"{module.__name__}.{name}"
        for module, name in handlers
        if not getattr(getattr(module, name), "__rate_limited__", False)
    ]
    assert unlimited == [], f"unlimited heavy endpoints: {unlimited}"


@pytest.mark.usefixtures("setup_test_db")
def test_import_burst_is_throttled(client, admin_user):
    """B7: the import budget (10/hour) mirrors export and cuts a burst off."""
    headers = create_test_headers(admin_user.id, admin_user.username, "admin")
    # A checksum-less payload fails validation (400) — which still consumes
    # the budget, exactly like the H8 export burst asserts via 404s.
    payload = {"meta": {}, "boards": []}

    statuses = []
    with _production_limiter():
        for _ in range(11):
            statuses.append(
                client.post("/api/data/import", json=payload, headers=headers).status_code
            )

    assert statuses[:10] == [400] * 10, statuses
    assert statuses[10] == 429, statuses


def test_vector_inspection_failure_does_not_fail_open(tmp_path):
    """B10: an inspection error returns nothing-stale (no full re-embed)."""
    from src.aac_app.services.local_vector_store import LocalVectorStore

    store = LocalVectorStore.__new__(LocalVectorStore)
    object.__setattr__(store, "_engine", None)
    # ``_ensure_schema`` succeeds (the unavailable branch is already covered),
    # then the metadata inspection itself raises.
    def _ok():
        return True

    def _boom():
        raise RuntimeError("synthetic inspection failure")

    object.__setattr__(store, "_ensure_schema", _ok)
    object.__setattr__(store, "_get_engine", _boom)

    expected = {1: "dog", 2: "cat"}
    assert store.get_stale_symbol_ids(expected) == set()


@pytest.mark.usefixtures("setup_test_db")
def test_oversized_multipart_language_is_rejected(client, admin_user):
    """B11: the multipart ``language`` field is bound like SymbolBase."""
    headers = create_test_headers(admin_user.id, admin_user.username, "admin")

    ok = client.post(
        "/api/boards/symbols/upload",
        data={"label": "dog", "language": "en"},
        files={"file": ("tiny.png", b"\x89PNG\r\n\x1a\n", "image/png")},
        headers=headers,
    )
    assert ok.status_code in (200, 400, 415), ok.text  # not 422: field itself valid

    oversized = client.post(
        "/api/boards/symbols/upload",
        data={"label": "dog", "language": "x" * 4000},
        files={"file": ("tiny.png", b"\x89PNG\r\n\x1a\n", "image/png")},
        headers=headers,
    )
    assert oversized.status_code == 422, oversized.text


@pytest.mark.usefixtures("setup_test_db")
def test_oversized_generate_svg_language_is_rejected(client, admin_user):
    """B11: the LLM generation path is bound the same way."""
    headers = create_test_headers(admin_user.id, admin_user.username, "admin")
    response = client.post(
        "/api/boards/symbols/generate-svg",
        data={"label": "dog", "language": "x" * 4000},
        headers=headers,
    )
    assert response.status_code == 422, response.text
