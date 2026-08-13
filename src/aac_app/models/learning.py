"""Learning sessions, modes, plans, and progress models."""

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from .base import Base


class LearningSession(Base):
    """AI tutoring session."""

    __tablename__ = "learning_sessions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    topic_name = Column(String(100), nullable=False)
    purpose = Column(Text)
    # Learning mode key (e.g. "practice", "regression_mode"); the mode's
    # prompt_instruction is appended to the LLM system prompt for this session.
    mode_key = Column(String(50), nullable=True)
    status = Column(String(20), default="active")
    comprehension_score = Column(Float, default=0.0)
    questions_asked = Column(Integer, default=0)
    questions_answered = Column(Integer, default=0)
    correct_answers = Column(Integer, default=0)
    conversation_history = Column(JSON, default=list)
    started_at = Column(DateTime, default=func.now())
    ended_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="learning_sessions")


class LearningMode(Base):
    """Learning Companion interaction mode."""

    __tablename__ = "learning_modes"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    key = Column(String(50), nullable=False)
    description = Column(Text)
    prompt_instruction = Column(Text)
    is_custom = Column(Boolean, default=True)
    # When False, sessions using this mode skip auto-asking questions;
    # teachers can still request a question manually.
    auto_ask_enabled = Column(Boolean, default=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    creator = relationship("User")


class LearningPlan(Base):
    """Structured learning plan."""

    __tablename__ = "learning_plans"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    difficulty = Column(String(20), default="beginner")
    status = Column(String(20), default="active")
    target_completion = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    user = relationship("User")
    tasks = relationship("LearningTask", back_populates="plan")


class LearningTask(Base):
    """Individual task within a learning plan."""

    __tablename__ = "learning_tasks"

    id = Column(Integer, primary_key=True)
    plan_id = Column(Integer, ForeignKey("learning_plans.id"), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    task_type = Column(String(50), default="practice")
    status = Column(String(20), default="pending")
    priority = Column(Integer, default=1)
    estimated_duration = Column(Integer, default=30)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())

    plan = relationship("LearningPlan", back_populates="tasks")


class UserProgress(Base):
    """Track user learning progress."""

    __tablename__ = "user_progress"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    metric_type = Column(String(50), nullable=False)
    metric_value = Column(Float, nullable=False)
    recorded_at = Column(DateTime, default=func.now())

    user = relationship("User")
