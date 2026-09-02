"""Tests for the saved-topics API (server-side topic storage).

Covers GET /api/learning/topics/saved (owner + roster-student visibility),
POST (teacher/admin only), and DELETE (owner, admin override, 404).
"""
import pytest
from fastapi.testclient import TestClient

from src.aac_app.models import CommunicationBoard, SavedTopic, StudentTeacher, User
from src.aac_app.services.auth_service import get_password_hash
from src.api.main import app
from tests.auth_helpers import create_test_headers

client = TestClient(app)

pytestmark = pytest.mark.usefixtures("setup_test_db")


@pytest.fixture
def teacher_user(test_db_session):
    user = User(
        username="saved_topics_teacher",
        display_name="Saved Topics Teacher",
        user_type="teacher",
        password_hash=get_password_hash("TeacherPass123"),
        is_active=True,
    )
    test_db_session.add(user)
    test_db_session.commit()
    test_db_session.refresh(user)
    return user


@pytest.fixture
def student_user(test_db_session):
    user = User(
        username="saved_topics_student",
        display_name="Saved Topics Student",
        user_type="student",
        password_hash=get_password_hash("StudentPass123"),
        is_active=True,
    )
    test_db_session.add(user)
    test_db_session.commit()
    test_db_session.refresh(user)
    return user


def _create_topic(db, user, topic="El espacio", board="Viaje al espacio"):
    topic = SavedTopic(
        user_id=user.id,
        board=board,
        topic=topic,
        created_by=user.display_name or user.username,
    )
    db.add(topic)
    db.commit()
    db.refresh(topic)
    return topic


def test_teacher_creates_and_lists_own_topics(teacher_user, test_db_session):
    board = CommunicationBoard(user_id=teacher_user.id, name="Los animales")
    test_db_session.add(board)
    test_db_session.commit()
    test_db_session.refresh(board)

    response = client.post(
        "/api/learning/topics/saved",
        json={"topic": "Animales", "board": "Los animales", "board_id": board.id},
        headers=create_test_headers(teacher_user.id, teacher_user.username, "teacher"),
    )
    assert response.status_code == 201
    created = response.json()
    assert created["topic"] == "Animales"
    assert created["board"] == "Los animales"
    assert created["board_id"] == board.id
    assert created["user_id"] == teacher_user.id
    assert created["created_by"] == "Saved Topics Teacher"
    assert "id" in created and "created_at" in created

    listed = client.get(
        "/api/learning/topics/saved",
        headers=create_test_headers(teacher_user.id, teacher_user.username, "teacher"),
    )
    assert listed.status_code == 200
    assert [entry["topic"] for entry in listed.json()] == ["Animales"]


def test_saved_topic_rejects_missing_board(teacher_user):
    response = client.post(
        "/api/learning/topics/saved",
        json={"topic": "Animales", "board": "Los animales", "board_id": 999999},
        headers=create_test_headers(teacher_user.id, teacher_user.username, "teacher"),
    )
    assert response.status_code == 404


def test_saved_topic_rejects_private_board_owned_by_another_teacher(
    teacher_user, test_db_session
):
    other = User(
        username="saved_topics_private_board_owner",
        display_name="Private Board Owner",
        user_type="teacher",
        password_hash=get_password_hash("TeacherPass123"),
        is_active=True,
    )
    test_db_session.add(other)
    test_db_session.commit()
    test_db_session.refresh(other)
    board = CommunicationBoard(user_id=other.id, name="Private")
    test_db_session.add(board)
    test_db_session.commit()
    test_db_session.refresh(board)

    response = client.post(
        "/api/learning/topics/saved",
        json={"topic": "Privado", "board": "Private", "board_id": board.id},
        headers=create_test_headers(teacher_user.id, teacher_user.username, "teacher"),
    )
    assert response.status_code == 403


