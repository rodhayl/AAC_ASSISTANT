import base64
import json

import pytest
from fastapi.testclient import TestClient

from src.aac_app.models import (
    Achievement,
    BoardAssignment,
    CommunicationBoard,
    Symbol,
    User,
    UserAchievement,
)
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
    # Sign the canonical payload with the server-side export integrity key.
    checksum = compute_checksum(base)
    payload = {
        **base,
        "meta": {
            **base["meta"],
            "checksum_sha256": checksum,
            "schema_version": "2",
        },
    }
    # Import
    imp = client.post("/api/data/import", json=payload, headers=headers)
    assert imp.status_code == 200

    exported = client.get(
        "/api/data/export",
        params={"username": "importer"},
        headers=headers,
    )
    assert exported.status_code == 200
    exported_payload = exported.json()
    tampered = {
        **exported_payload,
        "totalPoints": exported_payload["totalPoints"] + 1,
    }
    assert (
        client.post("/api/data/import", json=tampered, headers=headers).status_code
        == 400
    )
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

    # A client can calculate the old public SHA-256 digest, but it must not
    # authenticate a new import because it has no server-side secret.
    import hashlib

    unsigned_digest = hashlib.sha256(
        json.dumps(base, separators=(",", ":"), sort_keys=True, ensure_ascii=False).encode(
            "utf-8"
        )
    ).hexdigest()
    unsigned = {
        **base,
        "meta": {**base["meta"], "checksum_sha256": unsigned_digest},
    }
    assert client.post("/api/data/import", json=unsigned, headers=headers).status_code == 400

    legacy = {
        **payload,
        "meta": {
            **payload["meta"],
            "schema_version": "1",
            "checksum_sha256": unsigned_digest,
        },
    }
    legacy_response = client.post("/api/data/import", json=legacy, headers=headers)
    assert legacy_response.status_code == 400
    assert "older export format" in legacy_response.json()["detail"]

    unsupported = {
        **payload,
        "meta": {**payload["meta"], "schema_version": "999"},
    }
    unsupported_response = client.post("/api/data/import", json=unsupported, headers=headers)
    assert unsupported_response.status_code == 400
    assert "Unsupported export schema version" in unsupported_response.json()["detail"]

    missing_version = {**payload, "meta": {**payload["meta"]}}
    missing_version["meta"].pop("schema_version")
    missing_response = client.post("/api/data/import", json=missing_version, headers=headers)
    assert missing_response.status_code == 400
    assert "Unsupported export schema version" in missing_response.json()["detail"]


