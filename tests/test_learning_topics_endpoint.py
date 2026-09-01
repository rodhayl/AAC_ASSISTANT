"""Tests for the learning topic-pool endpoint and its coverage logic.

Covers the GET /api/learning/topics route (permissions, error mapping) and the
service-level pool computation (canonical + localized topic matching, coverage
window, custom-topic recents, and the block_custom_topics lock).
"""
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.aac_app.db import session_scope
from src.aac_app.models import LearningSession, StudentTeacher, User
from src.aac_app.services.auth_service import get_password_hash
from src.aac_app.services.learning.session import (
    COMMON_TOPICS,
    TOPIC_COVERAGE_WINDOW_DAYS,
    SessionLifecycleMixin,
)
from src.api.deps import get_learning_service
from src.api.main import app
from tests.auth_helpers import create_test_headers

client = TestClient(app)

pytestmark = pytest.mark.usefixtures("setup_test_db")


# ---------------------------------------------------------------------------
# Service-level pool computation
# ---------------------------------------------------------------------------

class _PoolService(SessionLifecycleMixin):
    """Minimal session mixin with the language resolution the pool uses."""

    _session_scope = staticmethod(session_scope)

    def _get_user_language(self, user_id: int, db=None) -> str:
        return "es"


def _add_session(db, user_id, topic, *, days_ago=0, purpose=""):
    session = LearningSession(
        user_id=user_id,
        topic_name=topic,
        purpose=purpose,
        started_at=datetime.now() - timedelta(days=days_ago),
    )
    db.add(session)
    return session


def test_topic_pool_returns_all_nine_common_topics_fresh(test_db_session, regular_user):
    pool = _PoolService().get_topic_pool(regular_user.id, db=test_db_session)

    assert pool["success"] is True

    assert [entry["key"] for entry in pool["common"]] == [
        key for key, _ in COMMON_TOPICS
    ]
    assert all(entry["practiced"] is False for entry in pool["common"])
    assert all(entry["last_used_at"] is None for entry in pool["common"])
    assert pool["recent"] == []


def test_topic_pool_marks_canonical_and_localized_sessions_practiced(
    test_db_session, regular_user
):
    # Canonical English topic value (frontend sends this).
    _add_session(test_db_session, regular_user.id, "food and dining", days_ago=1)
    # Localized label (sessions started from older surfaces or translated UI).
    _add_session(test_db_session, regular_user.id, "Emociones y Sentimientos", days_ago=2)
    test_db_session.commit()

    pool = _PoolService().get_topic_pool(regular_user.id, db=test_db_session)

    by_key = {entry["key"]: entry for entry in pool["common"]}
    assert by_key["food"]["practiced"] is True
    assert by_key["food"]["last_used_at"] is not None
    assert by_key["emotions"]["practiced"] is True
    assert by_key["general"]["practiced"] is False


def test_topic_pool_respects_coverage_window(test_db_session, regular_user):
    _add_session(
        test_db_session,
        regular_user.id,
        "shopping",
        days_ago=TOPIC_COVERAGE_WINDOW_DAYS + 1,
    )
    test_db_session.commit()

    by_key = {
        entry["key"]: entry
        for entry in _PoolService().get_topic_pool(
            regular_user.id, db=test_db_session
        )["common"]
    }
    # Practiced recently within the window; older sessions only set last_used_at.
    assert by_key["shopping"]["practiced"] is False
    assert by_key["shopping"]["last_used_at"] is not None


def test_topic_pool_lists_custom_topics_in_recent_and_skips_common(
    test_db_session, regular_user
):
    _add_session(test_db_session, regular_user.id, "El espacio", days_ago=3, purpose="Viaje al espacio")
    _add_session(test_db_session, regular_user.id, "El espacio", days_ago=1)
    _add_session(test_db_session, regular_user.id, "food and dining", days_ago=2)
    test_db_session.commit()

    pool = _PoolService().get_topic_pool(regular_user.id, db=test_db_session)

    assert [entry["topic"] for entry in pool["recent"]] == ["El espacio"]
    assert pool["recent"][0]["count"] == 2
    assert pool["recent"][0]["purpose"] == "Viaje al espacio"


def test_topic_pool_hides_recent_when_custom_topics_blocked(
    test_db_session, regular_user
):
    from src.aac_app.models import GuardianProfile

    profile = GuardianProfile(
        user_id=regular_user.id,
        created_by=regular_user.id,
        safety_constraints={"block_custom_topics": True},
    )
    test_db_session.add(profile)
    _add_session(test_db_session, regular_user.id, "El espacio", days_ago=1)
    test_db_session.commit()

    pool = _PoolService().get_topic_pool(regular_user.id, db=test_db_session)

    assert pool["recent"] == []
    assert len(pool["common"]) == len(COMMON_TOPICS)


# ---------------------------------------------------------------------------
# Route-level permissions and error mapping
# ---------------------------------------------------------------------------

@pytest.fixture
def teacher_user(test_db_session):
    user = User(
        username="topics_teacher",
        display_name="Topics Teacher",
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
        username="topics_student",
        display_name="Topics Student",
        user_type="student",
        password_hash=get_password_hash("StudentPass123"),
        is_active=True,
    )
    test_db_session.add(user)
    test_db_session.commit()
    test_db_session.refresh(user)
    return user


def _mock_service():
    service = MagicMock()
    service.get_topic_pool = MagicMock(
        return_value={
            "success": True,
            "common": [{"key": "general", "practiced": False, "last_used_at": None}],
            "recent": [],
        }
    )
    return service


@pytest.fixture
def mock_learning_service():
    return _mock_service()


@pytest.fixture(autouse=True)
def _override_learning_service(mock_learning_service):
    app.dependency_overrides[get_learning_service] = lambda: mock_learning_service
    yield
    app.dependency_overrides.pop(get_learning_service, None)


def test_topics_returns_own_pool_for_student(student_user):
    response = client.get(
        f"/api/learning/topics?user_id={student_user.id}",
        headers=create_test_headers(student_user.id, student_user.username, "student"),
    )
    assert response.status_code == 200
    assert response.json()["common"][0]["key"] == "general"


def test_topics_forbidden_for_unrelated_standard_user(regular_user, student_user, user_token):
    response = client.get(
        f"/api/learning/topics?user_id={student_user.id}",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert response.status_code == 403


def test_topics_teacher_scoped_to_roster(teacher_user, student_user, test_db_session):
    response = client.get(
        f"/api/learning/topics?user_id={student_user.id}",
        headers=create_test_headers(teacher_user.id, teacher_user.username, "teacher"),
    )
    assert response.status_code == 403

    test_db_session.add(
        StudentTeacher(teacher_id=teacher_user.id, student_id=student_user.id)
    )
    test_db_session.commit()

    response = client.get(
        f"/api/learning/topics?user_id={student_user.id}",
        headers=create_test_headers(teacher_user.id, teacher_user.username, "teacher"),
    )
    assert response.status_code == 200


def test_topics_admin_can_read_any_student(admin_user, admin_token, student_user):
    response = client.get(
        f"/api/learning/topics?user_id={student_user.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200


def test_topics_service_failure_maps_to_400(
    student_user, mock_learning_service
):
    mock_learning_service.get_topic_pool.return_value = {
        "success": False,
        "error": "boom",
    }
    response = client.get(
        f"/api/learning/topics?user_id={student_user.id}",
        headers=create_test_headers(student_user.id, student_user.username, "student"),
    )
    assert response.status_code == 400
    assert "boom" in response.json()["detail"]
