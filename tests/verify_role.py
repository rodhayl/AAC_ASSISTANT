import sys

import requests

BASE_URL = "http://localhost:8086"


def check_role(username, password, expected_role):
    print(f"Checking role for {username}...")
    login_data = {"username": username, "password": password}
    response = requests.post(f"{BASE_URL}/api/auth/token", data=login_data)
    if response.status_code != 200:
        print(f"Login failed: {response.text}")
        return False

    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    response = requests.get(f"{BASE_URL}/api/auth/me", headers=headers)
    user_data = response.json()

    actual_role = user_data.get("user_type")
    print(f"User: {username}, Role: {actual_role}, Expected: {expected_role}")

    if actual_role == expected_role:
        print("MATCH")
        return True
    else:
        print("MISMATCH")
        return False


if __name__ == "__main__":
    r1 = check_role("student_e2e_1", "Password123", "student")
    r2 = check_role("teacher_e2e_1", "Password123", "teacher")

    if r1 and r2:
        print("All roles correct.")
    else:
        print("Role verification failed.")
        sys.exit(1)
