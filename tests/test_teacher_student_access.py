from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.aac_app.models.database import StudentTeacher, User
from src.aac_app.services.auth_service import get_password_hash
from src.aac_app.utils.jwt_utils import create_access_token
from src.api.main import app

client = TestClient(app)


def get_auth_header(user):
    token = create_access_token(
        data={"sub": user.username, "user_id": user.id, "role": user.user_type}
    )
    return {"Authorization": f"Bearer {token}"}


def create_user(session, username, role, password="password123"):
    user = User(
        username=username,
        password_hash=get_password_hash(password),
        user_type=role,
        display_name=username,
        is_active=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_teacher_student_access(test_db_session: Session, setup_test_db):
    # Create users
    admin = create_user(test_db_session, "admin1", "admin")
    teacher = create_user(test_db_session, "teacher1", "teacher")
    student1 = create_user(test_db_session, "student1", "student")
    student2 = create_user(test_db_session, "student2", "student")

    # Assign student1 to teacher manually
    assignment = StudentTeacher(student_id=student1.id, teacher_id=teacher.id)
    test_db_session.add(assignment)
    test_db_session.commit()

    # 1. Teacher accessing assigned student (student1)
    response = client.get(
        f"/api/guardian-profiles/students/{student1.id}",
        headers=get_auth_header(teacher),
    )
    # Should return 404 if profile doesn't exist, but NOT 403
    assert response.status_code in [200, 404]
    assert response.status_code != 403

    # 2. Teacher accessing unassigned student (student2)
    response = client.get(
        f"/api/guardian-profiles/students/{student2.id}",
        headers=get_auth_header(teacher),
    )
    assert response.status_code == 403

    # 3. Admin accessing unassigned student (student2)
    response = client.get(
        f"/api/guardian-profiles/students/{student2.id}", headers=get_auth_header(admin)
    )
    assert response.status_code in [200, 404]

    # 4. Admin assigns student2 to teacher via API
    response = client.post(
        "/api/users/assign-student",
        json={"student_id": student2.id, "teacher_id": teacher.id},
        headers=get_auth_header(admin),
    )
    assert response.status_code == 201

    # 5. Teacher accessing student2 (now assigned)
    response = client.get(
        f"/api/guardian-profiles/students/{student2.id}",
        headers=get_auth_header(teacher),
    )
    assert response.status_code in [200, 404]

    # 6. Admin removes assignment
    response = client.delete(
        f"/api/users/assign-student/{student2.id}/{teacher.id}",
        headers=get_auth_header(admin),
    )
    assert response.status_code == 200

    # 7. Teacher accessing student2 (unassigned again)
    response = client.get(
        f"/api/guardian-profiles/students/{student2.id}",
        headers=get_auth_header(teacher),
    )
    assert response.status_code == 403


def test_list_students_filtering(test_db_session: Session, setup_test_db):
    # Create users
    admin = create_user(test_db_session, "admin2", "admin")
    teacher1 = create_user(test_db_session, "teacher2", "teacher")
    teacher2 = create_user(test_db_session, "teacher3", "teacher")
    student1 = create_user(test_db_session, "s1", "student")
    student2 = create_user(test_db_session, "s2", "student")
    student3 = create_user(test_db_session, "s3", "student")

    # Assign s1 -> t1, s2 -> t2, s3 -> unassigned
    test_db_session.add(StudentTeacher(student_id=student1.id, teacher_id=teacher1.id))
    test_db_session.add(StudentTeacher(student_id=student2.id, teacher_id=teacher2.id))
    test_db_session.commit()

    # Teacher 1 lists students
    response = client.get(
        "/api/guardian-profiles/students", headers=get_auth_header(teacher1)
    )
    assert response.status_code == 200
    data = response.json()
    ids = [s["id"] for s in data]
    assert student1.id in ids
    assert student2.id not in ids
    assert student3.id not in ids

    # Teacher 2 lists students
    response = client.get(
        "/api/guardian-profiles/students", headers=get_auth_header(teacher2)
    )
    assert response.status_code == 200
    data = response.json()
    ids = [s["id"] for s in data]
    assert student1.id not in ids
    assert student2.id in ids

    # Admin lists students (should see all)
    response = client.get(
        "/api/guardian-profiles/students", headers=get_auth_header(admin)
    )
    assert response.status_code == 200
    data = response.json()
    ids = [s["id"] for s in data]
    assert student1.id in ids
    assert student2.id in ids
    assert student3.id in ids
