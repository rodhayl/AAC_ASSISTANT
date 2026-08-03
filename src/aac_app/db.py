"""Database engine and session management.

The engine and session factory are process-level resources.  They are created
once for the configured database URL and reused by request dependencies and
background services.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager
from threading import RLock

from loguru import logger
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src import config
from src.aac_app.models import Base

_engine_instance: Engine | None = None
_session_factory: sessionmaker[Session] | None = None
_engine_url: str | None = None
_tables_initialized_url: str | None = None
_tables_initialized_engine_id: int | None = None
_resource_lock = RLock()


def get_database_path() -> str:
    """Return the configured SQLite database path, creating its directory."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    return str(config.DATABASE_PATH)


def _database_url() -> str:
    configured_url = os.environ.get("DATABASE_URL", "").strip()
    return configured_url or f"sqlite:///{get_database_path()}"


def create_engine_instance() -> Engine:
    """Return the cached process-wide SQLAlchemy engine."""
    global _engine_instance, _engine_url, _session_factory

    target_url = _database_url()
    if _engine_instance is not None and _engine_url == target_url:
        return _engine_instance

    with _resource_lock:
        if _engine_instance is not None and _engine_url == target_url:
            return _engine_instance

        if _engine_instance is not None:
            _engine_instance.dispose()

        logger.info("Creating database engine: {}", target_url)
        connect_args = {"check_same_thread": False} if target_url.startswith("sqlite") else {}
        engine_kwargs = {}
        if target_url in {"sqlite:///:memory:", "sqlite://"}:
            engine_kwargs["poolclass"] = StaticPool

        _engine_instance = create_engine(
            target_url,
            echo=False,
            connect_args=connect_args,
            **engine_kwargs,
        )
        _session_factory = sessionmaker(
            bind=_engine_instance,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
        _engine_url = target_url
        return _engine_instance


def create_session_factory() -> sessionmaker[Session]:
    """Return the cached process-wide session factory."""
    create_engine_instance()
    assert _session_factory is not None
    return _session_factory


def create_tables(engine: Engine | None = None) -> None:
    """Create any tables missing from the configured database."""
    engine = engine or create_engine_instance()
    logger.info("Creating database tables...")
    Base.metadata.create_all(engine)
    logger.info("Database tables created successfully")


def ensure_tables() -> Engine:
    """Create missing tables once for callers outside application lifespan."""
    global _tables_initialized_engine_id, _tables_initialized_url

    engine = create_engine_instance()
    key = (str(engine.url), id(engine))
    initialized_key = (_tables_initialized_url, _tables_initialized_engine_id)
    if initialized_key != key:
        with _resource_lock:
            initialized_key = (_tables_initialized_url, _tables_initialized_engine_id)
            if initialized_key != key:
                create_tables(engine)
                _tables_initialized_url, _tables_initialized_engine_id = key
    return engine


def mark_tables_initialized(engine: Engine) -> None:
    """Record that an engine has already passed the table-creation step."""
    global _tables_initialized_engine_id, _tables_initialized_url
    _tables_initialized_url = str(engine.url)
    _tables_initialized_engine_id = id(engine)


@contextmanager
def get_session() -> Generator[Session]:
    """Yield a managed database session for non-request code."""
    session = create_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
