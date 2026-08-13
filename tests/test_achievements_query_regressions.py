import pytest
from fastapi.testclient import TestClient

from src.aac_app.models import Achievement, StudentTeacher, User, UserAchievement
from src.aac_app.services.achievement_system import AchievementSystem
from src.api.main import app
from tests.test_utils_auth import create_test_headers


@pytest.fixture
def achievements_client(setup_test_db, test_db_session):
    yield TestClient(app)


def _create_student(test_db_session, *, username="achievement_student") -> User:
    student = User(
        username=username,
        display_name="Achievement Student",
        user_type="student",
        password_hash="test-hash",
    )
    test_db_session.add(student)
    test_db_session.commit()
    test_db_session.refresh(student)
    return student


def _create_teacher(test_db_session) -> User:
    teacher = User(
        username="achievement_teacher",
        display_name="Achievement Teacher",
        user_type="teacher",
        password_hash="test-hash",
    )
    test_db_session.add(teacher)
    test_db_session.commit()
    test_db_session.refresh(teacher)
    return teacher


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


def test_teacher_cannot_target_unassigned_student_for_achievement(
    achievements_client, test_db_session
):
    teacher = _create_teacher(test_db_session)
    student = _create_student(test_db_session, username="unassigned_achievement_student")
    headers = create_test_headers(teacher.id, teacher.username, "teacher")

    response = achievements_client.post(
        "/api/achievements/",
        headers=headers,
        json={
            "name": "Restricted Target",
            "description": "Only the student's teacher may target it",
            "target_user_id": student.id,
        },
    )

    assert response.status_code == 403


def test_teacher_can_target_assigned_student_for_achievement(
    achievements_client, test_db_session
):
    teacher = _create_teacher(test_db_session)
    student = _create_student(test_db_session, username="assigned_achievement_student")
    test_db_session.add(StudentTeacher(teacher_id=teacher.id, student_id=student.id))
    test_db_session.commit()
    headers = create_test_headers(teacher.id, teacher.username, "teacher")

    response = achievements_client.post(
        "/api/achievements/",
        headers=headers,
        json={
            "name": "Assigned Target",
            "description": "The assigned teacher may target it",
            "target_user_id": student.id,
        },
    )

    assert response.status_code == 201
    assert response.json()["target_user_id"] == student.id


def test_teacher_cannot_award_unassigned_student(
    achievements_client, test_db_session
):
    teacher = _create_teacher(test_db_session)
    student = _create_student(test_db_session, username="unassigned_award_student")
    achievement = _seed_system_achievements(test_db_session)[0]
    headers = create_test_headers(teacher.id, teacher.username, "teacher")

    response = achievements_client.post(
        f"/api/achievements/{achievement.id}/award",
        headers=headers,
        json={"user_id": student.id},
    )

    assert response.status_code == 403


def test_teacher_without_roster_cannot_access_other_student_achievements(
    achievements_client, test_db_session
):
    teacher = _create_teacher(test_db_session)
    student = _create_student(test_db_session, username="empty_roster_view_student")
    headers = create_test_headers(teacher.id, teacher.username, "teacher")

    for method, path in (
        ("get", f"/api/achievements/user/{student.id}"),
        ("post", f"/api/achievements/user/{student.id}/check"),
        ("get", f"/api/achievements/user/{student.id}/points"),
    ):
        response = getattr(achievements_client, method)(path, headers=headers)
        assert response.status_code == 403, response.text


def test_teacher_can_access_assigned_student_achievements(
    achievements_client, test_db_session
):
    teacher = _create_teacher(test_db_session)
    student = _create_student(test_db_session, username="assigned_view_student")
    test_db_session.add(StudentTeacher(teacher_id=teacher.id, student_id=student.id))
    test_db_session.commit()
    headers = create_test_headers(teacher.id, teacher.username, "teacher")

    for method, path in (
        ("get", f"/api/achievements/user/{student.id}"),
        ("post", f"/api/achievements/user/{student.id}/check"),
        ("get", f"/api/achievements/user/{student.id}/points"),
    ):
        response = getattr(achievements_client, method)(path, headers=headers)
        assert response.status_code == 200, response.text


def test_teacher_cannot_access_unassigned_student_achievements(
    achievements_client, test_db_session
):
    teacher = _create_teacher(test_db_session)
    assigned_student = _create_student(
        test_db_session, username="assigned_scope_student"
    )
    target_student = _create_student(test_db_session, username="unassigned_view_student")
    test_db_session.add(
        StudentTeacher(teacher_id=teacher.id, student_id=assigned_student.id)
    )
    test_db_session.commit()
    headers = create_test_headers(teacher.id, teacher.username, "teacher")

    for method, path in (
        ("get", f"/api/achievements/user/{target_student.id}"),
        ("post", f"/api/achievements/user/{target_student.id}/check"),
        ("get", f"/api/achievements/user/{target_student.id}/points"),
    ):
        response = getattr(achievements_client, method)(path, headers=headers)
        assert response.status_code == 403, response.text


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
