"""SQLAlchemy models grouped by domain.

Importing this package registers every model on :data:`Base.metadata`, while
re-exporting the classes keeps model imports stable for callers.
"""

from .achievement import Achievement, UserAchievement
from .analytics import SymbolUsageLog
from .audit_log import AuditLog, FailedLoginAttempt
from .base import Base
from .board import BoardAssignment, BoardSymbol, CommunicationBoard
from .collaboration import CollaborationSession
from .content_safety import ContentSafetyEvent
from .guardian import GuardianProfile, GuardianProfileHistory
from .learning import (
    LearningMode,
    LearningPlan,
    LearningSession,
    LearningTask,
    UserProgress,
)
from .notification import Notification
from .settings import AppSettings
from .symbol import Symbol
from .user import StudentTeacher, User, UserSettings

__all__ = [
    "Achievement",
    "AppSettings",
    "AuditLog",
    "Base",
    "BoardAssignment",
    "BoardSymbol",
    "CollaborationSession",
    "CommunicationBoard",
    "ContentSafetyEvent",
    "FailedLoginAttempt",
    "GuardianProfile",
    "GuardianProfileHistory",
    "LearningMode",
    "LearningPlan",
    "LearningSession",
    "LearningTask",
    "Notification",
    "StudentTeacher",
    "Symbol",
    "SymbolUsageLog",
    "User",
    "UserAchievement",
    "UserProgress",
    "UserSettings",
]
