"""Communication boards, placements, and assignments."""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from .base import Base


class CommunicationBoard(Base):
    """AAC communication board."""

    __tablename__ = "communication_boards"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    category = Column(String(50), default="general")
    is_public = Column(Boolean, default=False)
    is_template = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    grid_rows = Column(Integer, default=4)
    grid_cols = Column(Integer, default=5)
    locale = Column(String(10), default="en")
    is_language_learning = Column(Boolean, default=False)
    ai_enabled = Column(Boolean, default=False)
    ai_provider = Column(String(50), nullable=True)
    ai_model = Column(String(100), nullable=True)

    user = relationship("User", back_populates="communication_boards")
    symbols = relationship(
        "BoardSymbol",
        back_populates="board",
        foreign_keys="[BoardSymbol.board_id]",
    )


class BoardSymbol(Base):
    """Many-to-many relationship between boards and symbols."""

    __tablename__ = "board_symbols"

    id = Column(Integer, primary_key=True)
    board_id = Column(Integer, ForeignKey("communication_boards.id"), nullable=False)
    symbol_id = Column(Integer, ForeignKey("symbols.id"), nullable=False)
    position_x = Column(Integer, default=0)
    position_y = Column(Integer, default=0)
    size = Column(Integer, default=1)
    is_visible = Column(Boolean, default=True)
    custom_text = Column(String(100))
    linked_board_id = Column(Integer, ForeignKey("communication_boards.id"), nullable=True)
    color = Column(String(20), nullable=True)
    order_index = Column(Integer, default=0)

    board = relationship(
        "CommunicationBoard",
        foreign_keys=[board_id],
        back_populates="symbols",
    )
    symbol = relationship("Symbol", back_populates="board_symbols")
    linked_board = relationship("CommunicationBoard", foreign_keys=[linked_board_id])


class BoardAssignment(Base):
    """Board assigned to a student."""

    __tablename__ = "board_assignments"

    id = Column(Integer, primary_key=True)
    board_id = Column(Integer, ForeignKey("communication_boards.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    assigned_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=func.now())
