"""
Audit logging service for security events.

Provides centralized security event logging with configurable severity levels.
Created: November 30, 2025
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from loguru import logger
from sqlalchemy.orm import Session

from src.aac_app.models.audit_log import AuditLog


class AuditLogService:
    """Service for logging security events."""

    @staticmethod
    def log_event(
        db: Session,
        event_type: str,
        severity: str,
        description: str,
        user_id: Optional[int] = None,
        username: Optional[str] = None,
        user_type: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        endpoint: Optional[str] = None,
        success: bool = True,
        additional_data: Optional[Dict[str, Any]] = None,
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
            timestamp=datetime.now(timezone.utc),
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

        db.add(audit_entry)
        db.commit()
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
    def log_login_failed(
        db: Session,
        username: str,
        ip_address: Optional[str] = None,
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
        ip_address: Optional[str] = None,
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
        ip_address: Optional[str] = None,
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
    def log_privilege_escalation_attempt(
        db: Session,
        username: str,
        attempted_role: str,
        ip_address: Optional[str] = None,
    ):
        """Log privilege escalation attempt."""
        return AuditLogService.log_event(
            db=db,
            event_type="privilege_escalation",
            severity="critical",
            description=f"Privilege escalation attempt: User '{username}' tried to register as '{attempted_role}'",
            username=username,
            ip_address=ip_address,
            endpoint="/api/auth/register",
            success=False,
            additional_data={"attempted_role": attempted_role},
        )

    @staticmethod
    def log_account_created(
        db: Session,
        new_user_id: int,
        new_username: str,
        new_user_type: str,
        created_by_id: Optional[int] = None,
        created_by_username: Optional[str] = None,
        ip_address: Optional[str] = None,
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
    def log_account_deleted(
        db: Session,
        deleted_user_id: int,
        deleted_username: str,
        deleted_by_id: int,
        deleted_by_username: str,
        ip_address: Optional[str] = None,
    ):
        """Log account deletion."""
        return AuditLogService.log_event(
            db=db,
            event_type="account_deleted",
            severity="warning",
            description=f"Account deleted: {deleted_username} (by admin '{deleted_by_username}')",
            user_id=deleted_by_id,
            username=deleted_by_username,
            ip_address=ip_address,
            success=True,
            additional_data={
                "deleted_user_id": deleted_user_id,
                "deleted_username": deleted_username,
            },
        )

    @staticmethod
    def log_admin_action(
        db: Session,
        admin_id: int,
        admin_username: str,
        action: str,
        description: str,
        ip_address: Optional[str] = None,
        endpoint: Optional[str] = None,
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
