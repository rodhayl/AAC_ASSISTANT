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
            ("user_settings", "tts_local_speed", "REAL DEFAULT 1.0"),
            ("user_settings", "tts_language", "TEXT DEFAULT 'en'"),
            ("user_settings", "ui_language", "TEXT DEFAULT 'es-ES'"),
            ("user_settings", "notifications_enabled", "BOOLEAN DEFAULT 1"),
            ("user_settings", "voice_mode_enabled", "BOOLEAN DEFAULT 1"),
            ("user_settings", "dark_mode", "BOOLEAN DEFAULT 0"),
            ("user_settings", "dwell_time", "INTEGER DEFAULT 0"),
            ("user_settings", "ignore_repeats", "INTEGER DEFAULT 0"),
            ("user_settings", "high_contrast", "BOOLEAN DEFAULT 0"),
            ("user_settings", "hover_speak_enabled", "BOOLEAN DEFAULT 0"),
            ("user_settings", "hover_speak_delay_ms", "INTEGER DEFAULT 1000"),
            ("user_settings", "default_learning_mode", "VARCHAR(50) DEFAULT 'practice'"),
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
            ("learning_sessions", "board_id", "INTEGER"),
            ("saved_topics", "board_id", "INTEGER"),
            ("saved_topics", "created_by_user_id", "INTEGER"),
        )
        for table, column, definition in columns:
            if table_exists(table) and not has_column(table, column):
                logger.info("DB upgrade: adding {}.{}", table, column)
                connection.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
                )

        if table_exists("saved_topics") and has_column("saved_topics", "created_by_user_id"):
            connection.execute(
                text(
                    "UPDATE saved_topics SET created_by_user_id = user_id "
                    "WHERE created_by_user_id IS NULL"
                )
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
        ("ix_saved_topics_user_created", "saved_topics", "user_id, created_at"),
        ("ix_saved_topics_board", "saved_topics", "board_id"),
        ("ix_saved_topics_creator", "saved_topics", "created_by_user_id"),
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

        if "board_assignments" in existing_tables:
            assignment_columns = {
                row[1]
                for row in connection.execute(
                    text("PRAGMA table_info(board_assignments)")
                )
            }
            if {"id", "board_id", "student_id"} <= assignment_columns:
                # Older databases allowed duplicate assignments because the
                # ORM uniqueness rule was introduced after the table existed.
                # Keep the earliest row (and its audit metadata), then enforce
                # the invariant at the database boundary for concurrent writes.
                connection.execute(
                    text(
                        "DELETE FROM board_assignments "
                        "WHERE id NOT IN ("
                        "SELECT MIN(id) FROM board_assignments "
                        "GROUP BY board_id, student_id"
                        ")"
                    )
                )
                connection.execute(
                    text(
                        "CREATE UNIQUE INDEX IF NOT EXISTS "
                        "uq_board_assignments_board_student "
                        "ON board_assignments (board_id, student_id)"
                    )
                )


def _ensure_foreign_key_actions(engine: Engine) -> None:
    """Rebuild tables whose FK constraints lack ON DELETE actions.

    Older releases created ``board_symbols`` and ``symbol_usage_logs`` without
    ``ON DELETE CASCADE`` / ``ON DELETE SET NULL`` on ``symbol_id``, so deleting
    a symbol would fail with a FOREIGN KEY constraint error.  SQLite does not
    support ``ALTER TABLE ADD CONSTRAINT``, so this migration rebuilds the
    affected tables with the correct FK actions and performs a one-time
    cleanup of corrupted / duplicate symbols that accumulated under the old
    schema.
    """
    if engine.dialect.name != "sqlite":
        return

    with engine.begin() as connection:
        # Drop stale temp tables from a previous failed/interrupted migration.
        connection.execute(text("DROP TABLE IF EXISTS _board_symbols_new"))
        connection.execute(text("DROP TABLE IF EXISTS _symbol_usage_logs_new"))

        def table_exists(table: str) -> bool:
            row = connection.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name=:t"),
                {"t": table},
            ).fetchone()
            return row is not None

        def _fk_on_delete(table: str, col: str, ref_table: str) -> str | None:
            """Return the ON DELETE action for FK from *col* → *ref_table*.id."""
            rows = connection.execute(
                text(f"PRAGMA foreign_key_list({table})")
            ).fetchall()
            # PRAGMA foreign_key_list returns:
            #   0=id, 1=seq, 2=table, 3=from, 4=to, 5=on_update, 6=on_delete, 7=match
            for row in rows:
                if row[3] == col and row[2] == ref_table:
                    return row[6]  # on_delete
            return None

        # ── board_symbols: symbol_id → symbols.id needs ON DELETE CASCADE ──
        if table_exists("board_symbols") and _fk_on_delete(
            "board_symbols", "symbol_id", "symbols"
        ) != "CASCADE":
            # Only rebuild if the legacy table has the minimum required columns.
            _bs_cols = {
                r[1]
                for r in connection.execute(
                    text("PRAGMA table_info(board_symbols)")
                ).fetchall()
            }
            if {"id", "board_id", "symbol_id"} <= _bs_cols:
                logger.info(
                    "Migration: rebuilding board_symbols with ON DELETE CASCADE"
                )
                connection.execute(
                    text(
                        "CREATE TABLE _board_symbols_new ("
                        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
                        "  board_id INTEGER NOT NULL REFERENCES communication_boards(id),"
                        "  symbol_id INTEGER NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,"
                        "  position_x INTEGER DEFAULT 0,"
                        "  position_y INTEGER DEFAULT 0,"
                        "  size INTEGER DEFAULT 1,"
                        "  is_visible BOOLEAN DEFAULT 1,"
                        "  custom_text VARCHAR(100),"
                        "  linked_board_id INTEGER REFERENCES communication_boards(id),"
                        "  color VARCHAR(20),"
                        "  order_index INTEGER DEFAULT 0"
                        ")"
                    )
                )
                _bs_mapping = [
                    ("id", "id"),
                    ("board_id", "board_id"),
                    ("symbol_id", "symbol_id"),
                    ("position_x", "0"),
                    ("position_y", "0"),
                    ("size", "1"),
                    ("is_visible", "1"),
                    ("custom_text", "NULL"),
                    ("linked_board_id", "NULL"),
                    ("color", "NULL"),
                    ("order_index", "0"),
                ]
                _bs_sel = ", ".join(
                    c if c in _bs_cols else f for c, f in _bs_mapping
                )
                connection.execute(
                    text(f"INSERT INTO _board_symbols_new SELECT {_bs_sel} FROM board_symbols")
                )
                connection.execute(text("DROP TABLE board_symbols"))
                connection.execute(text("ALTER TABLE _board_symbols_new RENAME TO board_symbols"))

        # ── symbol_usage_logs: symbol_id → symbols.id needs ON DELETE SET NULL ──
        if table_exists("symbol_usage_logs") and _fk_on_delete(
            "symbol_usage_logs", "symbol_id", "symbols"
        ) != "SET NULL":
            _sul_cols = {
                r[1]
                for r in connection.execute(
                    text("PRAGMA table_info(symbol_usage_logs)")
                ).fetchall()
            }
            if {"id", "user_id", "symbol_label", "position_in_utterance",
                 "utterance_length", "timestamp"} <= _sul_cols:
                logger.info(
                    "Migration: rebuilding symbol_usage_logs with ON DELETE SET NULL"
                )
                connection.execute(
                    text(
                        "CREATE TABLE _symbol_usage_logs_new ("
                        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
                        "  user_id INTEGER NOT NULL REFERENCES users(id),"
                        "  session_id INTEGER REFERENCES learning_sessions(id),"
                        "  symbol_id INTEGER REFERENCES symbols(id) ON DELETE SET NULL,"
                        "  symbol_label VARCHAR(50) NOT NULL,"
                        "  symbol_category VARCHAR(50),"
                        "  position_in_utterance INTEGER NOT NULL,"
                        "  utterance_length INTEGER NOT NULL,"
                        "  semantic_intent VARCHAR(20),"
                        "  timestamp DATETIME NOT NULL,"
                        "  context_topic VARCHAR(100)"
                        ")"
                    )
                )
                _sul_mapping = [
                    ("id", "id"),
                    ("user_id", "user_id"),
                    ("session_id", "NULL"),
                    ("symbol_id", "symbol_id"),
                    ("symbol_label", "symbol_label"),
                    ("symbol_category", "NULL"),
                    ("position_in_utterance", "position_in_utterance"),
                    ("utterance_length", "utterance_length"),
                    ("semantic_intent", "NULL"),
                    ("timestamp", "timestamp"),
                    ("context_topic", "NULL"),
                ]
                _sul_sel = ", ".join(
                    c if c in _sul_cols else f for c, f in _sul_mapping
                )
                connection.execute(
                    text(
                        f"INSERT INTO _symbol_usage_logs_new "
                        f"SELECT {_sul_sel} FROM symbol_usage_logs"
                    )
                )
                connection.execute(text("DROP TABLE symbol_usage_logs"))
                connection.execute(
                    text("ALTER TABLE _symbol_usage_logs_new RENAME TO symbol_usage_logs")
                )

        # ── One-time cleanup: remove symbols with corrupted labels ──
        _corrupted_patterns = [
            "%frontend-%",
            "%comm-%",
            "%node_modules%",
            "%dist/%",
            "%build/%",
            "%/%/",
            "%-%-%-%-%",
        ]
        pattern_clauses = " OR ".join(
            [f"label LIKE '{p}'" for p in _corrupted_patterns]
        )
        result = connection.execute(
            text(f"SELECT id, label FROM symbols WHERE {pattern_clauses}")
        ).fetchall()
        if result:
            corrupted_ids = [row[0] for row in result]
            logger.info(
                "Migration: removing {} corrupted symbol(s): {}",
                len(corrupted_ids),
                [row[1] for row in result],
            )
            # With ON DELETE CASCADE now active, deleting the symbol
            # automatically removes board_symbols rows.  symbol_usage_logs
            # has ON DELETE SET NULL so those become NULL automatically.
            id_list = ",".join(str(i) for i in corrupted_ids)
            connection.execute(
                text(f"DELETE FROM symbols WHERE id IN ({id_list})")
            )

        # ── One-time cleanup: merge case-insensitive duplicate symbols ──
        dupe_rows = connection.execute(
            text(
                "SELECT LOWER(label), MIN(id), COUNT(*) FROM symbols "
                "GROUP BY LOWER(label) HAVING COUNT(*) > 1"
            )
        ).fetchall()
        if dupe_rows:
            total_dupes = sum(r[2] - 1 for r in dupe_rows)
            logger.info(
                "Migration: merging {} case-insensitive duplicate symbol(s)",
                total_dupes,
            )
            for _lower_label, keep_id, _cnt in dupe_rows:
                dupe_ids = [
                    row[0]
                    for row in connection.execute(
                        text(
                            "SELECT id FROM symbols "
                            "WHERE LOWER(label) = :ll AND id != :k"
                        ),
                        {"ll": _lower_label, "k": keep_id},
                    ).fetchall()
                ]
                if not dupe_ids:
                    continue
                # Reassign board_symbols.symbol_id → keep_id
                for did in dupe_ids:
                    connection.execute(
                        text(
                            "UPDATE board_symbols SET symbol_id = :k "
                            "WHERE symbol_id = :d"
                        ),
                        {"k": keep_id, "d": did},
                    )
                # Delete the duplicates (CASCADE handles board_symbols that
                # we already reassigned; SET NULL handles usage logs).
                id_list = ",".join(str(i) for i in dupe_ids)
                connection.execute(
                    text(f"DELETE FROM symbols WHERE id IN ({id_list})")
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
    _ensure_foreign_key_actions(engine)
    _ensure_sqlite_indexes(engine)
    return engine
