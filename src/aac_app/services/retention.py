"""Explicit, safe retention helpers for disposable application data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from src import config
from src.aac_app.models import LearningSession, Symbol
from src.api.file_uploads import remove_owned_upload


@dataclass(frozen=True)
class RetentionReport:
    """Counts and paths considered by a retention operation."""

    candidates: int
    removed: int


def cleanup_orphaned_symbol_uploads(
    db: Session,
    *,
    uploads_dir: Path | None = None,
    dry_run: bool = True,
) -> RetentionReport:
    """Find symbol files no longer referenced by the database.

    The default is a dry run. Only files under the configured symbol-upload
    directory are considered, and no database rows are modified.
    """
    root = (uploads_dir or config.UPLOADS_DIR / "symbols").resolve()
    referenced = {
        Path(symbol.image_path.removeprefix("/uploads/")).name
        for symbol in db.query(Symbol.image_path).filter(Symbol.image_path.is_not(None))
        if symbol[0] and symbol[0].startswith("/uploads/symbols/")
    }
    candidates = [path for path in root.glob("*") if path.is_file() and path.name not in referenced]
    if dry_run:
        return RetentionReport(candidates=len(candidates), removed=0)
    for path in candidates:
        remove_owned_upload(f"/uploads/symbols/{path.name}", root)
    return RetentionReport(candidates=len(candidates), removed=len(candidates))


def prune_completed_learning_sessions(
    db: Session,
    *,
    older_than_days: int,
    dry_run: bool = True,
) -> RetentionReport:
    """Count or delete completed sessions older than a caller-selected age.

    This never touches active sessions and defaults to dry-run so operators must
    explicitly opt into destructive retention behavior.
    """
    cutoff = datetime.now() - timedelta(days=max(0, older_than_days))
    query = db.query(LearningSession).filter(
        LearningSession.status == "completed",
        LearningSession.ended_at.is_not(None),
        LearningSession.ended_at < cutoff,
    )
    candidates = query.count()
    if dry_run or candidates == 0:
        return RetentionReport(candidates=candidates, removed=0)
    query.delete(synchronize_session=False)
    db.commit()
    return RetentionReport(candidates=candidates, removed=candidates)