def test_import_preserves_achievement_earned_at_and_rejects_invalid_timestamp(
    client, test_db_session
):
    registration = client.post(
        "/api/auth/register",
        json={
            "username": "achievement_importer",
            "password": "AchievementImport123",
            "display_name": "Achievement Importer",
            "user_type": "student",
        },
    )
    assert registration.status_code == 200
    user_id = registration.json()["id"]
    headers = create_test_headers(user_id, "achievement_importer", "student")
    earned_at = "2024-01-02T03:04:05"
    base = {
        "meta": {
            "exported_at": "2024-01-01T00:00:00Z",
            "username": "achievement_importer",
        },
        "boards": [],
        "assignedBoards": [],
        "achievements": [
            {
                "name": "Imported Achievement",
                "description": "Preserved history",
                "category": "general",
                "points": 10,
                "icon": "🏆",
                "earned_at": earned_at,
            }
        ],
        "totalPoints": 10,
        "learningHistory": [],
    }
    payload = {
        **base,
        "meta": {
            **base["meta"],
            "checksum_sha256": compute_checksum(base),
            "schema_version": "2",
        },
    }

    response = client.post("/api/data/import", json=payload, headers=headers)
    assert response.status_code == 200, response.text
    imported = (
        test_db_session.query(UserAchievement)
        .filter(UserAchievement.user_id == user_id)
        .one()
    )
    assert imported.earned_at is not None
    assert imported.earned_at.isoformat() == earned_at

    empty_timestamp_payload = {
        **base,
        "achievements": [
            {**base["achievements"][0], "earned_at": ""}
        ],
    }
    empty_timestamp_payload["meta"] = {
        **empty_timestamp_payload["meta"],
        "checksum_sha256": compute_checksum(empty_timestamp_payload),
        "schema_version": "2",
    }
    empty_timestamp_response = client.post(
        "/api/data/import", json=empty_timestamp_payload, headers=headers
    )
    assert empty_timestamp_response.status_code == 400
    assert "Invalid achievement timestamp" in empty_timestamp_response.json()["detail"]

    missing_timestamp_base = {
        **base,
        "achievements": [
            {
                **base["achievements"][0],
                "name": "Legacy Achievement Without Timestamp",
            }
        ],
    }
    missing_timestamp_base["achievements"][0].pop("earned_at")
    missing_timestamp_payload = {
        **missing_timestamp_base,
        "meta": {
            **missing_timestamp_base["meta"],
            "checksum_sha256": compute_checksum(missing_timestamp_base),
            "schema_version": "2",
        },
    }
    missing_timestamp_response = client.post(
        "/api/data/import", json=missing_timestamp_payload, headers=headers
    )
    assert missing_timestamp_response.status_code == 200, missing_timestamp_response.text
    missing_timestamp = (
        test_db_session.query(UserAchievement)
        .join(Achievement)
        .filter(
            UserAchievement.user_id == user_id,
            Achievement.name == "Legacy Achievement Without Timestamp",
        )
        .one()
    )
    assert missing_timestamp.earned_at is None

    changed_timestamp_base = {
        **base,
        "achievements": [
            {**base["achievements"][0], "earned_at": "2025-02-03T04:05:06"}
        ],
    }
    changed_timestamp_payload = {
        **changed_timestamp_base,
        "meta": {
            **changed_timestamp_base["meta"],
            "checksum_sha256": compute_checksum(changed_timestamp_base),
            "schema_version": "2",
        },
    }
    replay_response = client.post(
        "/api/data/import", json=changed_timestamp_payload, headers=headers
    )
    assert replay_response.status_code == 200, replay_response.text
    test_db_session.expire_all()
    replayed = (
        test_db_session.query(UserAchievement)
        .join(Achievement)
        .filter(
            UserAchievement.user_id == user_id,
            Achievement.name == "Imported Achievement",
        )
        .one()
    )
    assert replayed.earned_at.isoformat() == earned_at

    invalid_base = {
        **base,
        "achievements": [
            {
                **base["achievements"][0],
                "name": "Malformed Imported Achievement",
                "earned_at": "not-a-date",
            }
        ],
    }
    invalid_payload = {
        **invalid_base,
        "meta": {
            **invalid_base["meta"],
            "checksum_sha256": compute_checksum(invalid_base),
            "schema_version": "2",
        },
    }
    invalid_response = client.post(
        "/api/data/import", json=invalid_payload, headers=headers
    )
    assert invalid_response.status_code == 400
    assert "Invalid achievement timestamp" in invalid_response.json()["detail"]
    assert (
        test_db_session.query(Achievement)
        .filter(Achievement.name == "Imported Achievement")
        .count()
        == 1
    )
    malformed_achievement = (
        test_db_session.query(Achievement)
        .filter(Achievement.name == "Malformed Imported Achievement")
        .first()
    )
    assert malformed_achievement is None
    assert (
        test_db_session.query(UserAchievement)
        .join(Achievement)
        .filter(
            UserAchievement.user_id == user_id,
            Achievement.name == "Malformed Imported Achievement",
        )
        .count()
        == 0
    )
    assert (
        test_db_session.query(UserAchievement)
        .filter(UserAchievement.user_id == user_id)
        .count()
        == 2
    )


