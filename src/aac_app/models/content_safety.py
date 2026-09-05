"""Content-safety audit events.

Every time layered content protection blocks or redirects student-facing
content (chat input/output, topic words, pictogram labels, board AI, collab
payloads), one row records what happened and where. Teachers see events for
their roster students; admins can list aggregates.
"""

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text, func

from .base import Base


class ContentSafetyEvent(Base):
    """One blocked/redirected content-safety verdict for a student surface."""

    __tablename__ = "content_safety_events"

    id = Column(Integer, primary_key=True)
    # The student whose session produced the content. Null for server-wide
    # gates (e.g. autogen blocking a label with no student context).
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    # surface: chat | topic | words | pictogram | board | social
    surface = Column(String(30), nullable=False)
    # direction: input (student content) | output (generated content)
    direction = Column(String(10), nullable=False, default="output")
    # verdict: blocked | redirected | flagged
    verdict = Column(String(20), nullable=False, default="blocked")
    # matched families/terms (normalized text snippets)
    matched = Column(JSON, default=list)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now(), index=True)