def test_saved_topic_rejects_duplicate_for_same_teacher_and_board(
    teacher_user, test_db_session
):
    board = CommunicationBoard(user_id=teacher_user.id, name="Duplicate board")
    test_db_session.add(board)
    test_db_session.commit()
    test_db_session.refresh(board)
    payload = {"topic": "Same topic", "board": "Duplicate board", "board_id": board.id}
    headers = create_test_headers(teacher_user.id, teacher_user.username, "teacher")

    first = client.post("/api/learning/topics/saved", json=payload, headers=headers)
    second = client.post("/api/learning/topics/saved", json=payload, headers=headers)

    assert first.status_code == 201
    assert second.status_code == 409


def test_saved_topic_duplicate_detection_folds_case_accents_and_whitespace(
    teacher_user, test_db_session
):
    """"Astrofísica", " astrofisica ", and "ASTROFISICA" are one topic."""
    board = CommunicationBoard(user_id=teacher_user.id, name="Fold board")
    test_db_session.add(board)
    test_db_session.commit()
    test_db_session.refresh(board)
    headers = create_test_headers(teacher_user.id, teacher_user.username, "teacher")

    first = client.post(
        "/api/learning/topics/saved",
        json={"topic": "Astrofísica", "board": "Fold board", "board_id": board.id},
        headers=headers,
    )
    variants = client.post(
        "/api/learning/topics/saved",
        json={"topic": "  astrofisica  ", "board": "Fold board", "board_id": board.id},
        headers=headers,
    )
    upper = client.post(
        "/api/learning/topics/saved",
        json={"topic": "ASTROFISICA", "board": "Fold board", "board_id": board.id},
        headers=headers,
    )

    assert first.status_code == 201
    assert variants.status_code == 409
    assert upper.status_code == 409


def test_saved_topic_exposes_created_by_user_id_and_current_name(
    teacher_user, test_db_session
):
    board = CommunicationBoard(user_id=teacher_user.id, name="Identity board")
    test_db_session.add(board)
    test_db_session.commit()
    test_db_session.refresh(board)

    created = client.post(
        "/api/learning/topics/saved",
        json={"topic": "Topic", "board": "Identity board", "board_id": board.id},
        headers=create_test_headers(teacher_user.id, teacher_user.username, "teacher"),
    )
    assert created.status_code == 201
    payload = created.json()
    assert payload["created_by_user_id"] == teacher_user.id
    assert payload["created_by_name"] == "Saved Topics Teacher"

    teacher_user.display_name = "Renamed Teacher"
    test_db_session.commit()

    listed = client.get(
        "/api/learning/topics/saved",
        headers=create_test_headers(teacher_user.id, teacher_user.username, "teacher"),
    )
    assert listed.status_code == 200
    entry = next(item for item in listed.json() if item["id"] == payload["id"])
    # The stable name is refreshed from the user row; legacy field keeps old.
    assert entry["created_by_name"] == "Renamed Teacher"
    assert entry["created_by"] == "Saved Topics Teacher"



def test_saved_topic_accepts_owned_board(teacher_user, test_db_session):
    board = CommunicationBoard(user_id=teacher_user.id, name="Owned")
    test_db_session.add(board)
    test_db_session.commit()
    test_db_session.refresh(board)

    response = client.post(
        "/api/learning/topics/saved",
        json={"topic": "Owned topic", "board": "Owned", "board_id": board.id},
        headers=create_test_headers(teacher_user.id, teacher_user.username, "teacher"),
    )
    assert response.status_code == 201
    assert response.json()["board_id"] == board.id


def test_student_cannot_create_topic(student_user):
    response = client.post(
        "/api/learning/topics/saved",
        json={"topic": "Hola"},
        headers=create_test_headers(student_user.id, student_user.username, "student"),
    )
    assert response.status_code == 403


def test_student_sees_roster_teachers_topics(student_user, teacher_user, test_db_session):
    _create_topic(test_db_session, teacher_user, "Astronomía", "El cielo")
    _create_topic(test_db_session, teacher_user, "Cocina", "Recetas")

    # No roster yet: the student sees nothing.
    response = client.get(
        "/api/learning/topics/saved",
        headers=create_test_headers(student_user.id, student_user.username, "student"),
    )
    assert response.status_code == 200
    assert response.json() == []

    test_db_session.add(
        StudentTeacher(teacher_id=teacher_user.id, student_id=student_user.id)
    )
    test_db_session.commit()

    response = client.get(
        "/api/learning/topics/saved",
        headers=create_test_headers(student_user.id, student_user.username, "student"),
    )
    assert response.status_code == 200
    assert [entry["topic"] for entry in response.json()] == ["Cocina", "Astronomía"]