def test_export_import_preserves_symbol_color_and_audio_path(client, test_db_session):
    registration = client.post(
        "/api/auth/register",
        json={
            "username": "symbol_fields_importer",
            "password": "SymbolFields123",
            "display_name": "Symbol Fields Importer",
            "user_type": "student",
        },
    )
    assert registration.status_code == 200
    user_id = registration.json()["id"]
    headers = create_test_headers(user_id, "symbol_fields_importer", "student")

    symbol = Symbol(
        label="colored",
        category="general",
        audio_path="/uploads/colored.wav",
    )
    test_db_session.add(symbol)
    test_db_session.commit()
    test_db_session.refresh(symbol)

    base = {
        "meta": {
            "exported_at": "2024-01-01T00:00:00Z",
            "username": "symbol_fields_importer",
        },
        "boards": [
            {
                "name": "Color Board",
                "description": "",
                "category": "general",
                "is_public": False,
                "is_template": False,
                "grid_rows": 4,
                "grid_cols": 5,
                "symbols": [
                    {
                        "symbol_id": symbol.id,
                        "position_x": 1,
                        "position_y": 2,
                        "size": 1,
                        "is_visible": True,
                        "custom_text": "hi",
                        "color": "#ff0000",
                        "linked_board_id": 999999,
                        "symbol": {"id": symbol.id, "audio_path": "/uploads/colored.wav"},
                    }
                ],
            }
        ],
        "assignedBoards": [],
        "achievements": [],
        "totalPoints": 0,
        "learningHistory": [],
    }
    payload = {
        **base,
        "meta": {
            **base["meta"],
            "checksum_sha256": compute_checksum(base),
            "schema_version": "2",
        },
    }

    imported = client.post("/api/data/import", json=payload, headers=headers)
    assert imported.status_code == 200, imported.text

    exported = client.get(
        "/api/data/export",
        params={"username": "symbol_fields_importer"},
        headers=headers,
    )
    assert exported.status_code == 200, exported.text
    board = next(
        board for board in exported.json()["boards"] if board["name"] == "Color Board"
    )
    assert len(board["symbols"]) == 1
    assert board["symbols"][0]["color"] == "#ff0000"
    assert board["symbols"][0]["linked_board_id"] is None
    assert board["symbols"][0]["symbol"]["audio_path"] == "/uploads/colored.wav"


