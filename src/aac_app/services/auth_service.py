"""Password hashing and verification helpers for authentication."""

import bcrypt
from loguru import logger
from pwdlib import PasswordHash
from pwdlib.exceptions import PwdlibError, UnknownHashError

_PASSWORD_HASHER = PasswordHash.recommended()
_BCRYPT_PREFIXES = ("$2a$", "$2b$", "$2y$")


def get_password_hash(password: str) -> str:
    """
    Hash a password using the recommended Argon2 configuration.

    Args:
        password: Plain text password to hash

    Returns:
        Argon2 hash string (includes salt and algorithm parameters)
    """
    if not password:
        raise ValueError("Password cannot be empty")

    return _PASSWORD_HASHER.hash(password)


def _is_legacy_bcrypt_hash(password_hash: str) -> bool:
    return password_hash.startswith(_BCRYPT_PREFIXES)


def verify_password_and_update(
    plain_password: str, hashed_password: str
) -> tuple[bool, str | None]:
    """
    Verify a password and return a replacement hash for legacy bcrypt.

    Argon2 hashes are verified and rehashed according to pwdlib's current
    configuration. Existing bcrypt hashes are verified through bcrypt only for
    migration compatibility and are replaced with Argon2 after a successful
    verification.
    """
    try:
        return _PASSWORD_HASHER.verify_and_update(plain_password, hashed_password)
    except UnknownHashError:
        if not _is_legacy_bcrypt_hash(hashed_password):
            logger.warning("Password verification failed: unrecognized hash format")
            return False, None

        try:
            is_valid = bcrypt.checkpw(
                plain_password.encode("utf-8"), hashed_password.encode("utf-8")
            )
        except (TypeError, ValueError) as error:
            logger.warning(f"Password verification failed: {error}")
            return False, None

        return is_valid, get_password_hash(plain_password) if is_valid else None
    except PwdlibError as error:
        logger.warning(f"Password verification failed: {error}")
        return False, None


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain password against an Argon2 or legacy bcrypt hash.

    Args:
        plain_password: Plain text password to verify
        hashed_password: Bcrypt hash to verify against

    Returns:
        True if password matches, False otherwise
    """
    try:
        is_valid, _ = verify_password_and_update(plain_password, hashed_password)
        return is_valid
    except (TypeError, ValueError) as error:
        logger.warning(f"Password verification failed: {error}")
        return False
