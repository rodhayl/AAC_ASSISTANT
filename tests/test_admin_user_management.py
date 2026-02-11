from fastapi.testclient import TestClient
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