def test_replaying_same_import_is_idempotent(client):
    registration = client.post(
        "/api/auth/register",
        json={
            "username": "replay_importer",
            "password": "ReplayPass123",
            "display_name": "Replay Importer",
            "user_type": "student",
        },
    )
    assert registration.status_code == 200
    user_id = registration.json()["id"]
    headers = create_test_headers(user_id, "replay_importer", "student")
    base = {
        "meta": {
            "exported_at": "2024-01-01T00:00:00Z",
            "username": "replay_importer",
        },
        "boards": [
            {
                "name": "Replay Board",
                "description": "Same content on retry",
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
        "learningHistory": [
            {
                "topic_name": "animals",
                "purpose": "practice",
                "status": "completed",
                "comprehension_score": 0.5,
                "questions_asked": 2,
                "questions_answered": 1,
                "correct_answers": 1,
                "started_at": "2024-01-01T10:00:00",
                "ended_at": "2024-01-01T10:05:00",
            }
        ],
    }
    payload = {
        **base,
        "meta": {**base["meta"], "checksum_sha256": compute_checksum(base), "schema_version": "2"},
    }

    first = client.post("/api/data/import", json=payload, headers=headers)
    assert first.status_code == 200, first.text
    second = client.post("/api/data/import", json=payload, headers=headers)
    assert second.status_code == 200, second.text

    boards = client.get("/api/boards/", params={"user_id": user_id}, headers=headers)
    assert boards.status_code == 200
    assert [board["name"] for board in boards.json()].count("Replay Board") == 1

    history = client.get(f"/api/learning/history/{user_id}", headers=headers)
    assert history.status_code == 200
    assert len(history.json()["sessions"]) == 1


def test_replaying_assigned_board_import_is_idempotent(client, test_db_session):
    registration = client.post(
        "/api/auth/register",
        json={
            "username": "assigned_replay_importer",
            "password": "AssignedReplay123",
            "display_name": "Assigned Replay Importer",
            "user_type": "student",
        },
    )
    assert registration.status_code == 200
    student_id = registration.json()["id"]
    headers = create_test_headers(
        student_id, "assigned_replay_importer", "student"
    )

    owner = User(
        username="assigned_replay_owner",
        display_name="Assigned Replay Owner",
        password_hash="test-hash",
        user_type="student",
    )
    test_db_session.add(owner)
    test_db_session.flush()
    source_board = CommunicationBoard(
        user_id=owner.id,
        name="External Replay Board",
        description="External board",
        category="general",
        grid_rows=4,
        grid_cols=5,
    )
    test_db_session.add(source_board)
    test_db_session.commit()
    test_db_session.refresh(source_board)

    base = {
        "meta": {
            "exported_at": "2024-01-01T00:00:00Z",
            "username": "assigned_replay_importer",
        },
        "boards": [],
        "assignedBoards": [
            {
                "id": source_board.id,
                "name": source_board.name,
                "description": source_board.description,
                "category": source_board.category,
                "is_public": False,
                "is_template": False,
                "grid_rows": 4,
                "grid_cols": 5,
                "symbols": [],
            }
        ],
        "achievements": [],
        "totalPoints": 0,
        "learningHistory": [],
    }
    payload = {
        **base,
        "meta": {
            **base["meta"],
            "checksum_sha256": compute_checksum(base),
            "schema_version": "2",
        },
    }

    assert client.post("/api/data/import", json=payload, headers=headers).status_code == 200
    assert client.post("/api/data/import", json=payload, headers=headers).status_code == 200

    imported = (
        test_db_session.query(CommunicationBoard)
        .filter(
            CommunicationBoard.user_id == student_id,
            CommunicationBoard.name == source_board.name,
        )
        .all()
    )
    assert len(imported) == 1
    assignments = (
        test_db_session.query(BoardAssignment)
        .filter(
            BoardAssignment.board_id == imported[0].id,
            BoardAssignment.student_id == student_id,
        )
        .all()
    )
    assert len(assignments) == 1


def test_assigned_import_does_not_reuse_same_id_name_with_different_content(
    client, test_db_session
):
    registration = client.post(
        "/api/auth/register",
        json={
            "username": "collision_importer",
            "password": "CollisionPass123",
            "display_name": "Collision Importer",
            "user_type": "student",
        },
    )
    assert registration.status_code == 200
    student_id = registration.json()["id"]
    headers = create_test_headers(student_id, "collision_importer", "student")
    local_board = CommunicationBoard(
        user_id=student_id,
        name="Collision Board",
        description="Local content",
        category="general",
        grid_rows=4,
        grid_cols=5,
    )
    test_db_session.add(local_board)
    test_db_session.commit()
    test_db_session.refresh(local_board)

    base = {
        "meta": {
            "exported_at": "2024-01-01T00:00:00Z",
            "username": "collision_importer",
        },
        "boards": [],
        "assignedBoards": [
            {
                "id": local_board.id,
                "name": local_board.name,
                "description": "Imported content",
                "category": "general",
                "is_public": False,
                "is_template": False,
                "grid_rows": 4,
                "grid_cols": 5,
                "symbols": [],
            }
        ],
        "achievements": [],
        "totalPoints": 0,
        "learningHistory": [],
    }
    payload = {
        **base,
        "meta": {
            **base["meta"],
            "checksum_sha256": compute_checksum(base),
            "schema_version": "2",
        },
    }

    response = client.post("/api/data/import", json=payload, headers=headers)
    assert response.status_code == 200, response.text
    boards = (
        test_db_session.query(CommunicationBoard)
        .filter(
            CommunicationBoard.user_id == student_id,
            CommunicationBoard.name == local_board.name,
        )
        .all()
    )
    assert len(boards) == 2
    assert any(board.description == "Imported content" for board in boards)


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
    checksum = compute_checksum(checksum_payload)
    payload = {
        **base,
        "meta": {
            **base["meta"],
            "checksum_sha256": checksum,
            "schema_version": "2",
        },
    }

    response = client.post("/api/data/import", json=payload, headers=headers)
    assert response.status_code == 400

    boards = client.get("/api/boards/", params={"user_id": user_id}, headers=headers)
    assert boards.status_code == 200
    assert all(board["name"] != "Should Roll Back" for board in boards.json())


def test_import_rejects_malformed_and_oversized_payloads(client):
    registration = client.post(
        "/api/auth/register",
        json={
            "username": "bounded_importer",
            "password": "BoundedImport123",
            "display_name": "Bounded Importer",
            "user_type": "student",
        },
    )
    assert registration.status_code == 200
    user_id = registration.json()["id"]
    headers = create_test_headers(user_id, "bounded_importer", "student")

    malformed = {
        "meta": {"schema_version": "2", "username": "bounded_importer"},
        "boards": ["not-a-board"],
        "assignedBoards": [],
        "achievements": [],
        "totalPoints": 0,
        "learningHistory": [],
    }
    malformed["meta"]["checksum_sha256"] = compute_checksum(
        {
            **malformed,
            "meta": {"exported_at": None, "username": "bounded_importer"},
        }
    )
    malformed_response = client.post(
        "/api/data/import", json=malformed, headers=headers
    )
    assert malformed_response.status_code == 400
    assert malformed_response.json()["detail"] == "Invalid export data"

    invalid_symbol_base = {
        "meta": {"schema_version": "2", "username": "bounded_importer"},
        "boards": [
            {
                "name": "Invalid Symbol Board",
                "symbols": [{"symbol": {}}],
            }
        ],
        "assignedBoards": [],
        "achievements": [],
        "totalPoints": 0,
        "learningHistory": [],
    }
    invalid_symbol_base["meta"]["checksum_sha256"] = compute_checksum(
        {
            **invalid_symbol_base,
            "meta": {"exported_at": None, "username": "bounded_importer"},
        }
    )
    invalid_symbol_response = client.post(
        "/api/data/import", json=invalid_symbol_base, headers=headers
    )
    assert invalid_symbol_response.status_code == 400
    assert invalid_symbol_response.json()["detail"] == "Invalid export data"

    conflicting_symbol_base = {
        "meta": {"exported_at": None, "username": "bounded_importer"},
        "boards": [
            {
                "name": "Conflicting Symbol Board",
                "symbols": [{"symbol_id": 1, "symbol": {"id": 2}}],
            }
        ],
        "assignedBoards": [],
        "achievements": [],
        "totalPoints": 0,
        "learningHistory": [],
    }
    conflicting_symbol_payload = {
        **conflicting_symbol_base,
        "meta": {
            **conflicting_symbol_base["meta"],
            "checksum_sha256": compute_checksum(conflicting_symbol_base),
            "schema_version": "2",
        },
    }
    conflicting_symbol_response = client.post(
        "/api/data/import", json=conflicting_symbol_payload, headers=headers
    )
    assert conflicting_symbol_response.status_code == 400
    assert conflicting_symbol_response.json()["detail"] == "Invalid export data"

    missing_symbol_base = {
        "meta": {"exported_at": None, "username": "bounded_importer"},
        "boards": [
            {
                "name": "Missing Symbol Board",
                "symbols": [{"symbol_id": 999999999}],
            }
        ],
        "assignedBoards": [],
        "achievements": [],
        "totalPoints": 0,
        "learningHistory": [],
    }
    missing_symbol_payload = {
        **missing_symbol_base,
        "meta": {
            **missing_symbol_base["meta"],
            "checksum_sha256": compute_checksum(missing_symbol_base),
            "schema_version": "2",
        },
    }
    missing_symbol_response = client.post(
        "/api/data/import", json=missing_symbol_payload, headers=headers
    )
    assert missing_symbol_response.status_code == 400
    assert missing_symbol_response.json()["detail"] == "Invalid export data"

    boards = client.get("/api/boards/", params={"user_id": user_id}, headers=headers)
    assert boards.status_code == 200
    assert all(
        board["name"] != "Invalid Symbol Board" for board in boards.json()
    )

    oversized = {
        "meta": {"schema_version": "2", "username": "bounded_importer"},
        "boards": [
            {"name": f"Board {index}", "symbols": []}
            for index in range(1001)
        ],
        "assignedBoards": [],
        "achievements": [],
        "totalPoints": 0,
        "learningHistory": [],
    }
    oversized["meta"]["checksum_sha256"] = compute_checksum(
        {
            **oversized,
            "meta": {"exported_at": None, "username": "bounded_importer"},
        }
    )
    oversized_response = client.post(
        "/api/data/import", json=oversized, headers=headers
    )
    assert oversized_response.status_code == 413

    oversized_body_response = client.post(
        "/api/data/import",
        content=b"{" + b"\"x\":" + b"\"a\"" * (10 * 1024 * 1024),
        headers={**headers, "content-type": "application/json"},
    )
    assert oversized_body_response.status_code == 413

    malformed_json_response = client.post(
        "/api/data/import",
        content=b"not-json",
        headers={**headers, "content-type": "application/json"},
    )
    assert malformed_json_response.status_code == 400
    assert malformed_json_response.json()["detail"] == "Invalid export data"

    unauthenticated_response = client.post(
        "/api/data/import",
        content=b"not-json",
        headers={"content-type": "application/json"},
    )
    assert unauthenticated_response.status_code == 401


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
