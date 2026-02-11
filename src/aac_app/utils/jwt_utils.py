"""
JWT token utilities for secure authentication.

Provides JWT token creation, validation, and secret key management.
Uses HS256 algorithm for signing with a secret key from environment.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import jwt
from loguru import logger

from src import config

# JWT Configuration
# Load from env.properties via config module (environment variables take precedence)
JWT_SECRET_KEY = config.get("JWT_SECRET_KEY", "INSECURE_DEFAULT_CHANGE_IN_PRODUCTION")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 120  # 2 hours
REFRESH_TOKEN_EXPIRE_DAYS = 7  # 7 days

# Enforce secure secret in production
if config.get("ENVIRONMENT", "development") == "production":
    if JWT_SECRET_KEY == "INSECURE_DEFAULT_CHANGE_IN_PRODUCTION":
        raise ValueError(
            "CRITICAL SECURITY ERROR: JWT_SECRET_KEY must be set to a secure value in production. "
            "Generate one with: python -c 'import secrets; print(secrets.token_hex(32))'"
        )


def create_access_token(
    data: Dict[str, Any], expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create a JWT access token.

    Args:
        data: Dictionary of claims to encode in the token (e.g., {"sub": username, "user_id": id})
        expires_delta: Optional custom expiration time. Defaults to ACCESS_TOKEN_EXPIRE_MINUTES.

    Returns:
        Encoded JWT token as a string

    Raises:
        ValueError: If JWT_SECRET_KEY is not set or is the default insecure value in production
    """
    if JWT_SECRET_KEY == "INSECURE_DEFAULT_CHANGE_IN_PRODUCTION":
        logger.critical(
            "JWT_SECRET_KEY is using default insecure value! Set JWT_SECRET_KEY environment variable."
        )
        # In production, this should raise an error. For development, we'll log a warning.
        if os.getenv("ENVIRONMENT") == "production":
            raise ValueError("JWT_SECRET_KEY must be set in production environment")

    to_encode = data.copy()

    # Set expiration time
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        )

    to_encode.update(
        {
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "iss": "aac-assistant",  # Issuer claim
        }
    )

    # Create the JWT token
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

    logger.debug(f"Created JWT token for subject: {data.get('sub')}, expires: {expire}")
    return encoded_jwt


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Decode and validate a JWT access token.

    Args:
        token: The JWT token string to decode

    Returns:
        Dictionary of claims if token is valid, None if invalid or expired
    """
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_iat": True,
                "require": ["exp", "iat", "sub"],
            },
        )

        # Verify issuer if present
        if payload.get("iss") != "aac-assistant":
            logger.warning(f"Invalid token issuer: {payload.get('iss')}")
            return None

        return payload

    except jwt.ExpiredSignatureError:
        logger.warning("Token has expired")
        return None

    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid token: {e}")
        return None

    except Exception as e:
        logger.error(f"Unexpected error decoding token: {e}")
        return None


def get_token_expiration(token: str) -> Optional[datetime]:
    """
    Get the expiration time of a token without full validation.

    Args:
        token: JWT token string

    Returns:
        datetime object of expiration, or None if token is invalid
    """
    try:
        # Decode without verification to just check expiration
        payload = jwt.decode(token, options={"verify_signature": False})
        exp_timestamp = payload.get("exp")
        if exp_timestamp:
            return datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)
        return None
    except Exception as e:
        logger.debug(f"Could not extract expiration from token: {e}")
        return None


def validate_token_signature(token: str) -> bool:
    """
    Validate only the signature of a token (not expiration).
    Useful for checking if a token was issued by this server.

    Args:
        token: JWT token string

    Returns:
        True if signature is valid, False otherwise
    """
    try:
        jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
            options={
                "verify_signature": True,
                "verify_exp": False,  # Don't verify expiration
            },
        )
        return True
    except jwt.InvalidTokenError:
        return False
    except Exception as e:
        logger.error(f"Error validating token signature: {e}")
        return False


def create_refresh_token(data: Dict[str, Any]) -> str:
    """
    Create a JWT refresh token with longer expiration.

    Args:
        data: Dictionary of claims to encode (e.g., {"sub": username, "user_id": id})

    Returns:
        Encoded JWT refresh token as a string
    """
    if JWT_SECRET_KEY == "INSECURE_DEFAULT_CHANGE_IN_PRODUCTION":
        logger.critical("JWT_SECRET_KEY is using default insecure value!")
        if config.get("ENVIRONMENT", "development") == "production":
            raise ValueError("JWT_SECRET_KEY must be set in production environment")

    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    to_encode.update(
        {
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "iss": "aac-assistant",
            "type": "refresh",  # Mark as refresh token
        }
    )

    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    logger.debug(
        f"Created refresh token for subject: {data.get('sub')}, expires: {expire}"
    )
    return encoded_jwt


def generate_secret_key() -> str:
    """
    Generate a secure random secret key for JWT signing.
    This should be run once and the result stored securely in environment variables.

    Returns:
        A secure random 256-bit (32-byte) key encoded as hex string
    """
    import secrets

    return secrets.token_hex(32)


# Warning on module import if using insecure default
if JWT_SECRET_KEY == "INSECURE_DEFAULT_CHANGE_IN_PRODUCTION":
    logger.warning(
        "=" * 80 + "\n"
        "WARNING: Using default JWT_SECRET_KEY! This is INSECURE.\n"
        "Generate a secure key with: python -c 'import secrets; print(secrets.token_hex(32))'\n"
        "Then set JWT_SECRET_KEY environment variable or add to env.properties\n"
        "=" * 80
    )
