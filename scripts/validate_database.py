"""
Pre-startup Database Validation Script.

This script validates the database before starting the application.
It checks for common issues and provides helpful error messages.

Add this to start.bat to catch issues early.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def validate_user_passwords() -> bool:
    """Ensure all users have password hashes."""
    from src.aac_app.models.database import User, get_session

    print("Validating user passwords...")

    with get_session() as session:
        users_without_passwords = (
            session.query(User).filter(User.password_hash == None).all()  # noqa: E711
        )

        if users_without_passwords:
            print(f"\n[ERROR] Found {len(users_without_passwords)} users without passwords:")
            for user in users_without_passwords:
                print(f"  - {user.username} (ID: {user.id})")
            print("\nFix: Run 'python scripts/fix_null_passwords.py' to repair invalid users.")
            return False

        print("[OK] All users have password hashes")
        return True


def validate_default_users() -> bool:
    """Warn if sample default users are missing."""
    from src.aac_app.models.database import User, get_session

    print("Validating default users...")
    expected_users = ["student1", "teacher1", "admin1"]

    with get_session() as session:
        for username in expected_users:
            user = session.query(User).filter(User.username == username).first()
            if not user:
                print(f"[WARN] Default user '{username}' not found")
            elif not user.password_hash:
                print(f"[ERROR] Default user '{username}' has no password hash")
                return False
            else:
                print(f"[OK] Default user '{username}'")

        return True


def validate_database_schema() -> bool:
    """Validate that core DB schema exists."""
    from sqlalchemy import inspect

    from src.aac_app.models.database import create_engine_instance

    print("Validating database schema...")

    try:
        engine = create_engine_instance()
        inspector = inspect(engine)

        if "users" not in inspector.get_table_names():
            print("[ERROR] 'users' table not found")
            print(
                "Fix: Run 'python -c \"from src.aac_app.models.database import init_database; init_database()\"'"
            )
            return False

        columns = {col["name"]: col for col in inspector.get_columns("users")}
        if "password_hash" not in columns:
            print("[ERROR] 'password_hash' column not found in users table")
            return False

        password_hash_col = columns["password_hash"]
        if password_hash_col.get("nullable", True):
            print("[WARN] 'password_hash' is nullable; stricter schema is recommended")

        print("[OK] Database schema")
        return True
    except Exception as exc:
        print(f"[ERROR] Exception while validating schema: {exc}")
        return False


def main() -> int:
    """Run all validation checks."""
    print("=" * 60)
    print("Database Pre-Startup Validation")
    print("=" * 60)
    print()

    checks = [
        ("Database Schema", validate_database_schema),
        ("User Passwords", validate_user_passwords),
        ("Default Users", validate_default_users),
    ]

    failed_checks: list[str] = []

    for check_name, check_func in checks:
        print(f"\n[{check_name}]")
        try:
            if not check_func():
                failed_checks.append(check_name)
        except Exception as exc:
            print(f"[ERROR] {exc}")
            failed_checks.append(check_name)

    print("\n" + "=" * 60)

    if failed_checks:
        print("[ERROR] VALIDATION FAILED")
        print(f"Failed checks: {', '.join(failed_checks)}")
        print("The application may not work correctly until these issues are fixed.")
        return 1

    print("[OK] ALL VALIDATION CHECKS PASSED")
    print("Database is ready for use.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

