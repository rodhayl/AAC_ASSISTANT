import uuid

import requests

BASE_URL = "http://localhost:8086"


def test_register_teacher():
    username = f"teacher_fix_{uuid.uuid4().hex[:8]}"
    email = f"{username}@example.com"
    password = "Password123!"

    print(f"Attempting to register teacher: {username}")

    payload = {
        "username": username,
        "email": email,
        "password": password,
        "display_name": "Teacher Fix Test",
        "user_type": "teacher",
    }

    try:
        response = requests.post(f"{BASE_URL}/api/auth/register", json=payload)

        if response.status_code != 200:
            print(f"Registration failed: {response.status_code} {response.text}")
            return

        print("Registration successful.")

        # Now login and verify role
        print("Logging in...")
        login_data = {"username": username, "password": password}
        response = requests.post(f"{BASE_URL}/api/auth/token", data=login_data)
        if response.status_code != 200:
            print(f"Login failed: {response.text}")
            return

        token = response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        print("Fetching user info via /me...")
        response = requests.get(f"{BASE_URL}/api/auth/me", headers=headers)
        user_data = response.json()

        user_id = user_data["id"]
        print(f"User ID: {user_id}")

        print(f"Fetching user info via /users/{user_id}...")
        response = requests.get(f"{BASE_URL}/api/auth/users/{user_id}", headers=headers)
        if response.status_code != 200:
            print(f"FAILED to get user by ID: {response.status_code} {response.text}")
        else:
            print("SUCCESS: Got user by ID")

        role = user_data.get("user_type")
        print(f"Registered Role: {role}")

        if role == "teacher":
            print("SUCCESS: User registered as teacher.")
        else:
            print(f"FAILURE: User registered as {role} instead of teacher.")

    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to backend. Is it running?")


if __name__ == "__main__":
    test_register_teacher()
