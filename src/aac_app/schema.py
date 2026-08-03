"""Runtime schema creation and idempotent SQLite upgrades.

SQLite is the application's migration strategy.  ``ensure`` first creates
missing tables from the ORM metadata, then applies additive column upgrades
needed by databases created by older releases.
"""

from __future__ import annotations

from loguru import logger
from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.aac_app.db import create_engine_instance, create_tables, mark_tables_initialized


def _ensure_sqlite_columns(engine: Engine) -> None:
    """Apply additive column upgrades to an existing SQLite database."""
    if engine.dialect.name != "sqlite":
        return

    with engine.begin() as connection:
        def table_exists(table: str) -> bool:
            row = connection.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name=:table"),
                {"table": table},
            ).fetchone()
            return row is not None

        def has_column(table: str, column: str) -> bool:
            rows = connection.execute(text(f"PRAGMA table_info({table})")).fetchall()
            return any(row[1] == column for row in rows)

        columns = (
            ("symbols", "order_index", "INTEGER DEFAULT 0"),
            ("board_symbols", "order_index", "INTEGER DEFAULT 0"),
            ("user_settings", "ui_language", "TEXT DEFAULT 'es-ES'"),
            ("user_settings", "voice_mode_enabled", "INTEGER DEFAULT 1"),
            ("user_settings", "dwell_time", "INTEGER DEFAULT 0"),
            ("user_settings", "ignore_repeats", "INTEGER DEFAULT 0"),
            ("user_settings", "high_contrast", "INTEGER DEFAULT 0"),
        )
        for table, column, definition in columns:
            if table_exists(table) and not has_column(table, column):
                logger.info("DB upgrade: adding {}.{}", table, column)
                connection.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
                )

        if table_exists("learning_modes") and not has_column("learning_modes", "updated_at"):
            logger.info("DB upgrade: adding learning_modes.updated_at")
            connection.execute(text("ALTER TABLE learning_modes ADD COLUMN updated_at DATETIME"))
            connection.execute(
                text(
                    "UPDATE learning_modes SET updated_at = created_at "
                    "WHERE updated_at IS NULL"
                )
            )


def ensure(engine: Engine | None = None) -> Engine:
    """Create the current schema and apply all known legacy upgrades.

    The operation is safe to call repeatedly.  It is intentionally explicit
    rather than hidden in engine construction so application startup has one
    clear schema-management step.
    """
    engine = engine or create_engine_instance()
    create_tables(engine)
    _ensure_sqlite_columns(engine)
    mark_tables_initialized(engine)
    return engine


# Kept as a small compatibility name for code that used the old private helper
# while the actual implementation now lives in this module.
_ensure_sqlite_schema = _ensure_sqlite_columns
