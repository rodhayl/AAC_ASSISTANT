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
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

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
        # SQLite: a generous busy timeout plus WAL mode prevent write-lock
        # contention from stalling concurrent requests (desktop app and E2E).
        connect_args = (
            {"check_same_thread": False, "timeout": 30}
            if target_url.startswith("sqlite")
            else {}
        )
        engine_kwargs = {}
        if target_url in {"sqlite:///:memory:", "sqlite://"}:
            engine_kwargs["poolclass"] = StaticPool
        elif os.environ.get("TESTING") == "1" and target_url.startswith("sqlite"):
            # Tests use temporary file-backed SQLite. Avoid retaining pooled
            # DBAPI connections across fixture/client teardown; production
            # keeps the normal pool for lower connection overhead.
            engine_kwargs["poolclass"] = NullPool

        _engine_instance = create_engine(
            target_url,
            echo=False,
            connect_args=connect_args,
            **engine_kwargs,
        )

        if target_url.startswith("sqlite"):

            @event.listens_for(_engine_instance, "connect")
            def _configure_sqlite(dbapi_connection, _connection_record):
                cursor = dbapi_connection.cursor()
                try:
                    cursor.execute("PRAGMA foreign_keys=ON")
                    cursor.execute("PRAGMA journal_mode=WAL")
                    cursor.execute("PRAGMA synchronous=NORMAL")
                    cursor.execute("PRAGMA busy_timeout=30000")
                    # Keep the page cache bounded for low-memory desktops.
                    # Leave temp_store at SQLite's default so large sorts do not
                    # unexpectedly consume all available RAM.
                    cursor.execute("PRAGMA cache_size=-2000")
                finally:
                    cursor.close()

        _session_factory = sessionmaker(
            bind=_engine_instance,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
        _engine_url = target_url
        return _engine_instance


def dispose_engine_instance() -> None:
    """Dispose and clear the cached engine and session factory.

    This is primarily useful for test isolation and controlled application
    reconfiguration. The next database access creates a fresh engine for the
    current ``DATABASE_URL``.
    """
    global _engine_instance, _session_factory, _engine_url
    global _tables_initialized_url, _tables_initialized_engine_id

    with _resource_lock:
        if _engine_instance is not None:
            _engine_instance.dispose()
        _engine_instance = None
        _session_factory = None
        _engine_url = None
        _tables_initialized_url = None
        _tables_initialized_engine_id = None


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


@contextmanager
def session_scope(db: Session | None, session_factory=None) -> Generator[Session]:
    """Use a caller-owned session or safely manage a new service session.

    Request handlers pass their transaction-owned session through this helper;
    background/service callers get the same commit, rollback, and close
    behavior as :func:`get_session`.  Keeping this policy in one place avoids
    subtly different session lifecycles across services.
    """
    if db is not None:
        yield db
        return
    with (session_factory or get_session)() as session:
        yield session
