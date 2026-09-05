from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)


@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("/api/auth/users", {"limit": 1001}),
        ("/api/boards/", {"limit": 1001}),
        ("/api/boards/symbols", {"limit": 1001}),
        ("/api/achievements/leaderboard", {"limit": 101}),
        ("/api/guardian-profiles/students/1/history", {"limit": 101}),
        ("/api/learning/history/1", {"limit": 1001}),
        ("/api/notifications", {"user_id": 1, "limit": 101}),
    ],
)
def test_list_endpoints_reject_oversized_limits(path, params, admin_token, setup_test_db):
    response = client.get(
        path,
        params=params,
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("/api/auth/users", {"skip": -1}),
        ("/api/boards/", {"skip": -1}),
        ("/api/boards/symbols", {"skip": -1}),
        ("/api/notifications", {"user_id": 1, "skip": -1}),
    ],
)
def test_offset_pagination_rejects_negative_offsets(path, params, admin_token, setup_test_db):
    response = client.get(
        path,
        params=params,
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("path", "params"),
    [
        # get_students (users.py) and get_student_summaries (auth_users.py)
        # must cap skip like every other paginated list endpoint; an
        # oversized OFFSET would otherwise scan the whole table for nothing.
        ("/api/users/students", {"skip": 100_001}),
        ("/api/auth/users/student-summaries", {"skip": 100_001}),
    ],
)
def test_student_list_endpoints_reject_oversized_offsets(
    path, params, admin_token, setup_test_db
):
    response = client.get(
        path,
        params=params,
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 422
