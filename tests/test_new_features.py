import base64
import json

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.api.routers.export_import import compute_checksum
from tests.test_utils_auth import create_test_headers


@pytest.fixture
def client(setup_test_db):
    return TestClient(app)


def test_change_password_flow(client):
    # Register user
    r = client.post(
        "/api/auth/register",
        json={
            "username": "u1",
            "password": "OldPass123",
            "display_name": "U1",
            "user_type": "student",
        },
    )
    assert r.status_code == 200
    user_id = r.json()["id"]

    # Login with old password works
    assert (
        client.post(
            "/api/auth/token", data={"username": "u1", "password": "OldPass123"}
        ).status_code
        == 200
    )

    # Change password
    headers = create_test_headers(user_id, "u1", "student")
    cp = client.post(
        "/api/auth/change-password",
        json={
            "username": "u1",
            "current_password": "OldPass123",
            "new_password": "NewPass123",
            "confirm_password": "NewPass123",
        },
        headers=headers,
    )
    assert cp.status_code == 200

    # Old password fails
    assert (
        client.post(
            "/api/auth/token", data={"username": "u1", "password": "OldPass123"}
        ).status_code
        == 401
    )
    # New password succeeds
    assert (
        client.post(
            "/api/auth/token", data={"username": "u1", "password": "NewPass123"}
        ).status_code
        == 200
    )


def test_symbol_search_filters(client):
    # Register user to get auth
    reg = client.post(
        "/api/auth/register",
        json={
            "username": "searcher",
            "password": "SearchPass123",
            "display_name": "Searcher",
            "user_type": "student",
        },
    )
    user_id = reg.json()["id"]
    headers = create_test_headers(user_id, "searcher", "student")

    # Create symbols
    for lbl, cat in [("apple", "food"), ("cow", "farm"), ("water", "drinks")]:
        assert (
            client.post(
                "/api/boards/symbols",
                json={"label": lbl, "category": cat},
                headers=headers,
            ).status_code
            == 200
        )
    # Search by category (public endpoint?)
    # If search requires auth, add headers. Assuming it might be public or protected. Safe to add headers.
    res = client.get(
        "/api/boards/symbols", params={"category": "food"}, headers=headers
    )
    assert res.status_code == 200
    names = [s["label"] for s in res.json()]
    assert "apple" in names and "cow" not in names
    # Search term
    res2 = client.get("/api/boards/symbols", params={"search": "wat"}, headers=headers)
    assert res2.status_code == 200
    names2 = [s["label"] for s in res2.json()]
    assert "water" in names2


def test_checksum_is_stable_when_object_keys_are_reordered():
    first = {
        "meta": {"exported_at": "2024-01-01T00:00:00Z", "username": "stable"},
        "boards": [{"name": "B1", "symbols": [{"symbol_id": 1, "position_x": 0}]}],
        "assignedBoards": [],
        "achievements": [],
        "totalPoints": 0,
        "learningHistory": [],
    }
    reordered = {
        "learningHistory": [],
        "totalPoints": 0,
        "achievements": [],
        "assignedBoards": [],
        "boards": [{"symbols": [{"position_x": 0, "symbol_id": 1}], "name": "B1"}],
        "meta": {"username": "stable", "exported_at": "2024-01-01T00:00:00Z"},
    }

    assert first == reordered
    assert compute_checksum(first) == compute_checksum(reordered)

    unicode_first = {**first, "boards": [{"name": "niño 🧸", "symbols": []}]}
    unicode_reordered = {
        "learningHistory": [],
        "totalPoints": 0,
        "achievements": [],
        "assignedBoards": [],
        "boards": [{"symbols": [], "name": "niño 🧸"}],
        "meta": {"username": "stable", "exported_at": "2024-01-01T00:00:00Z"},
    }
    assert compute_checksum(unicode_first) == compute_checksum(unicode_reordered)


