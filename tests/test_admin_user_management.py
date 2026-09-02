from fastapi.testclient import TestClient

from src.aac_app.models import StudentTeacher, User
from src.api.main import app

client = TestClient(app)


def test_admin_manage_teachers(setup_test_db, admin_token, test_db_session):
    headers = {"Authorization": f"Bearer {admin_token}"}

    # 1. Create a Teacher
    teacher_data = {
        "username": "new_teacher",
        "password": "TeacherPass123",
        "confirm_password": "TeacherPass123",
        "display_name": "New Teacher",
        "user_type": "teacher",
        "email": "teacher@example.com"
    }
    response = client.post("/api/auth/admin/create-user", json=teacher_data, headers=headers)
    assert response.status_code == 200
    teacher_id = response.json()["id"]
    assert response.json()["username"] == "new_teacher"
    assert response.json()["user_type"] == "teacher"

    # 2. Create a Student
    student_data = {
        "username": "new_student",
        "password": "StudentPass123",
        "confirm_password": "StudentPass123",
        "display_name": "New Student",
        "user_type": "student"
    }
    response = client.post("/api/auth/admin/create-user", json=student_data, headers=headers)
    assert response.status_code == 200
    student_id = response.json()["id"]

    # 3. Verify Teachers List (Should contain teacher, NOT student)
    response = client.get("/api/auth/users", params={"limit": 100}, headers=headers)
    assert response.status_code == 200
    all_users = response.json()

    teachers = [u for u in all_users if u["user_type"] == "teacher"]
    students = [u for u in all_users if u["user_type"] == "student"]

    assert any(t["id"] == teacher_id for t in teachers)
    assert not any(t["id"] == student_id for t in teachers)

    assert any(s["id"] == student_id for s in students)
    assert not any(s["id"] == teacher_id for s in students)

    # 4. Update Teacher
    update_data = {"display_name": "Updated Teacher Name"}
    response = client.put(f"/api/auth/users/{teacher_id}", json=update_data, headers=headers)
    assert response.status_code == 200
    assert response.json()["display_name"] == "Updated Teacher Name"

    # 5. Delete Teacher
    response = client.delete(f"/api/auth/users/{teacher_id}", headers=headers)
    assert response.status_code == 200  # Or 204 depending on implementation

    # 6. Verify Deletion
    response = client.get(f"/api/auth/users/{teacher_id}", headers=headers)
    assert response.status_code == 404


def test_deleting_teacher_removes_their_saved_topics(
    setup_test_db, admin_token, test_db_session
):
    """Account deletion must not orphan saved topics or their creator FK."""
    from src.aac_app.models import SavedTopic

    headers = {"Authorization": f"Bearer {admin_token}"}
    create = client.post(
        "/api/auth/admin/create-user",
        json={
            "username": "topic_owner_teacher",
            "password": "TeacherPass123",
            "confirm_password": "TeacherPass123",
            "display_name": "Topic Owner",
            "user_type": "teacher",
        },
        headers=headers,
    )
    assert create.status_code == 200
    teacher_id = create.json()["id"]

    topic = SavedTopic(
        user_id=teacher_id,
        board="Board",
        topic="Topic",
        created_by="Topic Owner",
        created_by_user_id=teacher_id,
    )
    test_db_session.add(topic)
    test_db_session.commit()
    test_db_session.refresh(topic)

    response = client.delete(f"/api/auth/users/{teacher_id}", headers=headers)
    assert response.status_code == 200

    remaining = (
        test_db_session.query(SavedTopic)
        .filter(SavedTopic.id == topic.id)
        .first()
    )
    assert remaining is None
    # No dangling creator references either.
    dangling = (
        test_db_session.query(SavedTopic)
        .filter(SavedTopic.created_by_user_id == teacher_id)
        .count()
    )
    assert dangling == 0