def test_student_does_not_see_unrelated_teachers_topics(
    student_user, teacher_user, test_db_session
):
    other = User(
        username="saved_topics_other_teacher",
        display_name="Other Teacher",
        user_type="teacher",
        password_hash=get_password_hash("TeacherPass123"),
        is_active=True,
    )
    test_db_session.add(other)
    test_db_session.commit()
    test_db_session.refresh(other)

    _create_topic(test_db_session, other, "Geografía", "Mapas")
    test_db_session.add(
        StudentTeacher(teacher_id=teacher_user.id, student_id=student_user.id)
    )
    test_db_session.commit()

    response = client.get(
        "/api/learning/topics/saved",
        headers=create_test_headers(student_user.id, student_user.username, "student"),
    )
    assert response.json() == []


def test_teacher_does_not_see_other_teachers_topics(
    teacher_user, test_db_session
):
    other = User(
        username="saved_topics_other_teacher2",
        display_name="Other Teacher 2",
        user_type="teacher",
        password_hash=get_password_hash("TeacherPass123"),
        is_active=True,
    )
    test_db_session.add(other)
    test_db_session.commit()
    test_db_session.refresh(other)

    _create_topic(test_db_session, other, "Música", "Notas")
    response = client.get(
        "/api/learning/topics/saved",
        headers=create_test_headers(teacher_user.id, teacher_user.username, "teacher"),
    )
    assert response.json() == []


def test_owner_deletes_own_topic(teacher_user, test_db_session):
    topic = _create_topic(test_db_session, teacher_user)
    response = client.delete(
        f"/api/learning/topics/saved/{topic.id}",
        headers=create_test_headers(teacher_user.id, teacher_user.username, "teacher"),
    )
    assert response.status_code == 204
    assert test_db_session.query(SavedTopic).filter(SavedTopic.id == topic.id).first() is None


def test_teacher_cannot_delete_other_teachers_topic(teacher_user, test_db_session):
    other = User(
        username="saved_topics_other_teacher3",
        display_name="Other Teacher 3",
        user_type="teacher",
        password_hash=get_password_hash("TeacherPass123"),
        is_active=True,
    )
    test_db_session.add(other)
    test_db_session.commit()
    test_db_session.refresh(other)

    topic = _create_topic(test_db_session, other, "Deportes", "Fútbol")
    response = client.delete(
        f"/api/learning/topics/saved/{topic.id}",
        headers=create_test_headers(teacher_user.id, teacher_user.username, "teacher"),
    )
    assert response.status_code == 403
    assert test_db_session.query(SavedTopic).filter(SavedTopic.id == topic.id).first() is not None


