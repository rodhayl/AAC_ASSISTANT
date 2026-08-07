import requests

try:
    from .verify_common import BASE_URL, auth_headers, ensure_ok, login
except ImportError:  # Direct ``python scripts/verify_settings.py`` execution.
    from verify_common import BASE_URL, auth_headers, ensure_ok, login


def get_settings(token):
    headers = auth_headers(token)
    response = requests.get(f"{BASE_URL}/auth/preferences", headers=headers)
    return ensure_ok(response, "Get settings")


def update_settings(token, dwell_time):
    headers = auth_headers(token)
    payload = {"dwell_time": dwell_time}
    response = requests.put(
        f"{BASE_URL}/auth/preferences", headers=headers, json=payload
    )
    return ensure_ok(response, "Update settings")


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
