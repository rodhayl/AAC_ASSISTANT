"""Refresh-token rotation and replay detection (H3).

Before this service, a refresh token was a bearer credential valid until its
7-day expiry: one stolen copy could mint access tokens forever. Refresh now
rotates — every exchange consumes the presented ``jti`` and mints a successor
— and re-presenting an already-consumed ``jti`` outside a short grace window
is treated as replay and revokes the account's sessions.

Revocation deliberately reuses :func:`mark_credentials_changed` (the
``security_version`` bump every other credential path already uses) instead of
introducing a second revocation list. The grace window exists because two
in-flight refreshes of the same token are a legitimate client behaviour
(two tabs, a retried request): both must succeed rather than the second one
logging the user out.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from src.aac_app.models.refresh_token import RefreshTokenRecord

# Two requests racing on the same refresh token are indistinguishable from a
# replay if they land at the same instant, so a consumed token may be reused
# within this window (a fresh successor is minted either way).
REUSE_GRACE_SECONDS = 30


def _utcnow() -> datetime:
    """Naive UTC now, matching how timestamps are stored in SQLite."""
    return datetime.now(UTC).replace(tzinfo=None)


class RefreshRotationService:
    """Ledger of issued refresh-token ids and their consumption state."""

    @staticmethod
    def record_issued(
        db: Session,
        *,
        jti: str,
        family: str,
        user_id: int,
        expires_at: datetime,
    ) -> None:
        """Record a freshly minted refresh token as live."""
        db.add(
            RefreshTokenRecord(
                jti=jti,
                family=family,
                user_id=user_id,
                expires_at=expires_at,
                last_used_at=_utcnow(),
            )
        )

    @staticmethod
    def status(db: Session, *, jti: str, user_id: int) -> str:
        """Classify a presented ``jti`` for ``user_id``.

        Returns ``"unknown"`` (never issued — possibly a token minted before
        rotation existed, or its row aged out of the ledger), ``"live"``,
        ``"reused"`` (consumed inside the grace window: a duplicate in-flight
        exchange) or ``"replay"`` (consumed longer ago: the credential leaked
        and came back).
        """
        record = (
            db.query(RefreshTokenRecord)
            .filter(
                RefreshTokenRecord.jti == jti,
                RefreshTokenRecord.user_id == user_id,
            )
            .first()
        )
        if record is None:
            return "unknown"
        if record.consumed_at is None:
            return "live"
        consumed_at = record.consumed_at
        if consumed_at.tzinfo is not None:
            consumed_at = consumed_at.replace(tzinfo=None)
        if _utcnow() - consumed_at <= timedelta(seconds=REUSE_GRACE_SECONDS):
            return "reused"
        return "replay"

    @staticmethod
    def consume(db: Session, *, jti: str, user_id: int) -> None:
        """Mark ``jti`` consumed and prune rows past their expiry."""
        record = (
            db.query(RefreshTokenRecord)
            .filter(
                RefreshTokenRecord.jti == jti,
                RefreshTokenRecord.user_id == user_id,
            )
            .first()
        )
        if record is not None and record.consumed_at is None:
            record.consumed_at = _utcnow()

        # The ledger is bounded by the refresh-token lifetime: an expired
        # token cannot be rotated, so its row is pure disk growth.
        db.query(RefreshTokenRecord).filter(
            RefreshTokenRecord.expires_at < _utcnow()
        ).delete()

    @staticmethod
    def revoke_user(db: Session, *, user_id: int) -> int:
        """Drop every ledger row for a user (logout / replay revocation)."""
        return (
            db.query(RefreshTokenRecord)
            .filter(RefreshTokenRecord.user_id == user_id)
            .delete()
        )


refresh_rotation_service = RefreshRotationService()
