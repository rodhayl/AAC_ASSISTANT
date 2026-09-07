"""
Account lockout service for failed login protection.

Implements 5-attempt lockout with 15-minute cooldown.
Created: November 30, 2025
"""

from datetime import UTC, datetime, timedelta

from loguru import logger
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.aac_app.models.audit_log import FailedLoginAttempt

# The failed-login table is a write-mostly security table: nothing reads it
# except the per-username lockout lookup, so without retention it would grow
# monotonically forever under a flood of DISTINCT usernames (each within-
# window username mints its own row; the per-IP limiter does not help across
# IPs). Mirror the audit-log cap: on each failed attempt the oldest rows
# beyond the cap are deleted in one bounded batch, so the table converges to
# keeping the newest LOCKOUT_MAX_ROWS entries.
LOCKOUT_MAX_ROWS = 5000
LOCKOUT_PURGE_BATCH = 500


class AccountLockoutService:
    """Service for managing account lockout after failed logins."""

    # Configuration
    MAX_ATTEMPTS = 5
    LOCKOUT_DURATION_MINUTES = 15
    ATTEMPT_WINDOW_MINUTES = 60  # Count attempts within last hour

    @staticmethod
    def _purge_expired_attempts(db: Session, now: datetime) -> None:
        """Delete attempt rows that can no longer influence lockout.

        ``record_failed_attempt`` counts only rows inside the attempt window,
        and a row's lock always expires before its timestamp leaves that
        window (LOCKOUT_DURATION < ATTEMPT_WINDOW). Rows older than the
        window are therefore pure disk growth — failed logins are an
        unauthenticated endpoint, so without this purge the table grows
        without bound.
        """
        window_start = now - timedelta(
            minutes=AccountLockoutService.ATTEMPT_WINDOW_MINUTES
        )
        db.query(FailedLoginAttempt).filter(
            FailedLoginAttempt.timestamp < window_start
        ).delete()

    @staticmethod
    def _trim_to_cap(db: Session) -> None:
        """Delete the oldest rows beyond LOCKOUT_MAX_ROWS in one bounded batch.

        Called after the expiry purge on the failed-attempt path so a flood of
        distinct usernames (the only growth mode: increments reuse a row,
        first-attempt inserts add one) cannot outgrow the cap. Rows are
        ordered by ascending (timestamp, id) — the same insertion order the
        per-username lookups use — so the NEWEST rows (including the attempt
        just recorded) always survive.
        """
        total = db.query(func.count(FailedLoginAttempt.id)).scalar() or 0
        if total <= LOCKOUT_MAX_ROWS:
            return
        excess = min(total - LOCKOUT_MAX_ROWS, LOCKOUT_PURGE_BATCH)
        if excess <= 0:
            return
        ids = [
            row[0]
            for row in db.query(FailedLoginAttempt.id)
            .order_by(
                FailedLoginAttempt.timestamp.asc(), FailedLoginAttempt.id.asc()
            )
            .limit(excess)
            .all()
        ]
        if ids:
            db.query(FailedLoginAttempt).filter(
                FailedLoginAttempt.id.in_(ids)
            ).delete(synchronize_session=False)

    @staticmethod
    def record_failed_attempt(
        db: Session, username: str, ip_address: str | None = None
    ) -> tuple[bool, datetime | None, int]:
        """
        Record a failed login attempt.

        Args:
            db: Database session
            username: Username that failed login
            ip_address: IP address of attempt

        Returns:
            Tuple of (is_locked, locked_until, attempt_count)
        """
        now = datetime.now(UTC)
        AccountLockoutService._purge_expired_attempts(db, now)
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
            .order_by(FailedLoginAttempt.timestamp.desc(), FailedLoginAttempt.id.desc())
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

                db.flush()
                is_locked, locked_until, attempt_count = True, lockout_until, recent_attempt.attempt_count
            else:
                db.flush()
                is_locked, locked_until, attempt_count = False, None, recent_attempt.attempt_count
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
            db.flush()
            is_locked, locked_until, attempt_count = False, None, 1

            logger.info(
                f"Recorded first failed login attempt for '{username}' from IP {ip_address}"
            )

        # The mutation above grew the table by exactly one row (increment or
        # insert): trim it back to the cap once, AFTER the mutation. Trimming
        # before the lookup as well would pay a second COUNT/DELETE per failed
        # attempt for zero benefit — the flood case grows the table only via
        # this insert/increment. The still-locked early return above performs
        # no mutation and correctly skips the trim.
        AccountLockoutService._trim_to_cap(db)
        return is_locked, locked_until, attempt_count

    @staticmethod
    def is_locked(db: Session, username: str) -> tuple[bool, datetime | None]:
        """
        Check if account is currently locked.

        Args:
            db: Database session
            username: Username to check

        Returns:
            Tuple of (is_locked, locked_until)
        """
        now = datetime.now(UTC)

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
                locked_until = locked_until.replace(tzinfo=UTC)

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
        db.flush()

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
        db.flush()

        logger.info(
            f"Admin '{admin_username}' manually unlocked account '{username}' "
            f"({deleted_count} attempt records removed)"
        )

        return deleted_count > 0


# Global service instance
lockout_service = AccountLockoutService()
