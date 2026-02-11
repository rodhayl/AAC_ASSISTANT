import os
import sys

import requests

# Configuration
BASE_URL = os.environ.get("AAC_BASE_URL", "http://localhost:8086/api").rstrip("/")
USERNAME = os.environ.get("AAC_VERIFY_USERNAME", "").strip()
PASSWORD = os.environ.get("AAC_VERIFY_PASSWORD", "").strip()
BOARD_ID = 8
SYMBOL_LABEL = "horse"
LINKED_BOARD_ID = 9  # Collab Board

if not USERNAME or not PASSWORD:
    raise SystemExit(
        "Set AAC_VERIFY_USERNAME and AAC_VERIFY_PASSWORD before running this script."
    )


def login():
    response = requests.post(
        f"{BASE_URL}/auth/token", data={"username": USERNAME, "password": PASSWORD}
    )
    if response.status_code != 200:
        print(f"Login failed: {response.text}")
        sys.exit(1)
    return response.json()["access_token"]


def get_board_symbol_id(token, board_id, label):
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{BASE_URL}/boards/{board_id}", headers=headers)
    if response.status_code != 200:
        print(f"Get board failed: {response.text}")
        sys.exit(1)

    board = response.json()
    for s in board["symbols"]:
        if s["symbol"]["label"] == label:
            return s["id"]  # This is the BoardSymbol ID

    print(f"Symbol '{label}' not found on board {board_id}")
    sys.exit(1)


def update_symbol(token, board_id, symbol_id, linked_board_id):
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"linked_board_id": linked_board_id}
    print(f"Sending payload: {payload}")
    response = requests.put(
        f"{BASE_URL}/boards/{board_id}/symbols/{symbol_id}",
        headers=headers,
        json=payload,
    )

    if response.status_code != 200:
        print(f"Update failed: {response.status_code} {response.text}")
        sys.exit(1)

    print("Update successful")
    return response.json()


def main():
    print("Logging in...")
    token = login()

    print(f"Getting symbol ID for '{SYMBOL_LABEL}'...")
    symbol_id = get_board_symbol_id(token, BOARD_ID, SYMBOL_LABEL)
    print(f"Found symbol ID: {symbol_id}")

    print(f"Linking symbol to board {LINKED_BOARD_ID}...")
    result = update_symbol(token, BOARD_ID, symbol_id, LINKED_BOARD_ID)

    print("Result:", result)

    if result.get("linked_board_id") == LINKED_BOARD_ID:
        print("VERIFICATION PASSED: linked_board_id is correct in response")
    else:
        print("VERIFICATION FAILED: linked_board_id mismatch in response")


if __name__ == "__main__":
    main()
