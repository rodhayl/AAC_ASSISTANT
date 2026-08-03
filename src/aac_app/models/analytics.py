"""Symbol analytics and usage history model."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

from .base import Base


class SymbolUsageLog(Base):
    """Track symbol usage for analytics and personalization."""

    __tablename__ = "symbol_usage_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_id = Column(Integer, ForeignKey("learning_sessions.id"), nullable=True)
    symbol_id = Column(Integer, ForeignKey("symbols.id"), nullable=True)
    symbol_label = Column(String(50), nullable=False)
    symbol_category = Column(String(50), nullable=True)
    position_in_utterance = Column(Integer, nullable=False)
    utterance_length = Column(Integer, nullable=False)
    semantic_intent = Column(String(20), nullable=True)
    timestamp = Column(DateTime, default=func.now(), nullable=False)
    context_topic = Column(String(100), nullable=True)

    user = relationship("User")
    session = relationship("LearningSession")
    symbol = relationship("Symbol")
