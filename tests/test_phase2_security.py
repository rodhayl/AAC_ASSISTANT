"""
Comprehensive tests for Phase 2 security improvements.

Tests:
1. Password confirmation validation for admin/create-user
2. Token refresh mechanism (/auth/refresh endpoint)
3. Rate limiting on auth endpoints (integration test)
4. ENVIRONMENT=production enforcement (JWT secret validation)
5. Token expiration validation

Phase 2 implementation: November 30, 2025
"""

import importlib
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import jwt
import pytest
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy.orm import Session

from src.aac_app.models.database import User
from src.aac_app.services.auth_service import get_password_hash
from src.aac_app.utils.jwt_utils import (
    JWT_ALGORITHM,
    JWT_SECRET_KEY,
    create_access_token,
    create_refresh_token,
    decode_access_token,
)
from src.api.dependencies import get_db
from src.api.main import app
from tests.test_utils_auth import create_test_headers


@pytest.fixture
def client(test_db_session: Session):
    """Create FastAPI test client with test database."""

    def override_get_db():
        try:
            yield test_db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def admin_user(test_db_session: Session):
    """Create admin user for tests."""
    admin = User(
        username="admin_phase2",
        display_name="Admin Phase2",
        user_type="admin",
        password_hash=get_password_hash("AdminPass123"),
        is_active=True,
    )
    test_db_session.add(admin)
    test_db_session.commit()
    test_db_session.refresh(admin)
    return admin


