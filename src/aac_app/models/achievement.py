"""Achievement definitions and user-earned achievements."""

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from .base import Base


class Achievement(Base):
    """Achievement definition."""

    __tablename__ = "achievements"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    icon = Column(String(50))
    category = Column(String(50), default="general")
    points = Column(Integer, default=10)
    criteria_type = Column(String(50))
    criteria_value = Column(Float)
    is_active = Column(Boolean, default=True)
    is_manual = Column(Boolean, default=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    target_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=func.now())

    user_achievements = relationship(
        "UserAchievement",
        back_populates="achievement",
        foreign_keys="UserAchievement.achievement_id",
    )
    creator = relationship("User", foreign_keys=[created_by])
    target_user = relationship("User", foreign_keys=[target_user_id])


class UserAchievement(Base):
    """Achievement earned by a user."""

    __tablename__ = "user_achievements"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    achievement_id = Column(Integer, ForeignKey("achievements.id"), nullable=False)
    earned_at = Column(DateTime, default=func.now())
    progress = Column(Float, default=1.0)

    user = relationship("User", back_populates="achievements")
    achievement = relationship("Achievement", back_populates="user_achievements")
