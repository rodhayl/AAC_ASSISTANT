import pytest
from fastapi import HTTPException

from src.api.routers.auth_helpers import (
    validate_email_format,
    validate_password_strength,
)


@pytest.mark.parametrize(
    ("password", "message"),
    [
        ("", "Password is required"),
        ("short", "Password must be at least 8 characters long"),
        ("lowercase1", "Password must contain at least one uppercase letter"),
        ("UPPERCASE1", "Password must contain at least one lowercase letter"),
        ("NoDigitsHere", "Password must contain at least one number"),
    ],
)
def test_validate_password_strength_preserves_error_contract(password, message):
    with pytest.raises(HTTPException) as error:
        validate_password_strength(password)
    assert error.value.status_code == 400
    assert error.value.detail == message


def test_validate_password_strength_accepts_strong_password():
    validate_password_strength("StrongPass123")


@pytest.mark.parametrize("email", ["not-an-email", "name@example", "name @example.com"])
def test_validate_email_format_rejects_invalid_values(email):
    with pytest.raises(HTTPException, match="Invalid email format"):
        validate_email_format(email)


def test_validate_email_format_allows_optional_and_valid_values():
    validate_email_format(None)
    validate_email_format("")
    validate_email_format("name@example.com")
