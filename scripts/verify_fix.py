import sys

import requests

try:
    from .verify_common import BASE_URL, auth_headers, ensure_ok, login
except ImportError:  # Direct ``python scripts/verify_fix.py`` execution.
    from verify_common import BASE_URL, auth_headers, ensure_ok, login

BOARD_ID = 8
SYMBOL_LABEL = "horse"
LINKED_BOARD_ID = 9  # Collab Board


def get_board_symbol_id(token, board_id, label):
    headers = auth_headers(token)
    response = requests.get(f"{BASE_URL}/boards/{board_id}", headers=headers)
    board = ensure_ok(response, "Get board")
    for s in board["symbols"]:
        if s["symbol"]["label"] == label:
            return s["id"]  # This is the BoardSymbol ID

    print(f"Symbol '{label}' not found on board {board_id}")
    sys.exit(1)


def update_symbol(token, board_id, symbol_id, linked_board_id):
    headers = auth_headers(token)
    payload = {"linked_board_id": linked_board_id}
    print(f"Sending payload: {payload}")
    response = requests.put(
        f"{BASE_URL}/boards/{board_id}/symbols/{symbol_id}",
        headers=headers,
        json=payload,
    )

    result = ensure_ok(response, "Update")
    print("Update successful")
    return result


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
