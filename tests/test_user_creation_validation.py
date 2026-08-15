from fastapi.testclient import TestClient

from src.aac_app.models import (
    Achievement,
    AppSettings,
    AuditLog,
    BoardAssignment,
    BoardSymbol,
    CollaborationSession,
    CommunicationBoard,
    GuardianProfile,
    GuardianProfileHistory,
    LearningMode,
    LearningPlan,
    LearningSession,
    LearningTask,
    Notification,
    StudentTeacher,
    Symbol,
    SymbolUsageLog,
    User,
    UserAchievement,
    UserProgress,
    UserSettings,
)
from src.aac_app.services.auth_service import get_password_hash
from src.api.main import app
from tests.test_utils_auth import create_test_headers

client = TestClient(app)


def test_admin_delete_user_cleans_owned_data_and_relationships(
    setup_test_db,
    test_db_session,
    admin_user,
    admin_token,
):
    student = User(
        username="student_with_data",
        display_name="Student With Data",
        user_type="student",
        password_hash="unused",
        is_active=True,
    )
    teacher = User(
        username="teacher_for_delete",
        display_name="Teacher For Delete",
        user_type="teacher",
        password_hash="unused",
        is_active=True,
    )
    symbol = Symbol(label="Delete symbol", category="general")
    test_db_session.add_all([student, teacher, symbol])
    test_db_session.flush()
    board = CommunicationBoard(user_id=student.id, name="Student board")
    test_db_session.add(board)
    test_db_session.flush()
    test_db_session.add_all([
        BoardSymbol(board_id=board.id, symbol_id=symbol.id),
        BoardAssignment(board_id=board.id, student_id=student.id, assigned_by=admin_user.id),
        StudentTeacher(student_id=student.id, teacher_id=teacher.id),
        UserSettings(user_id=student.id),
    ])
    test_db_session.commit()
    student_id = student.id
    board_id = board.id

    response = client.delete(
        f"/api/auth/users/{student_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200, response.text
    # The API request uses a separate session; discard this session's stale
    # identity-map entry before checking the committed database state.
    test_db_session.expire_all()
    assert test_db_session.get(User, student_id) is None
    assert test_db_session.query(CommunicationBoard).filter_by(id=board_id).count() == 0
    assert test_db_session.query(BoardSymbol).filter_by(board_id=board_id).count() == 0
    assert test_db_session.query(BoardAssignment).filter_by(board_id=board_id).count() == 0
    assert test_db_session.query(StudentTeacher).filter_by(student_id=student_id).count() == 0
    assert test_db_session.query(UserSettings).filter_by(user_id=student_id).count() == 0


def test_admin_delete_user_cleans_all_user_foreign_keys(
    setup_test_db,
    test_db_session,
    admin_user,
    admin_token,
):
    student = User(
        username="student_with_related_data",
        display_name="Student With Related Data",
        user_type="student",
        password_hash="unused",
        is_active=True,
    )
    other_student = User(
        username="other_student_with_related_data",
        display_name="Other Student",
        user_type="student",
        password_hash="unused",
        is_active=True,
    )
    symbol = Symbol(label="Related symbol", category="general")
    test_db_session.add_all([student, other_student, symbol])
    test_db_session.flush()

    owned_board = CommunicationBoard(user_id=student.id, name="Owned board")
    other_board = CommunicationBoard(user_id=other_student.id, name="Other board")
    test_db_session.add_all([owned_board, other_board])
    test_db_session.flush()
    test_db_session.add_all([
        BoardSymbol(board_id=owned_board.id, symbol_id=symbol.id),
        BoardSymbol(
            board_id=other_board.id,
            symbol_id=symbol.id,
            linked_board_id=owned_board.id,
        ),
        BoardAssignment(
            board_id=owned_board.id,
            student_id=other_student.id,
            assigned_by=student.id,
        ),
        StudentTeacher(student_id=student.id, teacher_id=admin_user.id),
    ])

    learning_session = LearningSession(user_id=student.id, topic_name="Related topic")
    learning_plan = LearningPlan(user_id=student.id, name="Related plan")
    test_db_session.add_all([learning_session, learning_plan])
    test_db_session.flush()
    test_db_session.add_all([
        SymbolUsageLog(
            user_id=student.id,
            session_id=learning_session.id,
            symbol_id=symbol.id,
            symbol_label=symbol.label,
            position_in_utterance=0,
            utterance_length=1,
        ),
        LearningTask(plan_id=learning_plan.id, name="Related task"),
        UserProgress(
            user_id=student.id,
            metric_type="accuracy",
            metric_value=1.0,
        ),
        Notification(
            user_id=student.id,
            title="Related notification",
            message="Temporary QA notification",
        ),
        UserSettings(user_id=student.id),
    ])

    mode = LearningMode(
        name="Related mode",
        key="related-mode",
        prompt_instruction="Use related mode",
        created_by=student.id,
    )
    achievement = Achievement(
        name="Related achievement",
        created_by=student.id,
        target_user_id=student.id,
    )
    shared_achievement = Achievement(
        name="Shared achievement",
        created_by=admin_user.id,
        target_user_id=student.id,
    )
    test_db_session.add_all([mode, achievement, shared_achievement])
    test_db_session.flush()
    test_db_session.add(UserAchievement(user_id=student.id, achievement_id=achievement.id))

    target_profile = GuardianProfile(
        user_id=student.id,
        created_by=admin_user.id,
    )
    other_profile = GuardianProfile(
        user_id=other_student.id,
        created_by=student.id,
        updated_by=student.id,
    )
    test_db_session.add_all([target_profile, other_profile])
    test_db_session.flush()
    test_db_session.add_all([
        GuardianProfileHistory(
            profile_id=target_profile.id,
            field_name="age",
            changed_by=student.id,
        ),
        GuardianProfileHistory(
            profile_id=other_profile.id,
            field_name="age",
            changed_by=student.id,
        ),
        AppSettings(setting_key="related-setting", updated_by=student.id),
        CollaborationSession(
            session_name="Related collaboration",
            host_user_id=student.id,
            session_code="related-qa",
        ),
    ])
    test_db_session.commit()

    student_id = student.id
    owned_board_id = owned_board.id
    other_board_id = other_board.id
    other_profile_id = other_profile.id
    response = client.delete(
        f"/api/auth/users/{student_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200, response.text
    test_db_session.expire_all()
    assert test_db_session.get(User, student_id) is None
    deletion_audit = test_db_session.query(AuditLog).filter_by(
        event_type="admin_delete_user",
        user_id=admin_user.id,
    ).one()
    assert f"id={student_id}" in deletion_audit.description
    assert test_db_session.query(CommunicationBoard).filter_by(id=owned_board_id).count() == 0
    assert test_db_session.query(LearningSession).filter_by(user_id=student_id).count() == 0
    assert test_db_session.query(LearningPlan).filter_by(user_id=student_id).count() == 0
    assert test_db_session.query(SymbolUsageLog).filter_by(user_id=student_id).count() == 0
    assert test_db_session.query(UserProgress).filter_by(user_id=student_id).count() == 0
    assert test_db_session.query(Notification).filter_by(user_id=student_id).count() == 0
    assert test_db_session.query(UserSettings).filter_by(user_id=student_id).count() == 0
    assert test_db_session.query(UserAchievement).filter_by(user_id=student_id).count() == 0
    assert test_db_session.query(GuardianProfile).filter_by(user_id=student_id).count() == 0
    assert test_db_session.query(CollaborationSession).filter_by(host_user_id=student_id).count() == 0
    assert test_db_session.query(BoardAssignment).filter_by(assigned_by=student_id).count() == 0
    assert test_db_session.query(StudentTeacher).filter(
        (StudentTeacher.student_id == student_id)
        | (StudentTeacher.teacher_id == student_id)
    ).count() == 0

    remaining_symbol = test_db_session.query(BoardSymbol).filter_by(
        board_id=other_board_id
    ).one()
    assert remaining_symbol.linked_board_id is None
    remaining_mode = test_db_session.query(LearningMode).filter_by(key="related-mode").one()
    assert remaining_mode.created_by is None
    remaining_achievement = test_db_session.query(Achievement).filter_by(
        name="Related achievement"
    ).one()
    assert remaining_achievement.created_by is None
    assert remaining_achievement.target_user_id is None
    remaining_shared_achievement = test_db_session.query(Achievement).filter_by(
        name="Shared achievement"
    ).one()
    assert remaining_shared_achievement.created_by == admin_user.id
    assert remaining_shared_achievement.target_user_id is None
    remaining_profile = test_db_session.get(GuardianProfile, other_profile_id)
    assert remaining_profile.created_by == admin_user.id
    assert remaining_profile.updated_by is None
    remaining_history = test_db_session.query(GuardianProfileHistory).filter_by(
        profile_id=other_profile_id
    ).one()
    assert remaining_history.changed_by == admin_user.id
    assert test_db_session.query(AppSettings).filter_by(
        setting_key="related-setting", updated_by=student_id
    ).count() == 0


def test_teacher_student_creation_assigns_to_authenticated_teacher(
    setup_test_db,
    test_db_session,
    test_password,
):
    teacher = User(
        username="teacher_creates_student",
        display_name="Teacher Creates Student",
        user_type="teacher",
        password_hash=get_password_hash(test_password),
        is_active=True,
    )
    test_db_session.add(teacher)
    test_db_session.commit()
    test_db_session.refresh(teacher)

    response = client.post(
        "/api/users/students",
        headers=create_test_headers(teacher.id, teacher.username, teacher.user_type),
        json={
            "username": "teacher_created_student",
            "display_name": "Teacher Created Student",
            "password": test_password,
            "user_type": "student",
        },
    )

    assert response.status_code == 200, response.text
    student_id = response.json()["id"]
    assignment = test_db_session.query(StudentTeacher).filter_by(
        student_id=student_id,
        teacher_id=teacher.id,
    ).first()
    assert assignment is not None


def test_teacher_student_creation_rejects_weak_password_atomically(
    setup_test_db,
    test_db_session,
):
    teacher = User(
        username="teacher_rejects_weak_password",
        display_name="Teacher Rejects Weak Password",
        user_type="teacher",
        password_hash=get_password_hash("TeacherPass123"),
        is_active=True,
    )
    test_db_session.add(teacher)
    test_db_session.commit()
    test_db_session.refresh(teacher)

    response = client.post(
        "/api/users/students",
        headers=create_test_headers(teacher.id, teacher.username, teacher.user_type),
        json={
            "username": "weak_teacher_student",
            "display_name": "Weak Password Student",
            "password": "weakpass",
            "user_type": "student",
        },
    )

    assert response.status_code == 400
    assert test_db_session.query(User).filter(
        User.username == "weak_teacher_student"
    ).first() is None


def test_admin_student_creation_rejects_non_teacher_assignment(
    setup_test_db,
    test_db_session,
    admin_user,
    admin_token,
    test_password,
):
    non_teacher = User(
        username="assignment_target_student",
        display_name="Assignment Target Student",
        user_type="student",
        password_hash="test-hash",
        is_active=True,
    )
    test_db_session.add(non_teacher)
    test_db_session.commit()

    response = client.post(
        "/api/users/students",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "username": "created_student_invalid_assignment",
            "display_name": "Created Student",
            "user_type": "teacher",
            "password": test_password,
            "created_by_teacher_id": non_teacher.id,
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Teacher not found"
    assert (
        test_db_session.query(User)
        .filter(User.username == "created_student_invalid_assignment")
        .first()
        is None
    )


def test_admin_student_creation_rejects_inactive_teacher_assignment(
    setup_test_db,
    test_db_session,
    admin_token,
    test_password,
):
    inactive_teacher = User(
        username="inactive_assignment_teacher",
        display_name="Inactive Assignment Teacher",
        user_type="teacher",
        password_hash="test-hash",
        is_active=False,
    )
    test_db_session.add(inactive_teacher)
    test_db_session.commit()

    response = client.post(
        "/api/users/students",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "username": "created_student_inactive_assignment",
            "display_name": "Created Student",
            "user_type": "student",
            "password": test_password,
            "created_by_teacher_id": inactive_teacher.id,
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Teacher not found"
    assert (
        test_db_session.query(User)
        .filter(User.username == "created_student_inactive_assignment")
        .first()
        is None
    )


def test_student_creation_assigns_to_active_teacher(
    setup_test_db,
    test_db_session,
    admin_user,
    admin_token,
    test_password,
):
    teacher = User(
        username="active_assignment_teacher",
        display_name="Active Assignment Teacher",
        user_type="teacher",
        password_hash="test-hash",
        is_active=True,
    )
    test_db_session.add(teacher)
    test_db_session.commit()

    response = client.post(
        "/api/users/students",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "username": "created_student_valid_assignment",
            "display_name": "Created Student",
            "user_type": "teacher",
            "password": test_password,
            "created_by_teacher_id": teacher.id,
        },
    )

    assert response.status_code == 200
    created_id = response.json()["id"]
    assignment = (
        test_db_session.query(StudentTeacher)
        .filter_by(student_id=created_id, teacher_id=teacher.id)
        .one()
    )
    assert assignment.student_id == created_id
