import requests

BASE_URL = "http://localhost:8086"


def check_user_role(username, password):
    print(f"Checking role for {username}...")
    login_data = {"username": username, "password": password}
    response = requests.post(f"{BASE_URL}/api/auth/token", data=login_data)
    if response.status_code != 200:
        print(f"Login failed: {response.text}")
        return

    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    response = requests.get(f"{BASE_URL}/api/auth/me", headers=headers)
    user_data = response.json()

    print(
        f"User: {username}, Role: {user_data.get('user_type')}, ID: {user_data.get('id')}"
    )


if __name__ == "__main__":
    check_user_role("teacher_ui_test_1", "Password123!")
