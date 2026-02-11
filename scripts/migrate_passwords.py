"""
Password migration utility for AAC Assistant.

This script migrates user password hashes from legacy SHA-256 to bcrypt.
Because hashes are one-way, affected users are assigned one temporary
password that must be rotated immediately after migration.
"""

import argparse
import os
import re
import sys
from pathlib import Path

import bcrypt
from loguru import logger

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.aac_app.models.database import User, get_session

TEMP_PASSWORD_ENV = "AAC_MIGRATION_TEMP_PASSWORD"


def _password_is_strong(password: str) -> bool:
    return bool(
        len(password) >= 12
        and re.search(r"[A-Z]", password)
        and re.search(r"[a-z]", password)
        and re.search(r"\d", password)
        and re.search(r"[^A-Za-z0-9]", password)
    )


def _resolve_temp_password(cli_temp_password: str | None) -> str:
    temp_password = (cli_temp_password or os.getenv(TEMP_PASSWORD_ENV, "")).strip()
    if not temp_password:
        raise ValueError(
            "Temporary password is required via --temp-password or "
            f"{TEMP_PASSWORD_ENV}."
        )
    if not _password_is_strong(temp_password):
        raise ValueError(
            "Temporary password must be at least 12 chars and include upper, lower, "
            "digit, and special characters."
        )
    return temp_password


def migrate_passwords(temp_password: str, skip_confirmation: bool = False) -> None:
    """
    Migrate users that still store SHA-256 hashes to bcrypt.
    """
    logger.info("=" * 80)
    logger.info("PASSWORD MIGRATION SCRIPT")
    logger.info("=" * 80)
    logger.warning("This operation resets all SHA-256 user hashes to one temp password.")
    logger.warning("The temporary password value is intentionally not logged.")
    logger.info("=" * 80)

    if not skip_confirmation:
        response = input("Do you want to continue? (yes/no): ").strip().lower()
        if response != "yes":
            logger.info("Migration cancelled by user.")
            return

    logger.info("Starting password migration...")

    try:
        with get_session() as db:
            users = db.query(User).all()

            if not users:
                logger.warning("No users found in database.")
                return

            logger.info(f"Found {len(users)} users to evaluate")
            salt = bcrypt.gensalt()
            new_hash = bcrypt.hashpw(temp_password.encode("utf-8"), salt).decode("utf-8")

            migrated_count = 0
            for user in users:
                old_hash = user.password_hash
                is_sha256 = len(old_hash) == 64 and all(
                    c in "0123456789abcdef" for c in old_hash.lower()
                )

                if is_sha256:
                    user.password_hash = new_hash
                    logger.info(
                        f"Migrated user: {user.username} (id={user.id}, type={user.user_type})"
                    )
                    migrated_count += 1
                else:
                    logger.info(
                        f"Skipped user: {user.username} (already bcrypt or unknown format)"
                    )

            db.commit()

            logger.info("=" * 80)
            logger.info("Migration complete.")
            logger.info(f"Total users: {len(users)}")
            logger.info(f"Migrated: {migrated_count}")
            logger.info(f"Skipped: {len(users) - migrated_count}")
            logger.warning("Temporary passwords must be changed after first login.")
            logger.info("=" * 80)
    except Exception as exc:
        logger.error(f"Migration failed: {exc}")
        logger.exception(exc)
        sys.exit(1)


def verify_migration() -> None:
    """
    Verify password hash formats after migration.
    """
    logger.info("Verifying migration...")

    try:
        with get_session() as db:
            users = db.query(User).all()

            bcrypt_count = 0
            sha256_count = 0
            other_count = 0

            for user in users:
                hash_value = user.password_hash
                if hash_value.startswith(("$2a$", "$2b$", "$2y$")):
                    bcrypt_count += 1
                elif len(hash_value) == 64 and all(
                    c in "0123456789abcdef" for c in hash_value.lower()
                ):
                    sha256_count += 1
                    logger.warning(f"{user.username}: SHA-256 format (not migrated)")
                else:
                    other_count += 1
                    logger.warning(f"{user.username}: unknown hash format")

            logger.info("=" * 80)
            logger.info("VERIFICATION RESULTS")
            logger.info(f"Bcrypt hashes: {bcrypt_count}")
            logger.info(f"SHA-256 hashes: {sha256_count}")
            logger.info(f"Other formats: {other_count}")
            if sha256_count == 0:
                logger.info("All users are on bcrypt.")
            else:
                logger.warning(f"{sha256_count} users are still on SHA-256.")
            logger.info("=" * 80)
    except Exception as exc:
        logger.error(f"Verification failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Migrate user passwords from SHA-256 to bcrypt"
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify migration status without changing user records",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip interactive confirmation prompt",
    )
    parser.add_argument(
        "--temp-password",
        help=(
            "Temporary password to assign during migration. "
            f"If omitted, uses {TEMP_PASSWORD_ENV}."
        ),
    )
    args = parser.parse_args()

    if args.verify_only:
        verify_migration()
    else:
        try:
            temporary_password = _resolve_temp_password(args.temp_password)
        except ValueError as exc:
            logger.error(str(exc))
            sys.exit(2)
        migrate_passwords(temporary_password, skip_confirmation=args.yes)
        verify_migration()