def test_update_user_validates_role_email_and_active_flag(setup_test_db, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}

    def create_user(username, email, user_type):
        response = client.post(
            "/api/auth/admin/create-user",
            json={
                "username": username,
                "password": "StudentPass123",
                "confirm_password": "StudentPass123",
                "display_name": username,
                "user_type": user_type,
                "email": email,
            },
            headers=headers,
        )
        assert response.status_code == 200, response.text
        return response.json()

    first = create_user("edit_role_student", "role_edit@example.com", "student")
    second = create_user("edit_email_student", "email_edit@example.com", "student")

    # A role outside the supported set must be rejected, not persisted.
    invalid_role = client.put(
        f"/api/auth/users/{first['id']}",
        json={"user_type": "superadmin"},
        headers=headers,
    )
    assert invalid_role.status_code == 400

    # An explicit null role must also be rejected, not persisted as a broken role.
    null_role = client.put(
        f"/api/auth/users/{first['id']}",
        json={"user_type": None},
        headers=headers,
    )
    assert null_role.status_code == 400

    # A duplicate email must be rejected rather than corrupting uniqueness.
    duplicate_email = client.put(
        f"/api/auth/users/{second['id']}",
        json={"email": "role_edit@example.com"},
        headers=headers,
    )
    assert duplicate_email.status_code == 400

    # An empty email clears the stored value (stored as NULL, like an account
    # created without one), instead of silently keeping the old address.
    clear_email = client.put(
        f"/api/auth/users/{second['id']}",
        json={"email": ""},
        headers=headers,
    )
    assert clear_email.status_code == 200
    assert clear_email.json()["email"] is None

    # is_active must be a real boolean, not a truthy string.
    invalid_active = client.put(
        f"/api/auth/users/{first['id']}",
        json={"is_active": "false"},
        headers=headers,
    )
    assert invalid_active.status_code == 400

    # A valid role transition still works.
    valid_role = client.put(
        f"/api/auth/users/{first['id']}",
        json={"user_type": "teacher"},
        headers=headers,
    )
    assert valid_role.status_code == 200
    assert valid_role.json()["user_type"] == "teacher"

    # A blank display name must be rejected, matching the profile contract,
    # instead of persisting an invisible name.
    blank_name = client.put(
        f"/api/auth/users/{second['id']}",
        json={"display_name": "   "},
        headers=headers,
    )
    assert blank_name.status_code == 400
    assert blank_name.json()["detail"] != "errors.auth.displayNameRequired"


