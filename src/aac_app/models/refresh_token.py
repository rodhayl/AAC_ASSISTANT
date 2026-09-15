"""Single-use refresh-token rotation ledger (H3).

Each refresh token carries a ``jti`` (its own id) and a ``family`` id (stable
across the rotation chain started by one login). Presenting a token marks its
row consumed and mints a successor. Presenting a token that was consumed
longer than the reuse grace period ago means the credential leaked and was
replayed, which revokes the account's sessions through the existing
``User.security_version`` machinery — this table is only the rotation ledger,
not a second revocation mechanism.
"""

from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func

from .base import Base


class RefreshTokenRecord(Base):
    """One issued refresh-token id, marked consumed when it is rotated."""

    __tablename__ = "refresh_token_records"

    id = Column(Integer, primary_key=True)
    jti = Column(String(64), nullable=False, unique=True, index=True)
    family = Column(String(64), nullable=False, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    # NULL until the token is exchanged for a successor.
    consumed_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(
        DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None)
    )
    last_used_at = Column(DateTime, default=func.now())

    def __repr__(self) -> str:
        state = "consumed" if self.consumed_at else "live"
        return f"<RefreshTokenRecord(jti={self.jti}, family={self.family}, {state})>"
