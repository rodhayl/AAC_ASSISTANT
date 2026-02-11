import time
import traceback
import uuid

import requests

BASE_URL = "http://localhost:8086"


def test_student_board_creation():
    print("Starting test_student_board_creation...")

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

    # 1. Create a Student
    student_username = f"student_board_{uuid.uuid4().hex[:8]}"
    student_password = "Password123!"

    print(f"1. Registering student: {student_username}")
    payload = {
        "username": student_username,
        "password": student_password,
        "display_name": "Student Board Test",
        "user_type": "student",
    }

    try:
        response = requests.post(
            f"{BASE_URL}/api/auth/register", json=payload, timeout=5
        )
        print(f"Register response status: {response.status_code}")
        if response.status_code != 200:
            print(
                f"Student registration failed: {response.status_code} {response.text}"
            )
            return
        print("Student registration successful.")

        # 2. Login as Student
        print("2. Logging in as student...")
        login_data = {"username": student_username, "password": student_password}
        response = requests.post(
            f"{BASE_URL}/api/auth/token", data=login_data, timeout=5
        )
        print(f"Login response status: {response.status_code}")
        if response.status_code != 200:
            print(f"Login failed: {response.text}")
            return

        token = response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Get user ID from /me to pass to board creation if needed (though the endpoint seems to require it as a query param)
        response = requests.get(f"{BASE_URL}/api/auth/me", headers=headers, timeout=5)
        user_id = response.json()["id"]
        print(f"Student User ID: {user_id}")

        # 3. Create a Board
        board_name = "My Student Board"
        print(f"3. Creating board: {board_name}")
        board_payload = {
            "name": board_name,
            "description": "A board created by a student",
            "is_public": False,
            "grid_columns": 4,
            "grid_rows": 3,
        }

        # Note: The error 422 indicated "user_id" query param was missing.
        # Looking at boards.py:399 `user_id: int,` is a query param (default for scalar types in FastAPI)

        response = requests.post(
            f"{BASE_URL}/api/boards/?user_id={user_id}",
            json=board_payload,
            headers=headers,
            timeout=5,
        )
        print(f"Create board response status: {response.status_code}")

        if response.status_code == 200:
            print("SUCCESS: Student successfully created a board.")
            board_data = response.json()
            print(f"Board ID: {board_data['id']}, Owner ID: {board_data['user_id']}")
        elif response.status_code == 403:
            print(
                "FAILURE: Student forbidden from creating board (Expected if policy restricts this)."
            )
        else:
            print(
                f"FAILURE: Unexpected status code {response.status_code} {response.text}"
            )

    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to backend. Is it running?")
    except Exception:
        print("An error occurred:")
        traceback.print_exc()


if __name__ == "__main__":
    test_student_board_creation()
