"""Schema string bounds must match DB columns (PROMPT_13 D2).

SQLite never enforces VARCHAR lengths, so an overlong value only explodes
on Postgres. These tests pin the schema-side 422 so oversize input is
rejected before it ever reaches a ``String(N)`` column.
"""

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from tests.auth_helpers import create_test_headers

client = TestClient(app)

pytestmark = pytest.mark.usefixtures("setup_test_db")

_LONG_256 = "x" * 256
_LONG_201 = "x" * 201
_LONG_21 = "x" * 21


def test_symbol_image_path_over_255_is_rejected(admin_user):
    """Symbol.image_path is String(255); 256 chars must fail validation."""
    headers = create_test_headers(admin_user.id, admin_user.username, "admin")
    response = client.post(
        "/api/boards/symbols",
        json={
            "label": "bound-check",
            "category": "general",
            "image_path": _LONG_256,
            "audio_path": None,
            "language": "en",
        },
        headers=headers,
    )
    assert response.status_code == 422


def test_symbol_audio_path_over_255_is_rejected(admin_user):
    """Symbol.audio_path is String(255); 256 chars must fail validation."""
    headers = create_test_headers(admin_user.id, admin_user.username, "admin")
    response = client.post(
        "/api/boards/symbols",
        json={
            "label": "bound-check",
            "category": "general",
            "image_path": None,
            "audio_path": _LONG_256,
            "language": "en",
        },
        headers=headers,
    )
    assert response.status_code == 422


def test_notification_title_over_200_is_rejected(admin_user, regular_user):
    """Notification.title is String(200); 201 chars must fail validation."""
    headers = create_test_headers(admin_user.id, admin_user.username, "admin")
    response = client.post(
        "/api/notifications",
        json={
            "user_id": regular_user.id,
            "title": _LONG_201,
            "message": "hello",
            "notification_type": "info",
            "priority": "normal",
        },
        headers=headers,
    )
    assert response.status_code == 422


def test_notification_type_and_priority_are_bounded(admin_user, regular_user):
    """notification_type/priority are String(20); 21 chars must fail."""
    headers = create_test_headers(admin_user.id, admin_user.username, "admin")
    for field in ("notification_type", "priority"):
        payload = {
            "user_id": regular_user.id,
            "title": "ok",
            "message": "hello",
            "notification_type": "info",
            "priority": "normal",
        }
        payload[field] = _LONG_21
        response = client.post(
            "/api/notifications", json=payload, headers=headers
        )
        assert response.status_code == 422, field
