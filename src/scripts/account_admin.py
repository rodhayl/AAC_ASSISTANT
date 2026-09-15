"""Consolidated local account administration commands.

Examples:
    python -m src.scripts.account_admin check
    python -m src.scripts.account_admin reset --username admin1 --password 'NewPass123'
    python -m src.scripts.account_admin reset --username admin1 --password '123' --force
    python -m src.scripts.account_admin unlock --username teacher1

The password is read from AAC_ADMIN_RESET_PASSWORD or an interactive prompt;
``--password`` still works but warns because argv leaks the secret into the
process table and shell history.

Reset also clears failed-login lockout rows so the new password can be used
immediately, and warns when the account is deactivated.

Reset enforces the same password-strength policy as the API routes: a weak
password is refused with a clear message unless ``--force`` is passed (for
emergency recovery only).
"""

from __future__ import annotations

import argparse
import os
import sys
from getpass import getpass

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
    # A reset must actually restore access.  Leaving failed-login rows in
    # place answers the next login with "account locked" even though the new
    # password is correct (the API reset path clears them for the same
    # reason); an inactive account stays disabled, so say so explicitly
    # instead of letting the operator believe the account works again.
    lockout_service.reset_attempts(session, username)
    session.commit()
    if not user.is_active:
        print(
            f"Warning: {username!r} is deactivated; the password is reset but "
            "logins remain rejected until the account is reactivated."
        )
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
    """Resolve the new password, preferring sources that keep it off argv.

    ``--password`` lands in the process table and shell history, so it is the
    last resort and warns when used; the environment variable and an
    interactive prompt (stdin) are preferred.
    """
    if value:
        print(
            "Warning: --password exposes the secret in the process table and "
            "shell history; prefer AAC_ADMIN_RESET_PASSWORD or the interactive "
            "prompt."
        )
        return value.strip()
    password = os.environ.get("AAC_ADMIN_RESET_PASSWORD", "").strip()
    if password:
        return password
    if sys.stdin is not None and sys.stdin.isatty():
        password = getpass("New password: ").strip()
        if password:
            return password
    raise SystemExit(
        "Provide the new password via AAC_ADMIN_RESET_PASSWORD, the interactive "
        "prompt, or (last resort, insecure) --password <new_password>."
    )


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
