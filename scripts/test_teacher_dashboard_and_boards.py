import time
import traceback
import uuid

import requests

BASE_URL = "http://localhost:8086"


def test_teacher_dashboard_and_boards():
    print("Starting test_teacher_dashboard_and_boards...")

    # Wait for server to be ready
    print("Waiting for server to be ready...")
    for i in range(10):
        try:
            requests.get(f"{BASE_URL}/", timeout=1)
            print("Server is ready.")
            break
        except Exception:
            print(f"Waiting for server... {i+1}/10")
            time.sleep(2)
    else:
        print("Server did not become ready in time.")
        return

    # 1. Create a Teacher
    teacher_username = f"teacher_dash_{uuid.uuid4().hex[:8]}"
    teacher_password = "Password123!"

    print(f"1. Registering teacher: {teacher_username}")
    payload = {
        "username": teacher_username,
        "password": teacher_password,
        "display_name": "Teacher Dash Test",
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

        # Get user ID
        response = requests.get(f"{BASE_URL}/api/auth/me", headers=headers, timeout=5)
        teacher_id = response.json()["id"]
        print(f"Teacher User ID: {teacher_id}")

        # 3. Create a Board (for dashboard)
        board_name = "Teacher Dashboard Board"
        print(f"3. Creating board: {board_name}")
        board_payload = {
            "name": board_name,
            "description": "A board created by a teacher",
            "is_public": False,
            "grid_columns": 5,
            "grid_rows": 4,
        }

        response = requests.post(
            f"{BASE_URL}/api/boards/?user_id={teacher_id}",
            json=board_payload,
            headers=headers,
            timeout=5,
        )
        print(f"Create board response status: {response.status_code}")

        if response.status_code != 200:
            print(
                f"FAILURE: Board creation failed {response.status_code} {response.text}"
            )
            return

        board_id = response.json()["id"]
        print(f"Board created: {board_id}")

        # 4. Verify Board Appears in List (Dashboard)
        print("4. Verifying board in dashboard list...")
        response = requests.get(
            f"{BASE_URL}/api/boards/?user_id={teacher_id}", headers=headers, timeout=5
        )
        if response.status_code != 200:
            print(f"FAILURE: List boards failed {response.status_code} {response.text}")
            return

        boards = response.json()
        board_found = False
        for b in boards:
            if b["id"] == board_id:
                board_found = True
                print(f"Found board: {b['name']} (ID: {b['id']})")
                break

        if board_found:
            print("SUCCESS: Teacher dashboard lists created board.")
        else:
            print("FAILURE: Created board not found in list.")

        # 5. Check Public Boards Visibility
        print("5. Checking public boards visibility...")
        # Create a public board as teacher
        public_board_name = "Public Teacher Board"
        print(f"Creating public board: {public_board_name}")
        public_board_payload = {
            "name": public_board_name,
            "description": "A public board",
            "is_public": True,
            "grid_columns": 3,
            "grid_rows": 3,
        }
        response = requests.post(
            f"{BASE_URL}/api/boards/?user_id={teacher_id}",
            json=public_board_payload,
            headers=headers,
            timeout=5,
        )
        if response.status_code == 200:
            print("SUCCESS: Public board created.")
        else:
            print(f"FAILURE: Public board creation failed {response.status_code}")

    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to backend. Is it running?")
    except Exception:
        print("An error occurred:")
        traceback.print_exc()


if __name__ == "__main__":
    test_teacher_dashboard_and_boards()
