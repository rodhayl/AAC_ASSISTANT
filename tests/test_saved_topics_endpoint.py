"""Tests for the saved-topics API (server-side topic storage).

Covers GET /api/learning/topics/saved (owner + roster-student visibility),
POST (teacher/admin only), and DELETE (owner, admin override, 404).
"""
import pytest
from fastapi.testclient import TestClient

from src.aac_app.models import SavedTopic, StudentTeacher, User
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
    response = client.post(
        "/api/learning/topics/saved",
        json={"topic": "Animales", "board": "Los animales", "board_id": 7},
        headers=create_test_headers(teacher_user.id, teacher_user.username, "teacher"),
    )
    assert response.status_code == 201
    created = response.json()
    assert created["topic"] == "Animales"
    assert created["board"] == "Los animales"
    assert created["board_id"] == 7
    assert created["user_id"] == teacher_user.id
    assert created["created_by"] == "Saved Topics Teacher"
    assert "id" in created and "created_at" in created

    listed = client.get(
        "/api/learning/topics/saved",
        headers=create_test_headers(teacher_user.id, teacher_user.username, "teacher"),
    )
    assert listed.status_code == 200
    assert [entry["topic"] for entry in listed.json()] == ["Animales"]


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
