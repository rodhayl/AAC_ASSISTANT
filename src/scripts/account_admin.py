"""Consolidated local account administration commands.

Examples:
    python -m src.scripts.account_admin check
    python -m src.scripts.account_admin reset --username admin1 --password 'NewPass123'
    python -m src.scripts.account_admin reset --username admin1 --password '123' --force
    python -m src.scripts.account_admin unlock --username teacher1

The password may also be supplied through AAC_ADMIN_RESET_PASSWORD for reset.

Reset enforces the same password-strength policy as the API routes: a weak
password is refused with a clear message unless ``--force`` is passed (for
emergency recovery only).
"""

from __future__ import annotations

import argparse
import os

from sqlalchemy.orm import Session

from src.aac_app.db import get_session
from src.aac_app.models import User
from src.aac_app.services.auth_service import get_password_hash, password_strength_error
from src.aac_app.services.credential_service import mark_credentials_changed
from src.aac_app.services.lockout_service import lockout_service


def reset_password(
    session: Session,
    username: str,
    new_password: str,
    *,
    force: bool = False,
) -> bool:
    """Reset a user's password and report whether the reset happened.

    Returns ``False`` when the user does not exist, or when the new password
    fails the shared strength policy (length/upper/lower/digit) and ``force``
    is not set. ``force`` is the explicit emergency-recovery override: the
    weak password is still hashed and applied.
    """
    user = session.query(User).filter(User.username == username).first()
    if not user:
        return False
    error = password_strength_error(new_password)
    if error and not force:
        print(
            f"Refusing to set a weak password for {username!r}: {error}. "
            "Pass --force to override for emergency recovery."
        )
        return False
    user.password_hash = get_password_hash(new_password)
    mark_credentials_changed(user)
    session.commit()
    return True


def clear_lockout(session: Session, username: str) -> None:
    """Clear failed-login attempts for a username."""
    lockout_service.reset_attempts(session, username)


def check_account(session: Session, username: str) -> bool:
    """Print account information and return whether the account exists."""
    user = session.query(User).filter(User.username == username).first()
    if not user:
        print(f"User {username!r} not found.")
        return False
    print(f"Found user: {user.username}, type: {user.user_type}, active: {user.is_active}")
    return True


def _password(value: str | None) -> str:
    password = (value or os.environ.get("AAC_ADMIN_RESET_PASSWORD", "")).strip()
    if not password:
        raise SystemExit(
            "Provide --password <new_password> or set AAC_ADMIN_RESET_PASSWORD."
        )
    return password


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check", help="show whether an account exists")
    check.add_argument("--username", default="admin1")

    reset = subparsers.add_parser("reset", help="replace an account password")
    reset.add_argument("--username", default="admin1")
    reset.add_argument("--password")
    reset.add_argument(
        "--force",
        action="store_true",
        help="apply a weak password anyway (emergency recovery only)",
    )

    unlock = subparsers.add_parser("unlock", help="clear failed-login lockout attempts")
    unlock.add_argument("--username", default="admin1")

    args = parser.parse_args()
    with get_session() as session:
        if args.command == "check":
            return 0 if check_account(session, args.username) else 1
        if args.command == "reset":
            if not reset_password(
                session,
                args.username,
                _password(args.password),
                force=args.force,
            ):
                print(
                    f"Password for {args.username!r} was NOT reset "
                    "(user not found, or password too weak without --force)."
                )
                return 1
            print(f"Password for {args.username!r} was reset.")
            return 0
        clear_lockout(session, args.username)
        print(f"Lockout cleared for {args.username!r}.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
