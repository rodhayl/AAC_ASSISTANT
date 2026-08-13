"""AAC symbol library models."""

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, func
from sqlalchemy.orm import relationship

from .base import Base


class Symbol(Base):
    """AAC symbols and pictograms."""

    __tablename__ = "symbols"

    id = Column(Integer, primary_key=True)
    label = Column(String(100), nullable=False)
    description = Column(Text)
    category = Column(String(50), default="general")
    image_path = Column(String(255))
    audio_path = Column(String(255))
    keywords = Column(Text)
    language = Column(String(10), default="en")
    is_builtin = Column(Boolean, default=False)
    order_index = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())

    board_symbols = relationship("BoardSymbol", back_populates="symbol")
