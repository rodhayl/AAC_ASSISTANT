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


def get_settings(token):
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{BASE_URL}/auth/preferences", headers=headers)
    if response.status_code != 200:
        print(f"Get settings failed: {response.text}")
        sys.exit(1)
    return response.json()


def update_settings(token, dwell_time):
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"dwell_time": dwell_time}
    response = requests.put(
        f"{BASE_URL}/auth/preferences", headers=headers, json=payload
    )
    if response.status_code != 200:
        print(f"Update settings failed: {response.text}")
        sys.exit(1)
    return response.json()


def main():
    print("Logging in...")
    token = login()

    print("Getting current settings...")
    settings = get_settings(token)
    print(f"Current dwell_time: {settings.get('dwell_time')}")

    new_dwell = 500 if settings.get("dwell_time") != 500 else 1000
    print(f"Updating dwell_time to {new_dwell}...")

    updated = update_settings(token, new_dwell)
    print(f"Updated dwell_time: {updated.get('dwell_time')}")

    if updated.get("dwell_time") == new_dwell:
        print("VERIFICATION PASSED: Settings updated successfully")
    else:
        print("VERIFICATION FAILED: Settings mismatch")


if __name__ == "__main__":
    main()