def test_admin_can_delete_any_topic(admin_user, admin_token, teacher_user, test_db_session):
    topic = _create_topic(test_db_session, teacher_user, "Historia", "Antigua Roma")
    response = client.delete(
        f"/api/learning/topics/saved/{topic.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 204


def test_delete_missing_topic_returns_404(teacher_user):
    response = client.delete(
        "/api/learning/topics/saved/999999",
        headers=create_test_headers(teacher_user.id, teacher_user.username, "teacher"),
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Admin all-teachers view (scope=all)
# ---------------------------------------------------------------------------


def test_admin_lists_all_teachers_topics_with_scope_all(
    admin_user, admin_token, teacher_user, test_db_session
):
    other = User(
        username="saved_topics_admin_scope_teacher",
        display_name="Scope Teacher",
        user_type="teacher",
        password_hash=get_password_hash("TeacherPass123"),
        is_active=True,
    )
    test_db_session.add(other)
    test_db_session.commit()
    test_db_session.refresh(other)

    t1 = _create_topic(test_db_session, teacher_user, "Astronomía", "El cielo")
    t2 = _create_topic(test_db_session, other, "Cocina", "Recetas")

    response = client.get(
        "/api/learning/topics/saved?scope=all",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    entries = response.json()
    assert [entry["id"] for entry in entries] == [t2.id, t1.id]
    by_id = {entry["id"]: entry for entry in entries}
    assert by_id[t1.id]["created_by"] == "Saved Topics Teacher"
    assert by_id[t2.id]["created_by"] == "Scope Teacher"


def test_admin_scope_all_ignores_own_topics_duplication(
    admin_user, admin_token, teacher_user, test_db_session
):
    own = _create_topic(test_db_session, admin_user, "Admin tema", "General")
    _create_topic(test_db_session, teacher_user, "Teacher tema", "Clase")

    response = client.get(
        "/api/learning/topics/saved?scope=all",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    ids = [entry["id"] for entry in response.json()]
    assert ids.count(own.id) == 1


def test_non_admin_cannot_use_scope_all(
    teacher_user, student_user, test_db_session
):
    for user, user_type in [(teacher_user, "teacher"), (student_user, "student")]:
        response = client.get(
            "/api/learning/topics/saved?scope=all",
            headers=create_test_headers(user.id, user.username, user_type),
        )
        assert response.status_code == 403


def test_list_creator_names_resolve_in_one_batch(
    teacher_user, test_db_session, monkeypatch
):
    """Many topics share creators; the list must not query per topic."""
    for index in range(5):
        _create_topic(test_db_session, teacher_user, f"Tema {index}", "Clase")

    queries = []
    original_get = test_db_session.get

    def tracking_get(entity, pk):
        queries.append((entity.__name__, pk))
        return original_get(entity, pk)

    monkeypatch.setattr(test_db_session, "get", tracking_get)

    response = client.get(
        "/api/learning/topics/saved",
        headers=create_test_headers(teacher_user.id, teacher_user.username, "teacher"),
    )
    assert response.status_code == 200
    entries = response.json()
    assert len(entries) == 5
    assert all(entry["created_by_name"] == "Saved Topics Teacher" for entry in entries)
    # The batched resolver must not fall back to per-topic db.get(User, id).
    assert not any(entity == "User" for entity, _pk in queries)


def test_list_pagination_limit_and_offset(teacher_user, test_db_session):
    for index in range(6):
        _create_topic(test_db_session, teacher_user, f"Tema {index}", "Clase")
    headers = create_test_headers(teacher_user.id, teacher_user.username, "teacher")

    full = client.get("/api/learning/topics/saved", headers=headers)
    assert full.status_code == 200
    all_ids = [entry["id"] for entry in full.json()]

    page = client.get(
        "/api/learning/topics/saved?limit=4", headers=headers
    )
    assert page.status_code == 200
    assert [entry["id"] for entry in page.json()] == all_ids[:4]

    second = client.get(
        "/api/learning/topics/saved?limit=4&offset=4", headers=headers
    )
    assert second.status_code == 200
    assert [entry["id"] for entry in second.json()] == all_ids[4:]

    # limit=0 and negative values are rejected by validation.
    invalid = client.get("/api/learning/topics/saved?limit=0", headers=headers)
    assert invalid.status_code == 422
    negative_offset = client.get(
        "/api/learning/topics/saved?offset=-1", headers=headers
    )
    assert negative_offset.status_code == 422


def test_list_creator_falls_back_to_legacy_snapshot(
    teacher_user, test_db_session
):
    """A creator whose account was deleted keeps the legacy name snapshot."""
    topic = _create_topic(test_db_session, teacher_user, "Huérfana", "Clase")
    topic.created_by_user_id = None
    test_db_session.commit()

    response = client.get(
        "/api/learning/topics/saved",
        headers=create_test_headers(teacher_user.id, teacher_user.username, "teacher"),
    )
    assert response.status_code == 200
    entry = next(item for item in response.json() if item["id"] == topic.id)
    assert entry["created_by_name"] == "Saved Topics Teacher"
