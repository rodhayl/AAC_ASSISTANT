"""Credential state helpers used by password mutation paths."""

from datetime import UTC, datetime

from src.aac_app.models import User


def mark_credentials_changed(user: User) -> None:
    """Revoke issued sessions after replacing a user's password."""
    user.security_version = (user.security_version or 1) + 1
    user.credentials_changed_at = datetime.now(UTC).replace(tzinfo=None)
