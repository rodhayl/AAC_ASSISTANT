"""Real-time collaboration session model."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func

from .base import Base


class CollaborationSession(Base):
    """Collaboration session for real-time communication."""

    __tablename__ = "collaboration_sessions"

    id = Column(Integer, primary_key=True)
    session_name = Column(String(100), nullable=False)
    host_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String(20), default="waiting")
    session_code = Column(String(20), unique=True, nullable=False)
    max_participants = Column(Integer, default=5)
    created_at = Column(DateTime, default=func.now())
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
