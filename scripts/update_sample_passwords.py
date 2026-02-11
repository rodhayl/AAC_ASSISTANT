"""
Update sample users with non-hardcoded strong passwords.

This script updates passwords for sample users (student1, teacher1, admin1).
Passwords are read from these optional environment variables:
- AAC_SEED_STUDENT1_PASSWORD
- AAC_SEED_TEACHER1_PASSWORD
- AAC_SEED_ADMIN1_PASSWORD
If a variable is missing, a random password is generated.
"""

import os
import secrets
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.aac_app.models.database import User, get_session  # noqa: E402
from src.aac_app.services.auth_service import get_password_hash  # noqa: E402


def _resolve_password(username: str) -> str:
    env_value = os.environ.get(f"AAC_SEED_{username.upper()}_PASSWORD", "").strip()
    if env_value:
        return env_value
    return secrets.token_urlsafe(14)


def update_sample_passwords():
    """Update sample user passwords without hardcoded defaults."""
    password_updates = {
        "student1": _resolve_password("student1"),
        "teacher1": _resolve_password("teacher1"),
        "admin1": _resolve_password("admin1"),
    }

    with get_session() as db:
        updated = 0
        for username, new_password in password_updates.items():
            user = db.query(User).filter(User.username == username).first()
            if user:
                user.password_hash = get_password_hash(new_password)
                print(f"Updated password for {username}")
                updated += 1
            else:
                print(f"User {username} not found")

        db.commit()
        print(f"\nUpdated {updated} user passwords")
        print("\nUpdated credentials (store them securely):")
        for username, password in password_updates.items():
            print(f"  {username} / {password}")


if __name__ == "__main__":
    if "--force" not in sys.argv:
        print("This script will reset passwords for sample users.")
        print("Run with --force to execute.")
        sys.exit(1)

    print("Updating sample user passwords...\n")
    update_sample_passwords()
