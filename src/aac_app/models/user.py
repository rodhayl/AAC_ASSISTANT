"""User accounts, preferences, and teacher/student relationships."""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

from .base import Base


class User(Base):
    """User model for authentication and profiles."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(100), unique=True, nullable=True)
    password_hash = Column(String(255), nullable=False)
    # Incremented whenever credentials are replaced so issued sessions can be revoked.
    security_version = Column(Integer, nullable=False, default=1, server_default="1")
    # Used to revoke legacy tokens that predate security-version claims.
    credentials_changed_at = Column(DateTime, nullable=True)
    display_name = Column(String(100), nullable=False)
    user_type = Column(String(20), default="student")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    learning_sessions = relationship("LearningSession", back_populates="user")
    achievements = relationship("UserAchievement", back_populates="user")
    communication_boards = relationship("CommunicationBoard", back_populates="user")
    settings = relationship("UserSettings", back_populates="user", uselist=False)


class UserSettings(Base):
    """User-specific settings and preferences."""

    __tablename__ = "user_settings"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    tts_provider = Column(String(20), default="kokoro", server_default="kokoro")
    tts_voice = Column(String(20), default="default")
    tts_local_voice = Column(String(40), default="default", server_default="default")
    tts_language = Column(String(10), default="en")
    ui_language = Column(String(10), default="es-ES")
    notifications_enabled = Column(Boolean, default=True)
    voice_mode_enabled = Column(Boolean, default=True)
    dark_mode = Column(Boolean, default=False)
    dwell_time = Column(Integer, default=0)
    ignore_repeats = Column(Integer, default=0)
    high_contrast = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="settings")


class StudentTeacher(Base):
    """Association between students and teachers."""

    __tablename__ = "student_teachers"

    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    teacher_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=func.now())

    student = relationship("User", foreign_keys=[student_id], backref="teachers")
    teacher = relationship("User", foreign_keys=[teacher_id], backref="students")
