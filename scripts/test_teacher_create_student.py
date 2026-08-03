import time
import traceback
import uuid

import requests

BASE_URL = "http://localhost:8086"


def test_teacher_create_student():
    print("Starting test_teacher_create_student...")

    # Wait for server to be ready
    print("Waiting for server to be ready...")
    for i in range(10):
        try:
            requests.get(f"{BASE_URL}/", timeout=1)
            print("Server is ready.")
            break
        except requests.exceptions.RequestException:
            print(f"Waiting for server... {i+1}/10")
            time.sleep(2)
    else:
        print("Server did not become ready in time.")
        return

    # 1. Create a Teacher
    teacher_username = f"teacher_mgmt_{uuid.uuid4().hex[:8]}"
    teacher_password = "Password123!"

    print(f"1. Registering teacher: {teacher_username}")
    payload = {
        "username": teacher_username,
        "password": teacher_password,
        "display_name": "Teacher Mgmt Test",
        "user_type": "teacher",
    }

    try:
        response = requests.post(
            f"{BASE_URL}/api/auth/register", json=payload, timeout=5
        )
        print(f"Register response status: {response.status_code}")
        if response.status_code != 200:
            print(
                f"Teacher registration failed: {response.status_code} {response.text}"
            )
            return
        print("Teacher registration successful.")

        # 2. Login as Teacher
        print("2. Logging in as teacher...")
        login_data = {"username": teacher_username, "password": teacher_password}
        response = requests.post(
            f"{BASE_URL}/api/auth/token", data=login_data, timeout=5
        )
        print(f"Login response status: {response.status_code}")
        if response.status_code != 200:
            print(f"Login failed: {response.text}")
            return

        token = response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 3. Create a Student
        student_username = f"student_sub_{uuid.uuid4().hex[:8]}"
        student_password = "Password123!"

        print(f"3. Creating student: {student_username}")
        student_payload = {
            "username": student_username,
            "password": student_password,
            "display_name": "Student Sub Test",
            "user_type": "student",
        }

        # The UI calls /auth/register directly
        response = requests.post(
            f"{BASE_URL}/api/auth/register", json=student_payload, timeout=5
        )
        print(f"Create student response status: {response.status_code}")
        if response.status_code != 200:
            print(f"Student creation failed: {response.status_code} {response.text}")
            return

        print("Student creation request successful.")

        # 4. Verify Student in List
        print("4. Verifying student in list...")
        response = requests.get(
            f"{BASE_URL}/api/auth/users", headers=headers, timeout=5
        )
        print(f"List users response status: {response.status_code}")
        if response.status_code != 200:
            print(f"Failed to list users: {response.status_code} {response.text}")
            return

        users = response.json()
        student_found = False
        for u in users:
            if u["username"] == student_username:
                student_found = True
                print(f"Found student: {u['username']}, Role: {u['user_type']}")
                break

        if student_found:
            print("SUCCESS: Teacher successfully created and found student.")
        else:
            print("FAILURE: Student not found in list.")

    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to backend. Is it running?")
    except Exception:
        print("An error occurred:")
        traceback.print_exc()


if __name__ == "__main__":
    test_teacher_create_student()