def test_import_endpoint_checksum_and_boards(client):
    # Register user
    r = client.post(
        "/api/auth/register",
        json={
            "username": "importer",
            "password": "ImportPass123",
            "display_name": "Imp",
            "user_type": "student",
        },
    )
    assert r.status_code == 200
    user_id = r.json()["id"]
    headers = create_test_headers(user_id, "importer", "student")

    # Prepare export-like payload
    base = {
        "meta": {"exported_at": "2024-01-01T00:00:00Z", "username": "importer"},
        "boards": [
            {
                "name": "B1",
                "description": "D",
                "category": "general",
                "is_public": False,
                "is_template": False,
                "grid_rows": 4,
                "grid_cols": 5,
                "symbols": [],
            }
        ],
        "assignedBoards": [],
        "achievements": [],
        "totalPoints": 0,
        "learningHistory": [],
    }
    # Compute checksum like server
    raw = json.dumps(
        {
            "meta": {
                "exported_at": base["meta"]["exported_at"],
                "username": base["meta"]["username"],
            },
            "boards": base["boards"],
            "assignedBoards": base["assignedBoards"],
            "achievements": base["achievements"],
            "totalPoints": base["totalPoints"],
            "learningHistory": base["learningHistory"],
        },
        separators=(",", ":"),
    )
    import hashlib

    checksum = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    payload = {**base, "meta": {**base["meta"], "checksum_sha256": checksum}}
    # Import
    imp = client.post("/api/data/import", json=payload, headers=headers)
    assert imp.status_code == 200
    # Verify board exists via list
    lst = client.get(
        "/api/boards/", params={"user_id": r.json()["id"]}, headers=headers
    )
    assert lst.status_code == 200
    names = [b["name"] for b in lst.json()]
    assert "B1" in names
    # Tamper rejection
    bad = {**payload, "meta": {**payload["meta"], "checksum_sha256": "bad"}}
    assert client.post("/api/data/import", json=bad, headers=headers).status_code == 400


def test_import_rejects_invalid_history_atomically(client):
    registration = client.post(
        "/api/auth/register",
        json={
            "username": "atomic_importer",
            "password": "AtomicPass123",
            "display_name": "Atomic Importer",
            "user_type": "student",
        },
    )
    assert registration.status_code == 200
    user_id = registration.json()["id"]
    headers = create_test_headers(user_id, "atomic_importer", "student")

    base = {
        "meta": {
            "exported_at": "2024-01-01T00:00:00Z",
            "username": "atomic_importer",
        },
        "boards": [
            {
                "name": "Should Roll Back",
                "description": "",
                "category": "general",
                "is_public": False,
                "is_template": False,
                "grid_rows": 4,
                "grid_cols": 5,
                "symbols": [],
            }
        ],
        "assignedBoards": [],
        "achievements": [],
        "totalPoints": 0,
        "learningHistory": [{"started_at": "not-a-date"}],
    }
    checksum_payload = {
        "meta": base["meta"],
        "boards": base["boards"],
        "assignedBoards": base["assignedBoards"],
        "achievements": base["achievements"],
        "totalPoints": base["totalPoints"],
        "learningHistory": base["learningHistory"],
    }
    checksum_payload["learningHistory"] = base["learningHistory"]
    raw = json.dumps(checksum_payload, separators=(",", ":"))
    import hashlib

    checksum = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    payload = {**base, "meta": {**base["meta"], "checksum_sha256": checksum}}

    response = client.post("/api/data/import", json=payload, headers=headers)
    assert response.status_code == 400

    boards = client.get("/api/boards/", params={"user_id": user_id}, headers=headers)
    assert boards.status_code == 200
    assert all(board["name"] != "Should Roll Back" for board in boards.json())


def test_upload_validation(client):
    # Register user
    reg = client.post(
        "/api/auth/register",
        json={
            "username": "uploader",
            "password": "UploadPass123",
            "display_name": "Up",
            "user_type": "student",
        },
    )
    user_id = reg.json()["id"]
    headers = create_test_headers(user_id, "uploader", "student")

    # Prepare a non-image file content
    files = {"file": ("test.txt", b"hello", "text/plain")}
    data = {"label": "NotImage", "category": "general"}
    r = client.post(
        "/api/boards/symbols/upload", files=files, data=data, headers=headers
    )
    assert r.status_code == 400
    # Prepare small PNG data
    png_header = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    files2 = {"file": ("a.png", png_header, "image/png")}
    r2 = client.post(
        "/api/boards/symbols/upload", files=files2, data=data, headers=headers
    )
    # This might fail if the upload logic actually checks valid PNG structure beyond header or if mock FS is not set up
    # But usually 400 means validation failed. If it passes validation, it might try to save.
    # We expect success or a specific error, but definitely not 401.
    # If 200 OK, great. If 500, we might need to fix something.
    # Let's assume the test expects success or at least validation pass.
    # The original test didn't assert result for r2, implying it might just be checking it doesn't crash or returns 200.
    assert r2.status_code in [200, 201]


def test_students_update_delete(client, admin_user):
    # Create student
    stu = client.post(
        "/api/auth/register",
        json={
            "username": "stu1",
            "password": "StudentPass123",
            "display_name": "S",
            "user_type": "student",
        },
    ).json()

    # Use admin_user fixture which is a real admin in the DB
    headers = create_test_headers(admin_user.id, admin_user.username, "admin")

    # Update student
    up = client.put(
        f"/api/auth/users/{stu['id']}",
        json={"display_name": "Updated", "user_type": "student"},
        headers=headers,
    )
    assert up.status_code == 200
    assert up.json()["display_name"] == "Updated"
    # Delete student
    de = client.delete(f"/api/auth/users/{stu['id']}", headers=headers)
    assert de.status_code == 200
