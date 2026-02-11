"""
Test utilities for authentication in AAC Assistant tests.

Provides helper functions for creating valid JWT tokens for testing.
"""

from src.aac_app.utils.jwt_utils import create_access_token


def create_test_token(
    user_id: int, username: str = None, user_type: str = "student"
) -> str:
    """
    Create a valid JWT token for testing.

    This replaces the old mock-token-{id} pattern with real signed JWTs.

    Args:
        user_id: User's database ID
        username: Optional username (defaults to f"user{user_id}")
        user_type: User type (student, teacher, admin)

    Returns:
        Valid JWT token string

    Example:
        >>> token = create_test_token(user_id=1, username="testuser", user_type="student")
        >>> headers = {"Authorization": f"Bearer {token}"}
    """
    if username is None:
        username = f"user{user_id}"

    return create_access_token(
        data={"sub": username, "user_id": user_id, "user_type": user_type}
    )


def create_test_headers(
    user_id: int, username: str = None, user_type: str = "student"
) -> dict:
    """
    Create authorization headers with a valid JWT token for testing.

    Args:
        user_id: User's database ID
        username: Optional username (defaults to f"user{user_id}")
        user_type: User type (student, teacher, admin)

    Returns:
        Dictionary with Authorization header

    Example:
        >>> headers = create_test_headers(user_id=1, user_type="teacher")
        >>> response = client.get("/api/auth/users", headers=headers)
    """
    token = create_test_token(user_id, username, user_type)
    return {"Authorization": f"Bearer {token}"}
