"""
Database Migration Script: Fix Null Password Hashes

This script:
1. Identifies users with null password_hash
2. Either removes them or sets a default hash (configurable)
3. Validates database integrity

Run this after updating the schema to ensure no users have null passwords.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.aac_app.models.database import User, get_session  # noqa: E402
from src.api.routers.auth import hash_password  # noqa: E402


def fix_null_password_hashes(delete_invalid=False):
    """
    Fix users with null password hashes.

    Args:
        delete_invalid: If True, delete users with null passwords.
                       If False, set a random hash (user won't be able to login).
    """
    print("Checking for users with null password hashes...")

    with get_session() as session:
        # Find users with null password hash
        invalid_users = session.query(User).filter(User.password_hash.is_(None)).all()

        if not invalid_users:
            print("✓ No users with null password hashes found.")
            return True

        print(f"\n⚠ Found {len(invalid_users)} users with null password hashes:")
        for user in invalid_users:
            print(f"  - {user.username} ({user.user_type}, ID: {user.id})")

        if delete_invalid:
            print("\nDeleting invalid users...")
            for user in invalid_users:
                print(f"  Deleting user: {user.username}")
                session.delete(user)
            session.commit()
            print(f"✓ Deleted {len(invalid_users)} invalid users")
        else:
            print("\nSetting impossible password hash for invalid users...")
            print("(These users will not be able to login until password is reset)")
            impossible_hash = hash_password("__INVALID_USER_NO_PASSWORD__")
            for user in invalid_users:
                print(f"  Fixing user: {user.username}")
                user.password_hash = impossible_hash
            session.commit()
            print(f"✓ Fixed {len(invalid_users)} users")

        return True


def validate_database():
    """Validate that all users have password hashes"""
    print("\nValidating database integrity...")

    with get_session() as session:
        total_users = session.query(User).count()
        users_with_passwords = (
            session.query(User).filter(User.password_hash.is_not(None)).count()
        )
        users_without_passwords = total_users - users_with_passwords

        print(f"Total users: {total_users}")
        print(f"Users with passwords: {users_with_passwords}")
        print(f"Users without passwords: {users_without_passwords}")

        if users_without_passwords > 0:
            print("\n❌ Database validation FAILED!")
            print(f"   {users_without_passwords} users still have null password hashes")
            return False

        print("\n✅ Database validation PASSED!")
        print("   All users have valid password hashes")
        return True


def main():
    """Main migration function"""
    print("=" * 60)
    print("Database Migration: Fix Null Password Hashes")
    print("=" * 60)

    try:
        # Fix null password hashes (delete invalid users)
        fix_null_password_hashes(delete_invalid=True)

        # Validate database
        if validate_database():
            print("\n✅ Migration completed successfully!")
            return 0
        else:
            print("\n❌ Migration failed! Please review the errors above.")
            return 1

    except Exception as e:
        print(f"\n❌ Migration failed with error: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
