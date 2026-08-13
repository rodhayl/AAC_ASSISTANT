import sys

import requests

try:
    from .verify_common import BASE_URL, auth_headers, ensure_ok, login
except ImportError:  # Direct ``python scripts/verify_smartbar.py`` execution.
    from verify_common import BASE_URL, auth_headers, ensure_ok, login


def get_suggestions(token, current_symbols):
    headers = auth_headers(token)
    params = {"current_symbols": current_symbols, "limit": 5}
    print(f"Requesting suggestions for: '{current_symbols}'")
    response = requests.get(
        f"{BASE_URL}/analytics/next-symbol", headers=headers, params=params
    )

    return ensure_ok(response, "Get suggestions")


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
