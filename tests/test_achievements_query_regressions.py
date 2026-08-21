import pytest
from fastapi.testclient import TestClient

from src.aac_app.models import (
    Achievement,
    LearningSession,
    StudentTeacher,
    User,
    UserAchievement,
)
from src.aac_app.services.achievement_system import AchievementSystem
from src.api.main import app
from tests.auth_helpers import create_test_headers


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


def test_create_achievement_accepts_empty_description(
    achievements_client, admin_user
):
    """The editor allows leaving the description blank, so the API must accept
    an empty string instead of rejecting it with a validation error."""
    headers = create_test_headers(admin_user.id, admin_user.username, "admin")
    response = achievements_client.post(
        "/api/achievements/",
        headers=headers,
        json={
            "name": "No Description",
            "description": "",
            "category": "custom",
            "points": 10,
        },
    )

    assert response.status_code == 201
    assert response.json()["description"] == ""


def test_update_achievement_accepts_cleared_description(
    achievements_client, admin_user
):
    """Clearing the description in the editor must not fail validation."""
    headers = create_test_headers(admin_user.id, admin_user.username, "admin")
    created = achievements_client.post(
        "/api/achievements/",
        headers=headers,
        json={
            "name": "Will Clear Description",
            "description": "Some text",
        },
    )
    assert created.status_code == 201

    response = achievements_client.put(
        f"/api/achievements/{created.json()['id']}",
        headers=headers,
        json={"description": ""},
    )

    assert response.status_code == 200
    assert response.json()["description"] == ""


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


def test_create_achievement_rejects_incomplete_automatic_criteria(
    achievements_client, admin_user
):
    """Automatic achievements cannot silently become manual when one field is missing."""
    headers = create_test_headers(admin_user.id, admin_user.username, "admin")
    response = achievements_client.post(
        "/api/achievements/",
        headers=headers,
        json={
            "name": "Incomplete Criteria",
            "description": "Missing target value",
            "criteria_type": "sessions_completed",
        },
    )

    assert response.status_code == 400


def test_create_achievement_rejects_negative_values(
    achievements_client, admin_user
):
    """Points and automatic thresholds cannot be negative."""
    headers = create_test_headers(admin_user.id, admin_user.username, "admin")
    response = achievements_client.post(
        "/api/achievements/",
        headers=headers,
        json={
            "name": "Negative Criteria",
            "description": "Invalid threshold",
            "points": -1,
            "criteria_type": "sessions_completed",
            "criteria_value": 0,
        },
    )

    assert response.status_code == 422


def test_update_achievement_can_clear_automatic_criteria(
    achievements_client, admin_user
):
    """Explicit null criteria values switch a custom achievement to manual."""
    headers = create_test_headers(admin_user.id, admin_user.username, "admin")
    created = achievements_client.post(
        "/api/achievements/",
        headers=headers,
        json={
            "name": "Switchable Badge",
            "description": "Can become manual",
            "criteria_type": "sessions_completed",
            "criteria_value": 1,
        },
    )
    assert created.status_code == 201

    response = achievements_client.put(
        f"/api/achievements/{created.json()['id']}",
        headers=headers,
        json={"criteria_type": None, "criteria_value": None},
    )

    assert response.status_code == 200
    assert response.json()["is_manual"] is True
    assert response.json()["criteria_type"] is None
    assert response.json()["criteria_value"] is None


def test_update_achievement_can_change_target_student(
    achievements_client, test_db_session, admin_user
):
    """Admins can retarget a custom achievement through the update API."""
    student = _create_student(test_db_session, username="retargeted_achievement_student")
    headers = create_test_headers(admin_user.id, admin_user.username, "admin")
    created = achievements_client.post(
        "/api/achievements/",
        headers=headers,
        json={
            "name": "Retargetable Badge",
            "description": "Can be assigned to a student later",
        },
    )
    assert created.status_code == 201

    response = achievements_client.put(
        f"/api/achievements/{created.json()['id']}",
        headers=headers,
        json={"target_user_id": student.id},
    )

    assert response.status_code == 200
    assert response.json()["target_user_id"] == student.id


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


def test_custom_automatic_achievement_is_awarded_when_criteria_met(
    setup_test_db, test_db_session
):
    teacher = _create_teacher(test_db_session)
    student = _create_student(test_db_session, username="custom_auto_student")
    test_db_session.add(
        Achievement(
            name="Custom Auto Badge",
            description="Awarded after one completed session",
            category="custom",
            criteria_type="sessions_completed",
            criteria_value=1,
            points=15,
            icon="⭐",
            created_by=teacher.id,
            is_manual=False,
            is_active=True,
        )
    )
    test_db_session.add(
        LearningSession(
            user_id=student.id,
            topic_name="Practice",
            status="completed",
            questions_answered=1,
            correct_answers=1,
            comprehension_score=1.0,
        )
    )
    test_db_session.commit()

    AchievementSystem().check_achievements(student.id, db=test_db_session)

    earned = (
        test_db_session.query(UserAchievement)
        .join(Achievement)
        .filter(
            UserAchievement.user_id == student.id,
            Achievement.name == "Custom Auto Badge",
        )
        .count()
    )
    assert earned == 1


def test_custom_automatic_achievement_targeting_respects_student(
    setup_test_db, test_db_session
):
    teacher = _create_teacher(test_db_session)
    target_student = _create_student(test_db_session, username="custom_target_student")
    other_student = _create_student(test_db_session, username="custom_other_student")
    test_db_session.add(
        Achievement(
            name="Targeted Auto Badge",
            description="Only for the targeted student",
            category="custom",
            criteria_type="sessions_completed",
            criteria_value=1,
            points=15,
            icon="⭐",
            created_by=teacher.id,
            target_user_id=target_student.id,
            is_manual=False,
            is_active=True,
        )
    )
    for student in (target_student, other_student):
        test_db_session.add(
            LearningSession(
                user_id=student.id,
                topic_name="Practice",
                status="completed",
                questions_answered=1,
                correct_answers=1,
                comprehension_score=1.0,
            )
        )
    test_db_session.commit()

    for student in (target_student, other_student):
        AchievementSystem().check_achievements(student.id, db=test_db_session)

    def _earned(user_id: int) -> int:
        return (
            test_db_session.query(UserAchievement)
            .join(Achievement)
            .filter(
                UserAchievement.user_id == user_id,
                Achievement.name == "Targeted Auto Badge",
            )
            .count()
        )

    assert _earned(target_student.id) == 1
    assert _earned(other_student.id) == 0