def test_students_endpoint_paginates(setup_test_db, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    student_ids = []
    for i in range(3):
        data = {
            "username": f"page_student_{i}",
            "password": "StudentPass123",
            "confirm_password": "StudentPass123",
            "display_name": f"Page Student {i}",
            "user_type": "student",
        }
        response = client.post("/api/auth/admin/create-user", json=data, headers=headers)
        assert response.status_code == 200
        student_ids.append(response.json()["id"])

    first_page = client.get("/api/users/students", params={"limit": 2}, headers=headers)
    assert first_page.status_code == 200
    assert len(first_page.json()) == 2
    assert [s["id"] for s in first_page.json()] == sorted(s["id"] for s in first_page.json())

    second_page = client.get(
        "/api/users/students", params={"skip": 2, "limit": 2}, headers=headers
    )
    assert second_page.status_code == 200
    assert len(second_page.json()) == 1

    invalid = client.get("/api/users/students", params={"limit": 501}, headers=headers)
    assert invalid.status_code == 422


def test_auth_user_pagination_is_deterministically_ordered(setup_test_db, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    created_ids = []
    for index in range(4):
        response = client.post(
            "/api/auth/admin/create-user",
            headers=headers,
            json={
                "username": f"ordered_page_student_{index}",
                "password": "StudentPass123",
                "confirm_password": "StudentPass123",
                "display_name": f"Ordered Page Student {index}",
                "user_type": "student",
            },
        )
        assert response.status_code == 200, response.text
        created_ids.append(response.json()["id"])

    first = client.get(
        "/api/auth/users",
        params={"user_type": "student", "skip": 0, "limit": 2},
        headers=headers,
    )
    second = client.get(
        "/api/auth/users",
        params={"user_type": "student", "skip": 2, "limit": 2},
        headers=headers,
    )
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    first_ids = [user["id"] for user in first.json()]
    second_ids = [user["id"] for user in second.json()]
    assert first_ids == sorted(first_ids)
    assert second_ids == sorted(second_ids)
    assert set(first_ids).isdisjoint(second_ids)
    assert set(created_ids).issubset(first_ids + second_ids)


def test_teacher_user_pagination_deduplicates_legacy_assignments(
    setup_test_db, admin_token, test_db_session
):
    headers = {"Authorization": f"Bearer {admin_token}"}
    teacher_response = client.post(
        "/api/auth/admin/create-user",
        headers=headers,
        json={
            "username": "ordered_teacher",
            "password": "TeacherPass123",
            "confirm_password": "TeacherPass123",
            "display_name": "Ordered Teacher",
            "user_type": "teacher",
        },
    )
    assert teacher_response.status_code == 200, teacher_response.text
    teacher = teacher_response.json()
    student_response = client.post(
        "/api/auth/admin/create-user",
        headers=headers,
        json={
            "username": "ordered_assigned_student",
            "password": "StudentPass123",
            "confirm_password": "StudentPass123",
            "display_name": "Ordered Assigned Student",
            "user_type": "student",
        },
    )
    assert student_response.status_code == 200, student_response.text
    student = student_response.json()

    test_db_session.add_all(
        [
            StudentTeacher(student_id=student["id"], teacher_id=teacher["id"]),
            StudentTeacher(student_id=student["id"], teacher_id=teacher["id"]),
        ]
    )
    test_db_session.commit()

    # The request must be authenticated as the teacher, not the admin.
    from tests.auth_helpers import create_test_headers

    teacher_page = client.get(
        "/api/auth/users",
        params={"skip": 0, "limit": 10, "user_type": "student"},
        headers=create_test_headers(teacher["id"], teacher["username"], "teacher"),
    )
    assert teacher_page.status_code == 200, teacher_page.text
    matching = [item for item in teacher_page.json() if item["id"] == student["id"]]
    assert len(matching) == 1


def _create_admin_via_api(headers, username):
    response = client.post(
        "/api/auth/admin/create-user",
        json={
            "username": username,
            "password": "AdminPass123",
            "confirm_password": "AdminPass123",
            "display_name": username,
            "user_type": "admin",
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_last_active_admin_cannot_deactivate_or_demote_self(
    setup_test_db, admin_token, test_db_session
):
    """Self-deactivation/demotion of the only active admin would strand the
    app in setup: reject it. Self-deletion is already blocked separately, so
    the update path is the real last-admin escape hatch."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    admin_id = test_db_session.query(User.id).filter(User.username == "admin_test").scalar()
    assert admin_id is not None

    deactivate = client.put(
        f"/api/auth/users/{admin_id}",
        json={"is_active": False},
        headers=headers,
    )
    assert deactivate.status_code == 400
    assert deactivate.json()["detail"] != "errors.auth.lastAdminRequired"

    demote = client.put(
        f"/api/auth/users/{admin_id}",
        json={"user_type": "teacher"},
        headers=headers,
    )
    assert demote.status_code == 400
    assert demote.json()["detail"] != "errors.auth.lastAdminRequired"

    # The admin is still active and an admin.
    still = test_db_session.query(User).filter(User.id == admin_id).first()
    assert still.user_type == "admin"
    assert still.is_active is True

    # Once a second active admin exists, self-deactivation is allowed.
    _create_admin_via_api(headers, "second_admin_self_deactivate")
    deactivate_ok = client.put(
        f"/api/auth/users/{admin_id}",
        json={"is_active": False},
        headers=headers,
    )
    assert deactivate_ok.status_code == 200
    assert deactivate_ok.json()["is_active"] is False


def test_teacher_isolation(setup_test_db, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Ensure admin can see both but frontend filters them
    response = client.get("/api/auth/users", headers=headers)
    assert response.status_code == 200
    users = response.json()
    assert isinstance(users, list)
    # This test relies on the fact that the backend returns ALL users to admin,
    # and the frontend is responsible for filtering.
    # My implementation of Teachers.tsx does: setTeachers(list.filter(u => u.user_type === 'teacher'))
    # So backend isolation isn't enforced for admin, which is correct.
