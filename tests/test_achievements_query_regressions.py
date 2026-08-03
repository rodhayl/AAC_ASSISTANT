from contextlib import contextmanager
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.aac_app.models.database import Achievement, User, UserAchievement
from src.aac_app.services.achievement_system import AchievementSystem
from src.api.main import app
from tests.test_utils_auth import create_test_headers


@pytest.fixture
def achievements_client(setup_test_db, test_db_session):
    @contextmanager
    def override_get_session():
        yield test_db_session

    with patch(
        "src.api.routers.achievements.get_session",
        side_effect=override_get_session,
    ):
        yield TestClient(app)


def _create_student(test_db_session) -> User:
    student = User(
        username="achievement_student",
        display_name="Achievement Student",
        user_type="student",
        password_hash="test-hash",
    )
    test_db_session.add(student)
    test_db_session.commit()
    test_db_session.refresh(student)
    return student


def _seed_system_achievements(test_db_session) -> list[Achievement]:
    achievements = [
        Achievement(
            name="First Steps",
            description="Complete your first learning session",
            category="beginner",
            criteria_type="sessions_completed",
            criteria_value=1,
            is_active=True,
        ),
        Achievement(
            name="Vocabulary Explorer",
            description="Learn 10 new words",
            category="vocabulary",
            criteria_type="vocabulary_size",
            criteria_value=10,
            is_active=True,
        ),
        Achievement(
            name="Quick Learner",
            description="Answer 5 questions correctly",
            category="performance",
            criteria_type="correct_answers",
            criteria_value=5,
            is_active=True,
        ),
    ]
    test_db_session.add_all(achievements)
    test_db_session.commit()
    return achievements


def test_fresh_student_sees_seeded_system_achievements(
    setup_test_db, test_db_session
):
    student = _create_student(test_db_session)
    _seed_system_achievements(test_db_session)

    result = AchievementSystem().get_user_achievements(student.id)

    names = {achievement["name"] for achievement in result}
    assert {
        "First Steps",
        "Vocabulary Explorer",
        "Quick Learner",
    } <= names


def test_award_then_list_has_earned_at_and_full_progress(
    achievements_client, test_db_session, admin_user
):
    student = _create_student(test_db_session)
    achievements = _seed_system_achievements(test_db_session)
    client = achievements_client
    headers = create_test_headers(admin_user.id, admin_user.username, "admin")

    award_response = client.post(
        f"/api/achievements/{achievements[0].id}/award",
        headers=headers,
        json={"user_id": student.id},
    )
    assert award_response.status_code == 200

    list_response = client.get(
        f"/api/achievements/user/{student.id}",
        headers=headers,
    )
    assert list_response.status_code == 200
    result = list_response.json()
    first_steps = next(item for item in result if item["name"] == "First Steps")

    assert first_steps["earned_at"] is not None
    assert first_steps["progress"] == 100.0


def test_create_achievement_with_zero_criteria_value_is_automatic(
    achievements_client, admin_user
):
    client = achievements_client
    response = client.post(
        "/api/achievements/",
        headers=create_test_headers(admin_user.id, admin_user.username, "admin"),
        json={
            "name": "Zero Threshold",
            "description": "An automatic achievement with a zero threshold",
            "category": "custom",
            "points": 10,
            "criteria_type": "sessions_completed",
            "criteria_value": 0,
        },
    )

    assert response.status_code == 201
    assert response.json()["is_manual"] is False


def test_update_achievement_with_zero_criteria_value_is_automatic(
    achievements_client, admin_user
):
    client = achievements_client
    headers = create_test_headers(admin_user.id, admin_user.username, "admin")
    created = client.post(
        "/api/achievements/",
        headers=headers,
        json={
            "name": "Nonzero Threshold",
            "description": "Will be updated",
            "category": "custom",
            "points": 10,
            "criteria_type": "sessions_completed",
            "criteria_value": 1,
        },
    )
    assert created.status_code == 201

    response = client.put(
        f"/api/achievements/{created.json()['id']}",
        headers=headers,
        json={"criteria_value": 0},
    )

    assert response.status_code == 200
    assert response.json()["is_manual"] is False


def test_leaderboard_returns_awarded_rows(setup_test_db, test_db_session):
    student = _create_student(test_db_session)
    achievements = _seed_system_achievements(test_db_session)
    test_db_session.add(
        UserAchievement(
            user_id=student.id,
            achievement_id=achievements[0].id,
        )
    )
    test_db_session.commit()

    result = AchievementSystem().get_leaderboard()

    assert result == [
        {
            "username": "achievement_student",
            "display_name": "Achievement Student",
            "points": 10,
            "achievement_count": 1,
        }
    ]
