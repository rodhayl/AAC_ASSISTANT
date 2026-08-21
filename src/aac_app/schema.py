"""Runtime schema creation and idempotent SQLite upgrades.

SQLite is the application's migration strategy.  ``ensure`` first creates
missing tables from the ORM metadata, then applies additive column upgrades
needed by databases created by older releases.
"""

from __future__ import annotations

from loguru import logger
from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.aac_app.db import create_engine_instance, create_tables


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

        # ``create_all`` only creates missing tables; it deliberately does not
        # alter tables from an older installation. Keep every additive column
        # introduced after the original schema here, including nullable/default
        # fields whose absence would otherwise make ORM queries fail at runtime.
        # SQLite permits these safe additive changes without rebuilding tables.
        columns = (
            ("users", "security_version", "INTEGER NOT NULL DEFAULT 1"),
            ("users", "credentials_changed_at", "DATETIME"),
            ("symbols", "order_index", "INTEGER DEFAULT 0"),
            ("board_symbols", "order_index", "INTEGER DEFAULT 0"),
            ("board_symbols", "linked_board_id", "INTEGER"),
            ("board_symbols", "color", "VARCHAR(20)"),
            ("communication_boards", "grid_rows", "INTEGER DEFAULT 4"),
            ("communication_boards", "grid_cols", "INTEGER DEFAULT 5"),
            ("communication_boards", "locale", "VARCHAR(10) DEFAULT 'en'"),
            ("communication_boards", "is_language_learning", "BOOLEAN DEFAULT 0"),
            ("communication_boards", "ai_enabled", "BOOLEAN DEFAULT 0"),
            ("communication_boards", "ai_provider", "VARCHAR(50)"),
            ("communication_boards", "ai_model", "VARCHAR(100)"),
            ("user_settings", "tts_provider", "TEXT DEFAULT 'kokoro'"),
            ("user_settings", "tts_voice", "TEXT DEFAULT 'default'"),
            ("user_settings", "tts_local_voice", "TEXT DEFAULT 'default'"),
            ("user_settings", "tts_language", "TEXT DEFAULT 'en'"),
            ("user_settings", "ui_language", "TEXT DEFAULT 'es-ES'"),
            ("user_settings", "notifications_enabled", "BOOLEAN DEFAULT 1"),
            ("user_settings", "voice_mode_enabled", "BOOLEAN DEFAULT 1"),
            ("user_settings", "dark_mode", "BOOLEAN DEFAULT 0"),
            ("user_settings", "dwell_time", "INTEGER DEFAULT 0"),
            ("user_settings", "ignore_repeats", "INTEGER DEFAULT 0"),
            ("user_settings", "high_contrast", "BOOLEAN DEFAULT 0"),
            ("achievements", "criteria_type", "VARCHAR(50)"),
            ("achievements", "criteria_value", "FLOAT"),
            ("achievements", "is_manual", "BOOLEAN DEFAULT 0"),
            ("achievements", "created_by", "INTEGER"),
            ("achievements", "target_user_id", "INTEGER"),
            ("symbol_usage_logs", "session_id", "INTEGER"),
            ("symbol_usage_logs", "symbol_id", "INTEGER"),
            ("symbol_usage_logs", "symbol_category", "VARCHAR(50)"),
            ("symbol_usage_logs", "semantic_intent", "VARCHAR(20)"),
            ("symbol_usage_logs", "context_topic", "VARCHAR(100)"),
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

        if table_exists("learning_sessions") and not has_column("learning_sessions", "mode_key"):
            logger.info("DB upgrade: adding learning_sessions.mode_key")
            connection.execute(text("ALTER TABLE learning_sessions ADD COLUMN mode_key VARCHAR(50)"))

        if table_exists("learning_modes") and not has_column(
            "learning_modes", "auto_ask_enabled"
        ):
            logger.info("DB upgrade: adding learning_modes.auto_ask_enabled")
            connection.execute(
                text("ALTER TABLE learning_modes ADD COLUMN auto_ask_enabled BOOLEAN DEFAULT 1")
            )


def _ensure_sqlite_indexes(engine: Engine) -> None:
    """Create indexes for confirmed ownership, join, and history queries.

    Index creation is additive and idempotent so it is safe for existing
    SQLite databases and for repeated application startup.
    """
    if engine.dialect.name != "sqlite":
        return

    indexes = (
        ("ix_communication_boards_user_public", "communication_boards", "user_id, is_public"),
        (
            "ix_board_symbols_board_position",
            "board_symbols",
            "board_id, position_y, position_x",
        ),
        ("ix_board_symbols_symbol_id", "board_symbols", "symbol_id"),
        (
            "ix_board_assignments_student_board",
            "board_assignments",
            "student_id, board_id",
        ),
        (
            "ix_symbol_usage_logs_user_timestamp",
            "symbol_usage_logs",
            "user_id, timestamp",
        ),
        (
            "ix_symbol_usage_logs_user_session_position",
            "symbol_usage_logs",
            "user_id, session_id, position_in_utterance",
        ),
        (
            "ix_symbol_usage_logs_user_symbol_label",
            "symbol_usage_logs",
            "user_id, symbol_label",
        ),
        ("ix_learning_sessions_user_started", "learning_sessions", "user_id, started_at"),
        (
            "ix_learning_sessions_user_status_started",
            "learning_sessions",
            "user_id, status, started_at",
        ),
        (
            "ix_learning_sessions_status_ended",
            "learning_sessions",
            "status, ended_at",
        ),
        (
            "ix_notifications_user_read_created",
            "notifications",
            "user_id, is_read, created_at",
        ),
        ("ix_notifications_user_created", "notifications", "user_id, created_at"),
        ("ix_learning_modes_key", "learning_modes", "key"),
        (
            "ix_user_achievements_user_achievement",
            "user_achievements",
            "user_id, achievement_id",
        ),
        ("ix_user_progress_user_metric", "user_progress", "user_id, metric_type, id"),
        (
            "ix_student_teachers_teacher_student",
            "student_teachers",
            "teacher_id, student_id",
        ),
        (
            "ix_student_teachers_student_teacher",
            "student_teachers",
            "student_id, teacher_id",
        ),
    )

    with engine.begin() as connection:
        existing_tables = {
            row[0]
            for row in connection.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )
        }
        for index_name, table_name, columns in indexes:
            if table_name not in existing_tables:
                continue
            available_columns = {
                row[1]
                for row in connection.execute(text(f"PRAGMA table_info({table_name})"))
            }
            requested_columns = {column.strip() for column in columns.split(",")}
            if not requested_columns <= available_columns:
                logger.warning(
                    "Skipping index {} because {} is missing columns {}",
                    index_name,
                    table_name,
                    sorted(requested_columns - available_columns),
                )
                continue
            connection.execute(
                text(
                    f"CREATE INDEX IF NOT EXISTS {index_name} "
                    f"ON {table_name} ({columns})"
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
    _ensure_sqlite_indexes(engine)
    return engine
