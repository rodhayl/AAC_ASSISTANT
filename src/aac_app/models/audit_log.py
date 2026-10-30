"""
Audit logging model for security events.

Tracks all security-relevant events for forensics and compliance.
Created: November 30, 2025
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

# Import Base from database module
from src.aac_app.models.database import Base


class AuditLog(Base):
    """
    Audit log for security events.

    Tracks:
    - Failed login attempts
    - Password changes
    - Privilege escalation attempts
    - Account creation/deletion
    - Admin actions
    """

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    # Event details
    event_type = Column(
        String(50), nullable=False, index=True
    )  # login_failed, password_changed, etc.
    severity = Column(String(20), nullable=False, index=True)  # info, warning, critical

    # User information
    user_id = Column(
        Integer, nullable=True, index=True
    )  # May be null for failed logins
    username = Column(String(100), nullable=True, index=True)
    user_type = Column(String(20), nullable=True)

    # Request information
    ip_address = Column(String(45), nullable=True, index=True)  # IPv6 max length
    user_agent = Column(String(500), nullable=True)
    endpoint = Column(String(200), nullable=True)

    # Event details
    description = Column(Text, nullable=False)
    additional_data = Column(Text, nullable=True)  # JSON string for extra context

    # Success/failure
    success = Column(Boolean, default=True, nullable=False)

    def __repr__(self):
        return f"<AuditLog(id={self.id}, type={self.event_type}, user={self.username}, time={self.timestamp})>"


class FailedLoginAttempt(Base):
    """
    Track failed login attempts for account lockout.

    Implements 5-attempt lockout with 15-minute cooldown.
    """

    __tablename__ = "failed_login_attempts"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), nullable=False, index=True)
    ip_address = Column(String(45), nullable=True, index=True)
    timestamp = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    # Lockout tracking
    attempt_count = Column(Integer, default=1, nullable=False)
    locked_until = Column(DateTime(timezone=True), nullable=True, index=True)

    def __repr__(self):
        return (
            f"<FailedLoginAttempt(username={self.username}, "
            f"attempts={self.attempt_count}, locked={self.locked_until})>"
        )