class TestPasswordConfirmation:
    """Tests for password confirmation validation in admin/create-user."""

    def test_admin_create_user_requires_password_confirmation(
        self, client: TestClient, admin_user: User
    ):
        """Admin must provide password confirmation when creating users."""
        headers = create_test_headers(
            admin_user.id, admin_user.username, admin_user.user_type
        )

        response = client.post(
            "/api/auth/admin/create-user",
            json={
                "username": "newteacher",
                "display_name": "New Teacher",
                "user_type": "teacher",
                "password": "TeacherPass123",
                # Missing confirm_password
            },
            headers=headers,
        )

        assert response.status_code == 400
        assert "confirmation is required" in response.json()["detail"].lower()

    def test_admin_create_user_passwords_must_match(
        self, client: TestClient, admin_user: User
    ):
        """Password and confirm_password must match."""
        headers = create_test_headers(
            admin_user.id, admin_user.username, admin_user.user_type
        )

        response = client.post(
            "/api/auth/admin/create-user",
            json={
                "username": "newteacher",
                "display_name": "New Teacher",
                "user_type": "teacher",
                "password": "TeacherPass123",
                "confirm_password": "DifferentPass123",  # Doesn't match
            },
            headers=headers,
        )

        assert response.status_code == 400
        assert "do not match" in response.json()["detail"].lower()

    def test_admin_create_user_with_valid_confirmation(
        self, client: TestClient, admin_user: User, test_db_session: Session
    ):
        """Admin can create user when passwords match."""
        headers = create_test_headers(
            admin_user.id, admin_user.username, admin_user.user_type
        )

        response = client.post(
            "/api/auth/admin/create-user",
            json={
                "username": "newteacher",
                "display_name": "New Teacher",
                "user_type": "teacher",
                "password": "TeacherPass123",
                "confirm_password": "TeacherPass123",  # Matches!
            },
            headers=headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "newteacher"
        assert data["user_type"] == "teacher"

        # Verify user created in database
        user = test_db_session.query(User).filter(User.username == "newteacher").first()
        assert user is not None
        assert user.user_type == "teacher"


class TestTokenRefreshMechanism:
    """Tests for token refresh endpoint."""

    def test_refresh_token_returned_on_login(
        self, client: TestClient, test_db_session: Session
    ):
        """Login should return both access_token and refresh_token."""
        # Create test user
        user = User(
            username="refresh_user",
            display_name="Refresh User",
            user_type="student",
            password_hash=get_password_hash("UserPass123"),
            is_active=True,
        )
        test_db_session.add(user)
        test_db_session.commit()

        # Login
        response = client.post(
            "/api/auth/token",
            data={"username": "refresh_user", "password": "UserPass123"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert "token_type" in data
        assert data["token_type"] == "bearer"

        # Verify refresh token is valid JWT
        refresh_token = data["refresh_token"]
        payload = decode_access_token(refresh_token)
        assert payload is not None
        assert payload["type"] == "refresh"
        assert payload["user_id"] == user.id

    def test_refresh_endpoint_with_valid_token(
        self, client: TestClient, test_db_session: Session
    ):
        """Refresh endpoint should return new access token."""
        # Create test user
        user = User(
            username="refresh_user2",
            display_name="Refresh User 2",
            user_type="student",
            password_hash=get_password_hash("UserPass123"),
            is_active=True,
        )
        test_db_session.add(user)
        test_db_session.commit()

        # Create refresh token
        refresh_token = create_refresh_token({"sub": user.username, "user_id": user.id})

        # Call refresh endpoint
        response = client.post(f"/api/auth/refresh?refresh_token={refresh_token}")

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

        # Verify new access token is valid
        new_access_token = data["access_token"]
        payload = decode_access_token(new_access_token)
        assert payload is not None
        assert payload["user_id"] == user.id
        assert payload["sub"] == user.username

    def test_refresh_endpoint_rejects_access_token(
        self, client: TestClient, test_db_session: Session
    ):
        """Refresh endpoint should reject access tokens (not refresh tokens)."""
        # Create test user
        user = User(
            username="refresh_user3",
            display_name="Refresh User 3",
            user_type="student",
            password_hash=get_password_hash("UserPass123"),
            is_active=True,
        )
        test_db_session.add(user)
        test_db_session.commit()

        # Create ACCESS token (not refresh)
        access_token = create_access_token(
            {"sub": user.username, "user_id": user.id, "user_type": user.user_type}
        )

        # Try to use access token at refresh endpoint
        response = client.post(f"/api/auth/refresh?refresh_token={access_token}")

        assert response.status_code == 401
        assert "invalid token type" in response.json()["detail"].lower()

    def test_refresh_endpoint_rejects_expired_token(self, client: TestClient):
        """Refresh endpoint should reject expired refresh tokens."""
        # Create expired refresh token
        expired_token = jwt.encode(
            {
                "sub": "someuser",
                "user_id": 999,
                "exp": datetime.now(timezone.utc)
                - timedelta(hours=1),  # Expired 1 hour ago
                "iat": datetime.now(timezone.utc) - timedelta(days=8),
                "iss": "aac-assistant",
                "type": "refresh",
            },
            JWT_SECRET_KEY,
            algorithm=JWT_ALGORITHM,
        )

        response = client.post(f"/api/auth/refresh?refresh_token={expired_token}")

        assert response.status_code == 401
        assert "invalid or expired" in response.json()["detail"].lower()

    def test_refresh_endpoint_rejects_inactive_user(
        self, client: TestClient, test_db_session: Session
    ):
        """Refresh endpoint should reject tokens for inactive users."""
        # Create inactive user
        user = User(
            username="inactive_user",
            display_name="Inactive User",
            user_type="student",
            password_hash=get_password_hash("UserPass123"),
            is_active=False,  # Inactive!
        )
        test_db_session.add(user)
        test_db_session.commit()

        # Create valid refresh token
        refresh_token = create_refresh_token({"sub": user.username, "user_id": user.id})

        # Try to refresh
        response = client.post(f"/api/auth/refresh?refresh_token={refresh_token}")

        assert response.status_code == 403
        assert "inactive" in response.json()["detail"].lower()


class TestRateLimiting:
    """Tests for rate limiting on auth endpoints."""

    # @pytest.mark.skip(reason="Rate limiting requires actual time delays, skip in CI")
    def test_login_rate_limiting(self, client: TestClient, test_db_session: Session):
        """Login endpoint should enforce rate limit (10/minute)."""
        # Create test user
        user = User(
            username="ratelimit_user",
            display_name="Rate Limit User",
            user_type="student",
            password_hash=get_password_hash("UserPass123"),
            is_active=True,
        )
        test_db_session.add(user)
        test_db_session.commit()

        # Enable rate limiting by mocking TESTING=0
        with patch.dict(os.environ, {"TESTING": "0"}):
            # Add exception handler manually since it's skipped in main.py when TESTING=1
            app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

            try:
                # Make 11 login attempts (limit is 10/minute)
                for i in range(11):
                    # Use a unique IP for this test run to avoid conflict with other tests
                    # But slowapi defaults to remote_address.
                    # We can set X-Forwarded-For if we trusted it, but let's rely on the fact
                    # that this user/IP combination hasn't been used yet if we assume test isolation.
                    # Actually, limiter storage is in-memory.
                    # If previous tests used the IP, we might be already blocked.
                    # So we should mock the key_func or use a fresh IP.

                    # headers = {
                    #     "X-Forwarded-For": f"10.0.0.{i + 1}"
                    # }  # Try to spoof IP if possible, or just rely on clean state

                    # Since we can't easily clear the limiter state without access to the limiter instance
                    # and its storage, we'll try to run it. If it fails due to pre-existing limit,
                    # we might need a different strategy.

                    # Actually, slowapi's get_remote_address uses request.client.host.
                    # TestClient allows setting client host.

                    response = client.post(
                        "/api/auth/token",
                        data={"username": "ratelimit_user", "password": "UserPass123"},
                    )

                    if i < 10:
                        # It might fail early if other tests used the quota.
                        # But since we just enabled it, maybe it's fresh?
                        # Wait, the Limiter instance in auth.py is global.
                        # If it was initialized with TESTING=1 (default), it might be a mock or disabled?
                        # In auth.py: _limiter_instance = Limiter(...)
                        # It is NOT conditional on env at import time.
                        # The conditional_limiter wrapper checks env at RUNTIME.
                        # So setting TESTING=0 works!

                        assert (
                            response.status_code == 200
                        ), f"Request {i + 1} should succeed"
                    else:
                        assert (
                            response.status_code == 429
                        ), "Request 11 should be rate limited"
                        # SlowAPI default handler returns {"error": "..."} but can be configured.
                        # We check for either 'detail' (FastAPI default) or 'error' (SlowAPI default)
                        data = response.json()
                        msg = data.get("detail") or data.get("error") or ""
                        assert "rate limit" in msg.lower()
            finally:
                # Remove exception handler to clean up?
                # Dict.pop might raise if not found, but it should be there.
                app.exception_handlers.pop(RateLimitExceeded, None)

    # @pytest.mark.skip(reason="Rate limiting requires actual time delays, skip in CI")
    def test_register_rate_limiting(self, client: TestClient):
        """Registration endpoint should enforce rate limit (5/hour)."""

        with patch.dict(os.environ, {"TESTING": "0"}):
            app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

            try:
                # Make 6 registration attempts (limit is 5/hour)
                for i in range(6):
                    response = client.post(
                        "/api/auth/register",
                        json={
                            "username": f"newuser_rl_{i}",
                            "display_name": f"New User {i}",
                            "password": "UserPass123",
                        },
                    )

                    if i < 5:
                        assert (
                            response.status_code == 200
                        ), f"Request {i + 1} should succeed"
                    else:
                        assert (
                            response.status_code == 429
                        ), "Request 6 should be rate limited"
            finally:
                app.exception_handlers.pop(RateLimitExceeded, None)


class TestEnvironmentEnforcement:
    """Tests for ENVIRONMENT=production enforcement."""

    def test_jwt_secret_key_loaded_from_config(self, monkeypatch):
        """JWT_SECRET_KEY should be loaded from config/env, not fallback default."""
        import importlib
        import src.aac_app.utils.jwt_utils as jwt_utils

        test_secret = "unit_test_secret_key_32_chars_min"
        monkeypatch.setenv("JWT_SECRET_KEY", test_secret)
        jwt_utils = importlib.reload(jwt_utils)

        # Should NOT be the default insecure value
        assert jwt_utils.JWT_SECRET_KEY != "INSECURE_DEFAULT_CHANGE_IN_PRODUCTION"
        # Should use configured value
        assert jwt_utils.JWT_SECRET_KEY == test_secret

    def test_environment_variable_set_to_development(self):
        """ENVIRONMENT should be set to 'development' in env.properties."""
        from src import config

        env = config.get("ENVIRONMENT", "development")
        assert (
            env == "development"
        ), "ENVIRONMENT should be 'development' in env.properties"

    # @pytest.mark.skip(reason="Cannot test production enforcement without changing env.properties")
    def test_production_rejects_default_jwt_secret(self):
        """In production, using default JWT_SECRET_KEY should raise ValueError."""

        # Use patch.dict to set environment variables
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "production",
                "JWT_SECRET_KEY": "INSECURE_DEFAULT_CHANGE_IN_PRODUCTION",
            },
        ):
            # Reload the module to trigger the import-time check
            import src.aac_app.utils.jwt_utils

            try:
                # This should raise ValueError
                with pytest.raises(
                    ValueError, match="JWT_SECRET_KEY must be set to a secure value"
                ):
                    importlib.reload(src.aac_app.utils.jwt_utils)
            finally:
                # Always restore the module to a valid state
                # We need to ensure ENVIRONMENT is not production or Key is valid
                # Removing the patch happens automatically by context manager,
                # but we must reload the module to clear the 'bad' state from memory
                pass

        # Reload outside the patch to restore original valid state
        importlib.reload(src.aac_app.utils.jwt_utils)


class TestTokenExpirationValidation:
    """Tests for token expiration handling."""

    def test_expired_access_token_rejected(
        self, client: TestClient, test_db_session: Session
    ):
        """Expired access tokens should be rejected by protected endpoints."""
        # Create test user
        user = User(
            username="expiry_user",
            display_name="Expiry User",
            user_type="student",
            password_hash=get_password_hash("UserPass123"),
            is_active=True,
        )
        test_db_session.add(user)
        test_db_session.commit()

        # Create expired token
        expired_token = jwt.encode(
            {
                "sub": user.username,
                "user_id": user.id,
                "user_type": user.user_type,
                "exp": datetime.now(timezone.utc)
                - timedelta(hours=1),  # Expired 1 hour ago
                "iat": datetime.now(timezone.utc) - timedelta(hours=3),
                "iss": "aac-assistant",
            },
            JWT_SECRET_KEY,
            algorithm=JWT_ALGORITHM,
        )

        # Try to use expired token
        response = client.get(
            "/api/auth/preferences",
            headers={"Authorization": f"Bearer {expired_token}"},
        )

        assert response.status_code == 401
        detail = response.json()["detail"].lower()
        assert "token" in detail or "credential" in detail

    def test_valid_token_accepted(self, client: TestClient, test_db_session: Session):
        """Valid, non-expired tokens should be accepted."""
        # Create test user
        user = User(
            username="valid_user",
            display_name="Valid User",
            user_type="student",
            password_hash=get_password_hash("UserPass123"),
            is_active=True,
        )
        test_db_session.add(user)
        test_db_session.commit()

        # Create valid token
        token = create_access_token(
            {"sub": user.username, "user_id": user.id, "user_type": user.user_type}
        )

        # Use valid token
        response = client.get(
            "/api/auth/preferences", headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200

    def test_token_expiration_time_is_2_hours(self):
        """Access tokens should expire in 2 hours."""
        from src.aac_app.utils.jwt_utils import ACCESS_TOKEN_EXPIRE_MINUTES

        assert (
            ACCESS_TOKEN_EXPIRE_MINUTES == 120
        ), "Access token should expire in 2 hours (120 minutes)"

    def test_refresh_token_expiration_time_is_7_days(self):
        """Refresh tokens should expire in 7 days."""
        from src.aac_app.utils.jwt_utils import REFRESH_TOKEN_EXPIRE_DAYS

        assert REFRESH_TOKEN_EXPIRE_DAYS == 7, "Refresh token should expire in 7 days"


class TestChangePasswordSecurity:
    """Tests for change-password endpoint security."""

    def test_change_password_requires_strong_password(
        self, client: TestClient, test_db_session: Session
    ):
        """Change password should enforce password strength requirements."""
        # Create test user
        user = User(
            username="change_user",
            display_name="Change User",
            user_type="student",
            password_hash=get_password_hash("OldPass123"),
            is_active=True,
        )
        test_db_session.add(user)
        test_db_session.commit()

        headers = create_test_headers(user.id, user.username, user.user_type)

        # Try weak password
        response = client.post(
            "/api/auth/change-password",
            json={
                "username": "change_user",
                "current_password": "OldPass123",
                "new_password": "weak",  # Too short, no uppercase
                "confirm_password": "weak",
            },
            headers=headers,
        )

        assert response.status_code == 400
        assert "password" in response.json()["detail"].lower()

    def test_change_password_requires_confirmation(
        self, client: TestClient, test_db_session: Session
    ):
        """Change password should require matching confirmation."""
        # Create test user
        user = User(
            username="change_user2",
            display_name="Change User 2",
            user_type="student",
            password_hash=get_password_hash("OldPass123"),
            is_active=True,
        )
        test_db_session.add(user)
        test_db_session.commit()

        headers = create_test_headers(user.id, user.username, user.user_type)

        # Mismatched confirmation
        response = client.post(
            "/api/auth/change-password",
            json={
                "username": "change_user2",
                "current_password": "OldPass123",
                "new_password": "NewPass123",
                "confirm_password": "DifferentPass123",  # Doesn't match
            },
            headers=headers,
        )

        assert response.status_code == 400
        assert "do not match" in response.json()["detail"].lower()

