import os
import sys

import requests

# Configuration
BASE_URL = os.environ.get("AAC_BASE_URL", "http://localhost:8086/api").rstrip("/")
USERNAME = os.environ.get("AAC_VERIFY_USERNAME", "").strip()
PASSWORD = os.environ.get("AAC_VERIFY_PASSWORD", "").strip()

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


def get_suggestions(token, current_symbols):
    headers = {"Authorization": f"Bearer {token}"}
    params = {"current_symbols": current_symbols, "limit": 5}
    print(f"Requesting suggestions for: '{current_symbols}'")
    response = requests.get(
        f"{BASE_URL}/analytics/next-symbol", headers=headers, params=params
    )

    if response.status_code != 200:
        print(f"Get suggestions failed: {response.status_code} {response.text}")
        sys.exit(1)

    return response.json()


def main():
    print("Logging in...")
    token = login()

    # Test 1: Empty context
    suggestions = get_suggestions(token, "")
    print(f"Suggestions (empty context): {suggestions}")
    if not isinstance(suggestions, list):
        print("FAILED: Expected list of suggestions")
        sys.exit(1)

    # Test 2: "I want" context
    suggestions = get_suggestions(token, "I,want")
    print(f"Suggestions ('I,want'): {suggestions}")

    print("VERIFICATION PASSED: Smartbar API is responsive")


if __name__ == "__main__":
    main()
