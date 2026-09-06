"""
Audit logging service for security events.

Provides centralized security event logging with configurable severity levels.
Created: November 30, 2025
"""

import json
from datetime import UTC, datetime
from typing import Any

from loguru import logger
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.aac_app.models.audit_log import AuditLog

# The audit log is a write-mostly diagnostics table: no endpoint or script
# reads it, so without retention it would grow monotonically forever. A
# bounded purge runs on an existing cheap path (successful login); each pass
# deletes at most AUDIT_LOG_PURGE_BATCH of the oldest rows beyond the cap so
# the write cost per call stays small and the table converges to keeping the
# newest AUDIT_LOG_MAX_ROWS entries.
AUDIT_LOG_MAX_ROWS = 5000
AUDIT_LOG_PURGE_BATCH = 500


class AuditLogService:
    """Service for logging security events."""

    @staticmethod
    def log_event(
        db: Session,
        event_type: str,
        severity: str,
        description: str,
        user_id: int | None = None,
        username: str | None = None,
        user_type: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        endpoint: str | None = None,
        success: bool = True,
        additional_data: dict[str, Any] | None = None,
    ) -> AuditLog:
        """
        Log a security event to the audit log.

        Args:
            db: Database session
            event_type: Type of event (login_failed, password_changed, etc.)
            severity: Severity level (info, warning, critical)
            description: Human-readable description
            user_id: User ID (if applicable)
            username: Username (if applicable)
            user_type: User type (student/teacher/admin)
            ip_address: IP address of request
            user_agent: User agent string
            endpoint: API endpoint
            success: Whether the action succeeded
            additional_data: Extra context as dictionary

        Returns:
            Created AuditLog entry
        """
        # Convert additional_data to JSON string
        additional_json = None
        if additional_data:
            try:
                additional_json = json.dumps(additional_data)
            except Exception as e:
                logger.warning(f"Failed to serialize additional_data: {e}")

        # Create audit log entry
        audit_entry = AuditLog(
            timestamp=datetime.now(UTC),
            event_type=event_type,
            severity=severity,
            user_id=user_id,
            username=username,
            user_type=user_type,
            ip_address=ip_address,
            user_agent=user_agent,
            endpoint=endpoint,
            description=description,
            additional_data=additional_json,
            success=success,
        )

        # Audit entries participate in the caller's transaction. Request
        # handlers commit once through get_db; committing here could persist
        # business changes before a later operation fails and make rollback
        # semantics inconsistent.
        db.add(audit_entry)
        db.flush()
        db.refresh(audit_entry)

        # Also log to application logger for immediate visibility
        log_level = (
            "info"
            if severity == "info"
            else "warning" if severity == "warning" else "error"
        )
        getattr(logger, log_level)(
            f"AUDIT[{event_type}]: {description} | User: {username or 'N/A'} | IP: {ip_address or 'N/A'}"
        )

        return audit_entry

    @staticmethod
    def purge_old_entries(
        db: Session,
        *,
        max_rows: int = AUDIT_LOG_MAX_ROWS,
        batch_limit: int = AUDIT_LOG_PURGE_BATCH,
    ) -> int:
        """Delete the oldest audit rows beyond ``max_rows`` in bounded batches.

        Returns how many rows were deleted this call. The pass is capped by
        ``batch_limit`` so a single invocation never performs unbounded
        deletion work; repeated calls (e.g. one per successful login) converge
        to keeping only the newest ``max_rows`` entries. Rows are identified
        by ascending id, which matches insert order for this append-only
        table, so ``id <= newest_id - max_rows`` selects the oldest excess.
        """
        newest_id = db.query(func.max(AuditLog.id)).scalar()
        if newest_id is None or newest_id <= max_rows:
            return 0
        cutoff = newest_id - max_rows
        deleted = 0
        while deleted < batch_limit:
            ids = [
                row[0]
                for row in db.query(AuditLog.id)
                .filter(AuditLog.id <= cutoff)
                .order_by(AuditLog.id)
                .limit(batch_limit - deleted)
                .all()
            ]
            if not ids:
                break
            db.query(AuditLog).filter(AuditLog.id.in_(ids)).delete(
                synchronize_session=False
            )
            deleted += len(ids)
        return deleted

    @staticmethod
    def log_login_failed(
        db: Session,
        username: str,
        ip_address: str | None = None,
        reason: str = "Invalid credentials",
    ):
        """Log failed login attempt."""
        return AuditLogService.log_event(
            db=db,
            event_type="login_failed",
            severity="warning",
            description=f"Failed login attempt for user '{username}': {reason}",
            username=username,
            ip_address=ip_address,
            endpoint="/api/auth/token",
            success=False,
        )

    @staticmethod
    def log_login_success(
        db: Session,
        user_id: int,
        username: str,
        user_type: str,
        ip_address: str | None = None,
    ):
        """Log successful login."""
        return AuditLogService.log_event(
            db=db,
            event_type="login_success",
            severity="info",
            description=f"Successful login for user '{username}'",
            user_id=user_id,
            username=username,
            user_type=user_type,
            ip_address=ip_address,
            endpoint="/api/auth/token",
            success=True,
        )

    @staticmethod
    def log_password_changed(
        db: Session,
        user_id: int,
        username: str,
        changed_by_admin: bool = False,
        ip_address: str | None = None,
    ):
        """Log password change."""
        description = f"Password changed for user '{username}'"
        if changed_by_admin:
            description += " (by administrator)"

        return AuditLogService.log_event(
            db=db,
            event_type="password_changed",
            severity="info",
            description=description,
            user_id=user_id,
            username=username,
            ip_address=ip_address,
            endpoint="/api/auth/change-password",
            success=True,
        )

    @staticmethod
    def log_account_created(
        db: Session,
        new_user_id: int,
        new_username: str,
        new_user_type: str,
        created_by_id: int | None = None,
        created_by_username: str | None = None,
        ip_address: str | None = None,
    ):
        """Log account creation."""
        description = f"Account created: {new_username} (type: {new_user_type})"
        if created_by_username:
            description += f" by admin '{created_by_username}'"

        return AuditLogService.log_event(
            db=db,
            event_type="account_created",
            severity="info",
            description=description,
            user_id=created_by_id,
            username=created_by_username or "system",
            ip_address=ip_address,
            success=True,
            additional_data={
                "new_user_id": new_user_id,
                "new_username": new_username,
                "new_user_type": new_user_type,
            },
        )

    @staticmethod
    def log_admin_action(
        db: Session,
        admin_id: int,
        admin_username: str,
        action: str,
        description: str,
        ip_address: str | None = None,
        endpoint: str | None = None,
    ):
        """Log admin action."""
        return AuditLogService.log_event(
            db=db,
            event_type=f"admin_{action}",
            severity="info",
            description=f"Admin action: {description}",
            user_id=admin_id,
            username=admin_username,
            user_type="admin",
            ip_address=ip_address,
            endpoint=endpoint,
            success=True,
        )


# Global service instance
audit_service = AuditLogService()
