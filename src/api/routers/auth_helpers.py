"""Reusable helpers for authentication routes."""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from fastapi import HTTPException
from slowapi import Limiter
from slowapi.util import get_remote_address

_F = TypeVar("_F", bound=Callable[..., Any])
_limiter_instance = Limiter(key_func=get_remote_address)


def conditional_limiter(rate: str) -> Callable[[_F], _F]:
    """Apply rate limiting in production while keeping tests deterministic."""

    def decorator(func: _F) -> _F:
        limited_func = _limiter_instance.limit(rate)(func)

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if os.getenv("TESTING", "0") == "1":
                return func(*args, **kwargs)
            return limited_func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


_EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


def validate_email_format(email: str | None) -> None:
    """Reject a non-empty email that does not match the API's email contract."""
    if email and not _EMAIL_PATTERN.match(email):
        raise HTTPException(status_code=400, detail="Invalid email format")


def validate_password_strength(password: str) -> None:
    """Require a non-empty password with length and character diversity."""
    if not password or len(password.strip()) == 0:
        raise HTTPException(status_code=400, detail="Password is required")
    if len(password) < 8:
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 8 characters long",
        )
    requirements = (
        (r"[A-Z]", "Password must contain at least one uppercase letter"),
        (r"[a-z]", "Password must contain at least one lowercase letter"),
        (r"[0-9]", "Password must contain at least one number"),
    )
    for pattern, message in requirements:
        if not re.search(pattern, password):
            raise HTTPException(status_code=400, detail=message)
