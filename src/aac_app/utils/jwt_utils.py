"""
JWT token utilities for secure authentication.

Provides JWT token creation, validation, and secret key management.
Uses HS256 algorithm for signing with a secret key from environment.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from loguru import logger

from src import config

# JWT Configuration
# Load from .env via the shared configuration module (environment variables take precedence)
_INSECURE_DEFAULT_SECRET = "INSECURE_DEFAULT_CHANGE_IN_PRODUCTION"
JWT_SECRET_KEY = config.get("JWT_SECRET_KEY", _INSECURE_DEFAULT_SECRET)
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 120  # 2 hours
REFRESH_TOKEN_EXPIRE_DAYS = 7  # 7 days

# Enforce secure secret in production
if (
    config.get("ENVIRONMENT", "development") == "production"
    and JWT_SECRET_KEY == _INSECURE_DEFAULT_SECRET
):
    raise ValueError(
        "CRITICAL SECURITY ERROR: JWT_SECRET_KEY must be set to a secure value in production. "
        "Generate one with: python -c 'import secrets; print(secrets.token_hex(32))'"
    )


def _require_secure_secret() -> None:
    """Refuse to mint tokens with the placeholder secret in production."""
    if JWT_SECRET_KEY != _INSECURE_DEFAULT_SECRET:
        return
    logger.critical(
        "JWT_SECRET_KEY is using default insecure value! Set JWT_SECRET_KEY environment variable."
    )
    # In production, this should raise an error. For development, we'll log a warning.
    if config.get("ENVIRONMENT", "development") == "production":
        raise ValueError("JWT_SECRET_KEY must be set in production environment")


def _encode_token(
    data: dict[str, Any], *, token_type: str, expire: datetime
) -> str:
    """Encode a signed JWT with the standard claims and a type marker."""
    to_encode = data.copy()
    to_encode.update(
        {
            "exp": expire,
            "iat": datetime.now(UTC),
            "iss": "aac-assistant",  # Issuer claim
            "type": token_type,
        }
    )
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_access_token(
    data: dict[str, Any], expires_delta: timedelta | None = None
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
    _require_secure_secret()

    # Set expiration time
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        )

    encoded_jwt = _encode_token(data, token_type="access", expire=expire)

    logger.debug(f"Created JWT token for subject: {data.get('sub')}, expires: {expire}")
    return encoded_jwt


def _decode_token(
    token: str, *, expected_type: str | None, verify_exp: bool = True
) -> dict[str, Any] | None:
    """Decode a signed token and optionally enforce its token type.

    ``verify_exp=False`` still verifies the signature, issuer, type, and
    required claims; it only ignores an expired ``exp``. Callers use this
    exclusively for best-effort flows such as logout, where an expired access
    token must still identify its account so the refresh token can be revoked.
    """
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
            options={
                "verify_signature": True,
                "verify_exp": verify_exp,
                "verify_iat": True,
                "require": ["exp", "iat", "sub"],
            },
        )

        if payload.get("iss") != "aac-assistant":
            logger.warning(f"Invalid token issuer: {payload.get('iss')}")
            return None

        token_type = payload.get("type")
        if expected_type == "refresh":
            if token_type != "refresh":
                logger.warning("Token type mismatch: expected refresh token")
                return None
        elif expected_type == "access" and token_type not in (None, "access"):
            # Reject non-access tokens as bearer credentials. Tokens without a
            # type remain valid for backwards compatibility with already-issued
            # access tokens from before token types were added.
            logger.warning("Non-access token cannot be used as an access token")
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


def decode_access_token(
    token: str, *, verify_exp: bool = True
) -> dict[str, Any] | None:
    """Decode and validate an access token, rejecting other token types.

    Pass ``verify_exp=False`` for best-effort flows (e.g. logout) that must
    still identify the account of an expired token.
    """
    return _decode_token(token, expected_type="access", verify_exp=verify_exp)


def decode_refresh_token(token: str) -> dict[str, Any] | None:
    """Decode and validate a refresh token."""
    return _decode_token(token, expected_type="refresh")


def create_refresh_token(data: dict[str, Any]) -> str:
    """
    Create a JWT refresh token with longer expiration.

    Args:
        data: Dictionary of claims to encode (e.g., {"sub": username, "user_id": id})

    Returns:
        Encoded JWT refresh token as a string
    """
    _require_secure_secret()

    expire = datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    encoded_jwt = _encode_token(data, token_type="refresh", expire=expire)
    logger.debug(
        f"Created refresh token for subject: {data.get('sub')}, expires: {expire}"
    )
    return encoded_jwt


# Warning on module import if using insecure default
if JWT_SECRET_KEY == _INSECURE_DEFAULT_SECRET:
    logger.warning(
        "=" * 80 + "\n"
        "WARNING: Using default JWT_SECRET_KEY! This is INSECURE.\n"
        "Generate a secure key with: python -c 'import secrets; print(secrets.token_hex(32))'\n"
        "Then set JWT_SECRET_KEY environment variable or add to .env\n"
        "=" * 80
    )
