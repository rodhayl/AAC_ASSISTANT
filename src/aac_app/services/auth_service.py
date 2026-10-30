"""
Authentication service for password hashing and verification.

Uses bcrypt directly for secure password hashing with automatic salting.
"""

import bcrypt
from loguru import logger


def get_password_hash(password: str) -> str:
    """
    Hash a password using bcrypt with automatic salt generation.

    Args:
        password: Plain text password to hash

    Returns:
        Bcrypt hash string (includes salt and algorithm info)
    """
    if not password:
        raise ValueError("Password cannot be empty")

    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain password against a bcrypt hash.

    Args:
        plain_password: Plain text password to verify
        hashed_password: Bcrypt hash to verify against

    Returns:
        True if password matches, False otherwise
    """
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), hashed_password.encode("utf-8")
        )
    except Exception as e:
        logger.warning(f"Password verification failed: {e}")
        return False
