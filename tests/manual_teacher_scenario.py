import sys

import requests

BASE_URL = "http://localhost:8086"


def run_scenario():
    print("Starting Teacher Dashboard Scenario...")

    # 1. Login as Teacher
    login_data = {"username": "teacher_test_1", "password": "password123"}
    response = requests.post(f"{BASE_URL}/api/auth/token", data=login_data)
    if response.status_code != 200:
        print(f"Login failed: {response.text}")
        sys.exit(1)

    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("Login successful.")

    # Get current user info
    response = requests.get(f"{BASE_URL}/api/auth/me", headers=headers)
    user_id = response.json()["id"]
    print(f"Logged in as User ID: {user_id}")

    # 2. Create Board
    board_data = {
        "name": "Teacher Test Board",
        "description": "Created by automated script",
        "grid_rows": 3,
        "grid_cols": 4,
        "is_public": False,
        "ai_enabled": False,
    }
    response = requests.post(
        f"{BASE_URL}/api/boards/?user_id={user_id}", json=board_data, headers=headers
    )
    if response.status_code != 200:
        print(f"Board creation failed: {response.text}")
        sys.exit(1)

    board = response.json()
    board_id = board["id"]
    print(f"Board created: ID {board_id}, Name: {board['name']}")

    # 3. Add Symbol to Board
    # First, find a symbol to add (or assume symbol_id=1 exists)
    response = requests.get(f"{BASE_URL}/api/boards/symbols?limit=1", headers=headers)
    if response.status_code == 200 and len(response.json()) > 0:
        symbol_id = response.json()[0]["id"]
    else:
        # Create a symbol if none exist
        symbol_data = {
            "label": "Test Symbol",
            "category": "general",
            "keywords": ["test"],
        }
        response = requests.post(
            f"{BASE_URL}/api/boards/symbols", json=symbol_data, headers=headers
        )
        symbol_id = response.json()["id"]

    print(f"Adding Symbol ID {symbol_id} to Board {board_id}...")

    board_symbol_data = {
        "symbol_id": symbol_id,
        "position_x": 0,
        "position_y": 0,
        "color": "#FFFFFF",
    }
    response = requests.post(
        f"{BASE_URL}/api/boards/{board_id}/symbols",
        json=board_symbol_data,
        headers=headers,
    )
    if response.status_code != 200:
        print(f"Adding symbol failed: {response.text}")
        # Don't exit, maybe just log error
    else:
        print("Symbol added successfully.")

    # 4. Verify Board Content
    response = requests.get(f"{BASE_URL}/api/boards/{board_id}", headers=headers)
    board_details = response.json()
    symbols = board_details.get("symbols", [])
    print(f"Board has {len(symbols)} symbols.")

    found = any(s["symbol_id"] == symbol_id for s in symbols)
    if found:
        print("Verification SUCCESS: Symbol found on board.")
    else:
        print("Verification FAILED: Symbol not found on board.")
        sys.exit(1)

    print("Teacher Dashboard Scenario Completed Successfully.")


if __name__ == "__main__":
    run_scenario()
