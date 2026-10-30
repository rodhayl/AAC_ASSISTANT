"""
Account lockout service for failed login protection.

Implements 5-attempt lockout with 15-minute cooldown.
Created: November 30, 2025
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from loguru import logger
from sqlalchemy.orm import Session

from src.aac_app.models.audit_log import FailedLoginAttempt


class AccountLockoutService:
    """Service for managing account lockout after failed logins."""

    # Configuration
    MAX_ATTEMPTS = 5
    LOCKOUT_DURATION_MINUTES = 15
    ATTEMPT_WINDOW_MINUTES = 60  # Count attempts within last hour

    @staticmethod
    def record_failed_attempt(
        db: Session, username: str, ip_address: Optional[str] = None
    ) -> Tuple[bool, Optional[datetime], int]:
        """
        Record a failed login attempt.

        Args:
            db: Database session
            username: Username that failed login
            ip_address: IP address of attempt

        Returns:
            Tuple of (is_locked, locked_until, attempt_count)
        """
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(
            minutes=AccountLockoutService.ATTEMPT_WINDOW_MINUTES
        )

        # Get recent attempt record
        recent_attempt = (
            db.query(FailedLoginAttempt)
            .filter(
                FailedLoginAttempt.username == username,
                FailedLoginAttempt.timestamp >= window_start,
            )
            .first()
        )

        if recent_attempt:
            # Check if already locked
            if recent_attempt.locked_until and recent_attempt.locked_until > now:
                # Still locked
                logger.warning(
                    f"Failed login attempt for locked account '{username}' "
                    f"from IP {ip_address}. Locked until {recent_attempt.locked_until}"
                )
                return True, recent_attempt.locked_until, recent_attempt.attempt_count

            # Increment attempt count
            recent_attempt.attempt_count += 1
            recent_attempt.timestamp = now

            if ip_address:
                recent_attempt.ip_address = ip_address

            # Check if should lock
            if recent_attempt.attempt_count >= AccountLockoutService.MAX_ATTEMPTS:
                lockout_until = now + timedelta(
                    minutes=AccountLockoutService.LOCKOUT_DURATION_MINUTES
                )
                recent_attempt.locked_until = lockout_until

                logger.warning(
                    f"Account '{username}' locked after {recent_attempt.attempt_count} failed attempts. "
                    f"Locked until {lockout_until}"
                )

                db.commit()
                return True, lockout_until, recent_attempt.attempt_count

            db.commit()
            return False, None, recent_attempt.attempt_count
        else:
            # First failed attempt
            new_attempt = FailedLoginAttempt(
                username=username,
                ip_address=ip_address,
                timestamp=now,
                attempt_count=1,
                locked_until=None,
            )
            db.add(new_attempt)
            db.commit()

            logger.info(
                f"Recorded first failed login attempt for '{username}' from IP {ip_address}"
            )
            return False, None, 1

    @staticmethod
    def is_locked(db: Session, username: str) -> Tuple[bool, Optional[datetime]]:
        """
        Check if account is currently locked.

        Args:
            db: Database session
            username: Username to check

        Returns:
            Tuple of (is_locked, locked_until)
        """
        now = datetime.now(timezone.utc)

        # Get most recent attempt record
        attempt = (
            db.query(FailedLoginAttempt)
            .filter(FailedLoginAttempt.username == username)
            .order_by(FailedLoginAttempt.timestamp.desc())
            .first()
        )

        if not attempt:
            return False, None

        if attempt.locked_until:
            # Ensure attempt.locked_until is timezone-aware
            locked_until = attempt.locked_until
            if locked_until.tzinfo is None:
                locked_until = locked_until.replace(tzinfo=timezone.utc)

            if locked_until > now:
                return True, locked_until

        return False, None

    @staticmethod
    def reset_attempts(db: Session, username: str):
        """
        Reset failed attempt count after successful login.

        Args:
            db: Database session
            username: Username to reset
        """
        # Delete all failed attempt records for this user
        db.query(FailedLoginAttempt).filter(
            FailedLoginAttempt.username == username
        ).delete()
        db.commit()

        logger.info(
            f"Reset failed login attempts for '{username}' after successful login"
        )

    @staticmethod
    def unlock_account(db: Session, username: str, admin_username: str):
        """
        Manually unlock an account (admin action).

        Args:
            db: Database session
            username: Username to unlock
            admin_username: Admin performing unlock
        """
        # Delete all failed attempt records
        deleted_count = (
            db.query(FailedLoginAttempt)
            .filter(FailedLoginAttempt.username == username)
            .delete()
        )
        db.commit()

        logger.info(
            f"Admin '{admin_username}' manually unlocked account '{username}' "
            f"({deleted_count} attempt records removed)"
        )

        return deleted_count > 0


# Global service instance
lockout_service = AccountLockoutService()
