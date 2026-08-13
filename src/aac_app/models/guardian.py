"""Guardian profile and profile history models."""

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from .base import Base


class GuardianProfile(Base):
    """Hidden Learning Companion personality configuration."""

    __tablename__ = "guardian_profiles"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    template_name = Column(String(100), default="default")
    age = Column(Integer, nullable=True)
    gender = Column(String(30), nullable=True)
    medical_context = Column(JSON, default=dict)
    communication_style = Column(JSON, default=dict)
    safety_constraints = Column(JSON, default=dict)
    companion_persona = Column(JSON, default=dict)
    custom_instructions = Column(Text, nullable=True)
    private_notes = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    user = relationship("User", foreign_keys=[user_id], backref="guardian_profile")
    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])


class GuardianProfileHistory(Base):
    """Audit history for guardian profile changes."""

    __tablename__ = "guardian_profile_history"

    id = Column(Integer, primary_key=True)
    profile_id = Column(Integer, ForeignKey("guardian_profiles.id"), nullable=False)
    field_name = Column(String(50), nullable=False)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    changed_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    changed_at = Column(DateTime, default=func.now())
    change_reason = Column(Text, nullable=True)

    profile = relationship("GuardianProfile")
    changer = relationship("User")
