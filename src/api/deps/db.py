"""Database session dependency for request handlers."""

from collections.abc import Generator

from sqlalchemy.orm import Session

from src.aac_app.db import create_session_factory


def get_db() -> Generator[Session]:
    """Yield one managed database session for a request."""
    db = create_session_factory()()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
