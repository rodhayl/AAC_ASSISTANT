"""Global application settings model."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func

from .base import Base


class AppSettings(Base):
    """Global application settings managed by administrators."""

    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True)
    setting_key = Column(String(50), unique=True, nullable=False)
    setting_value = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
