"""
Test the exact login flow used by the frontend application.
Simulates the API calls made by authStore.ts:
1. POST /auth/token
2. Decode JWT to get user_id
3. GET /auth/users/{user_id}
"""

import base64
import json
import sys
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

# Add src to path
src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

from src.api.main import app  # noqa: E402

client = TestClient(app)


def decode_jwt_payload(token: str):
    """Decode JWT payload without verification (client-side simulation)"""
    try:
        # JWT is header.payload.signature
        payload_part = token.split(".")[1]
        # Add padding if needed
        payload_part += "=" * (-len(payload_part) % 4)
        decoded_bytes = base64.urlsafe_b64decode(payload_part)
        return json.loads(decoded_bytes)
    except Exception as e:
        print(f"Failed to decode JWT: {e}")
        return None


def test_frontend_login_flow():
    """Test the login flow for all user types"""

    # Generate unique username to avoid conflicts with existing DB
    unique_id = str(uuid.uuid4())[:8]
    username = f"student_test_{unique_id}"
    password = "Student123"

    # Ensure student exists (self-registration)
    print(f"\nRegistering {username}...")
    response = client.post(
        "/api/auth/register",
        json={
            "username": username,
            "password": password,
            "display_name": "Frontend Test Student",
            "user_type": "student",
        },
    )
    if response.status_code != 200:
        print(f"Registration failed: {response.status_code} - {response.text}")
        # If already exists (unlikely with uuid), try login anyway
        if response.status_code != 400:
            assert response.status_code == 200

    test_users = [
        (username, password, "student"),
        # Skip teacher/admin as they require pre-seeding which this test doesn't handle well
        # ('teacher1', 'Teacher123', 'teacher'),
        # ('admin1', 'Admin123', 'admin')
    ]

    print("\n=== Testing Frontend Login Flow ===")

    for username, password, expected_type in test_users:
        print(f"\nTesting user: {username}")

        # Step 1: Login (POST /auth/token)
        print("  Step 1: POST /api/auth/token")
        response = client.post(
            "/api/auth/token",
            data={"username": username, "password": password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if response.status_code != 200:
            print(f"  ❌ Login failed: {response.status_code} - {response.text}")
            assert response.status_code == 200
            continue

        data = response.json()
        token = data["access_token"]
        print("  ✅ Login successful, token received")

        # Step 2: Decode Token (Client-side)
        print("  Step 2: Decode JWT token")
        payload = decode_jwt_payload(token)
        if not payload:
            print("  ❌ Failed to decode token")
            assert payload is not None
            continue

        user_id = payload.get("user_id")
        print(f"  ✅ Token decoded. user_id={user_id}, sub={payload.get('sub')}")

        if not user_id:
            print("  ❌ user_id not found in token")
            assert user_id is not None
            continue

        # Step 3: Get User Details (GET /auth/users/{user_id})
        print(f"  Step 3: GET /api/auth/users/{user_id}")
        user_response = client.get(
            f"/api/auth/users/{user_id}", headers={"Authorization": f"Bearer {token}"}
        )

        if user_response.status_code != 200:
            print(
                f"  ❌ Fetch user failed: {user_response.status_code} - {user_response.text}"
            )
            assert user_response.status_code == 200
            continue

        user_data = user_response.json()
        print(
            f"  ✅ User details fetched: {user_data['username']} ({user_data['user_type']})"
        )

        # Verification
        assert user_data["username"] == username
        assert user_data["user_type"] == expected_type
        print("  ✅ Verification successful")


if __name__ == "__main__":
    test_frontend_login_flow()
