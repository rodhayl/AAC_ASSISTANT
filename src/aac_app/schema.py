"""Runtime schema creation and idempotent legacy upgrades.

``ensure`` first creates missing tables from the ORM metadata, then applies
the additive column/index upgrades needed by databases created by older
releases.  Discovery uses SQLAlchemy's dialect-portable inspector so a
non-SQLite deployment does not silently skip every upgrade (only the
constraint rebuilds that have no portable equivalent stay SQLite-specific).
"""

from __future__ import annotations

from collections.abc import Iterable

from loguru import logger
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from src.aac_app.db import create_engine_instance, create_tables


def _reflected_columns(inspector) -> dict[str, set[str]]:
    """Column names per table, skipping tables this connection cannot reflect.

    A sqlite-vec ``vec0`` table (``symbol_embeddings``) is only reflectable
    when its extension module is loaded on the inspecting connection, which is
    not the case during startup schema management. Letting that error escape
    aborted *every* additive upgrade for any database that already had the
    vector table, so an upgrading installation silently lost new columns and
    then failed at runtime. Virtual tables have no ORM columns to migrate, so
    skipping them is safe.
    """
    columns: dict[str, set[str]] = {}
    for table in inspector.get_table_names():
        try:
            columns[table] = {
                column["name"] for column in inspector.get_columns(table)
            }
        except SQLAlchemyError:
            logger.debug("DB upgrade: cannot reflect table {}; skipping", table)
    return columns


def _reflected_indexes(inspector, tables: Iterable[str]) -> dict[str, set[str]]:
    """Index names per table, skipping tables this connection cannot reflect."""
    indexes: dict[str, set[str]] = {}
    for table in tables:
        try:
            indexes[table] = {index["name"] for index in inspector.get_indexes(table)}
        except SQLAlchemyError:
            logger.debug("DB upgrade: cannot list indexes of {}; skipping", table)
    return indexes


def _table_columns(engine: Engine) -> dict[str, set[str]]:
    """Column names per table, on any dialect.

    The previous implementation read ``PRAGMA table_info`` / ``sqlite_master``
    and early-returned for every other dialect, so a Postgres deployment
    upgrading from an older release never received an additive column and
    failed later at runtime.
    """
    return _reflected_columns(sa_inspect(engine))


def _dialect_column_definition(dialect: str, definition: str) -> str:
    """Translate a SQLite-flavoured column definition for other dialects."""
    if dialect != "postgresql":
        return definition
    portable = definition.replace("DATETIME", "TIMESTAMP")
    if portable.upper().startswith("BOOLEAN"):
        portable = portable.replace("DEFAULT 1", "DEFAULT true").replace(
            "DEFAULT 0", "DEFAULT false"
        )
    return portable


def _ensure_additive_columns(engine: Engine) -> None:
    """Apply additive column upgrades to an existing database."""
    dialect = engine.dialect.name
    available_columns = _table_columns(engine)

    with engine.begin() as connection:
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
            ("content_safety_events", "call_count", "INTEGER NOT NULL DEFAULT 1"),
            ("learning_modes", "updated_at", "DATETIME"),
            ("learning_modes", "auto_ask_enabled", "BOOLEAN DEFAULT 1"),
            ("learning_sessions", "mode_key", "VARCHAR(50)"),
        )
        for table, column, definition in columns:
            table_columns = available_columns.get(table)
            if table_columns is None or column in table_columns:
                continue
            logger.info("DB upgrade: adding {}.{}", table, column)
            connection.execute(
                text(
                    f"ALTER TABLE {table} ADD COLUMN {column} "
                    f"{_dialect_column_definition(dialect, definition)}"
                )
            )
            table_columns.add(column)

        # Data backfills. Plain SQL, so they run on every dialect.
        if "created_by_user_id" in available_columns.get("saved_topics", set()):
            connection.execute(
                text(
                    "UPDATE saved_topics SET created_by_user_id = user_id "
                    "WHERE created_by_user_id IS NULL"
                )
            )

        if "updated_at" in available_columns.get("learning_modes", set()):
            connection.execute(
                text(
                    "UPDATE learning_modes SET updated_at = created_at "
                    "WHERE updated_at IS NULL"
                )
            )


# Duplicate-row cleanups that must run before the matching unique index is
# created. Shared by every dialect, unlike the SQLite-only table rebuilds.
_UNIQUE_ROSTER_INVARIANTS = (
    ("board_assignments", "uq_board_assignments_board_student", "board_id, student_id"),
    ("student_teachers", "uq_student_teachers_student_teacher", "student_id, teacher_id"),
    ("user_achievements", "uq_user_achievements_user_achievement", "user_id, achievement_id"),
)


def _create_index_prefix(dialect: str, *, unique: bool = False) -> str:
    """``CREATE [UNIQUE] INDEX`` with the dialect's idempotency clause."""
    prefix = "CREATE UNIQUE INDEX" if unique else "CREATE INDEX"
    if dialect in {"sqlite", "postgresql"}:
        return f"{prefix} IF NOT EXISTS"
    return prefix


def _ensure_indexes(engine: Engine) -> None:
    """Create indexes for confirmed ownership, join, and history queries.

    Index creation is additive and idempotent so it is safe for existing
    databases on any dialect and for repeated application startup.
    """
    dialect = engine.dialect.name
    inspector = sa_inspect(engine)
    available_columns = _reflected_columns(inspector)
    existing_indexes = _reflected_indexes(inspector, available_columns)

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
        for index_name, table_name, columns in indexes:
            table_columns = available_columns.get(table_name)
            if table_columns is None:
                continue
            requested_columns = {column.strip() for column in columns.split(",")}
            if not requested_columns <= table_columns:
                logger.warning(
                    "Skipping index {} because {} is missing columns {}",
                    index_name,
                    table_name,
                    sorted(requested_columns - table_columns),
                )
                continue
            if index_name in existing_indexes.get(table_name, set()):
                continue
            connection.execute(
                text(
                    f"{_create_index_prefix(dialect)} {index_name} "
                    f"ON {table_name} ({columns})"
                )
            )

        # Older databases allowed duplicate rows because these ORM uniqueness
        # rules were introduced after the tables existed. Keep the earliest
        # row (and its audit metadata), then enforce the invariant at the
        # database boundary so concurrent writes cannot duplicate a pair.
        for table_name, index_name, key_columns in _UNIQUE_ROSTER_INVARIANTS:
            table_columns = available_columns.get(table_name, set())
            required = {"id", *(column.strip() for column in key_columns.split(","))}
            if not required <= table_columns:
                continue
            if index_name in existing_indexes.get(table_name, set()):
                continue
            column_list = ", ".join(column.strip() for column in key_columns.split(","))
            connection.execute(
                text(
                    f"DELETE FROM {table_name} WHERE id NOT IN ("
                    f"SELECT MIN(id) FROM {table_name} GROUP BY {column_list})"
                )
            )
            connection.execute(
                text(
                    f"{_create_index_prefix(dialect, unique=True)} {index_name} "
                    f"ON {table_name} ({column_list})"
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

    SQLite cannot ``ALTER TABLE ADD CONSTRAINT``, so the fix requires a table
    rebuild for which no portable equivalent exists.  Non-SQLite deployments
    get an explicit warning naming the constraints their migration tooling
    must apply, instead of silently skipping the upgrade.
    """
    if engine.dialect.name != "sqlite":
        logger.warning(
            "Database dialect {} does not support the SQLite table-rebuild "
            "migration for ON DELETE actions on board_symbols.symbol_id "
            "(CASCADE) and symbol_usage_logs.symbol_id (SET NULL); apply them "
            "with the deployment's migration tooling.",
            engine.dialect.name,
        )
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


def _widen_legacy_tts_voice(engine: Engine) -> None:
    """Widen a length-limited ``user_settings.tts_voice`` to VARCHAR(200).

    Browser speechSynthesis voice pickers store full ``voiceURI`` strings
    (e.g. ``"Microsoft Sabina - Spanish (Mexico)"``) in this column. The
    original model declared ``String(20)`` which never matched the real-world
    value size; SQLite does not enforce VARCHAR lengths so nothing was ever
    truncated, but the declared type must agree with the widened model for
    schema introspection and non-SQLite engines.

    SQLite has no ``ALTER COLUMN TYPE``, so the column is widened by the
    rename/add/copy/drop sequence. PostgreSQL gets the native idempotent
    ``ALTER COLUMN TYPE`` in ``_widen_postgresql_tts_voice`` (``DATABASE_URL``
    accepts postgres connection strings, so a PG deployment must not keep the
    narrow type forever). The migration is idempotent on both backends: it
    runs only while the declared type still carries an explicit length limit
    below 200 and then leaves the widened column alone on later startups.
    """
    if engine.dialect.name == "postgresql":
        _widen_postgresql_tts_voice(engine)
        return
    if engine.dialect.name != "sqlite":
        return

    with engine.begin() as connection:
        table_row = connection.execute(
            text(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='user_settings'"
            )
        ).fetchone()
        if table_row is None:
            return
        info_rows = connection.execute(
            text("PRAGMA table_info(user_settings)")
        ).fetchall()
        voice_column = next((row for row in info_rows if row[1] == "tts_voice"), None)
        if voice_column is None:
            return

        # PRAGMA table_info columns: cid, name, type, notnull, dflt_value, pk
        declared_type = (voice_column[2] or "").strip().upper()
        # Only a declared length limit below the target needs widening; an
        # untyped/TEXT column is already unbounded and VARCHAR(200)+ is done.
        is_length_limited = (
            declared_type.startswith("VARCHAR(")
            or declared_type.startswith("CHAR(")
            or declared_type.startswith("NVARCHAR(")
        )
        if not is_length_limited:
            return
        try:
            limit = int(declared_type.split("(", 1)[1].rstrip(")"))
        except (IndexError, ValueError):
            return
        if limit >= 200:
            return

        logger.info(
            "DB upgrade: widening user_settings.tts_voice from {} to VARCHAR(200)",
            declared_type,
        )
        # Recreate the column with the same nullability/default but the wider
        # type, then copy existing values across and drop the narrow original.
        notnull = " NOT NULL" if voice_column[3] else ""
        default = f" DEFAULT {voice_column[4]}" if voice_column[4] is not None else ""
        connection.execute(
            text(
                "ALTER TABLE user_settings "
                "RENAME COLUMN tts_voice TO _tts_voice_legacy"
            )
        )
        connection.execute(
            text(
                f"ALTER TABLE user_settings "
                f"ADD COLUMN tts_voice VARCHAR(200){notnull}{default}"
            )
        )
        connection.execute(
            text(
                "UPDATE user_settings SET tts_voice = _tts_voice_legacy "
                "WHERE _tts_voice_legacy IS NOT NULL"
            )
        )
        connection.execute(
            text("ALTER TABLE user_settings DROP COLUMN _tts_voice_legacy")
        )


def _widen_postgresql_tts_voice(engine: Engine) -> None:
    """Widen a legacy ``user_settings.tts_voice`` column on PostgreSQL.

    Mirrors the SQLite branch: only an explicit declared length below 200
    needs widening (an unbounded TEXT or an already-widened column is left
    alone). PostgreSQL reports lengths through ``information_schema``, so the
    migration can introspect the current limit instead of guessing.
    """
    with engine.begin() as connection:
        row = connection.execute(
            text(
                "SELECT character_maximum_length "
                "FROM information_schema.columns "
                "WHERE table_schema = current_schema() "
                "AND table_name = 'user_settings' "
                "AND column_name = 'tts_voice'"
            )
        ).fetchone()
        if row is None or row[0] is None or int(row[0]) >= 200:
            # No column yet, an unbounded type (TEXT), or already widened.
            return
        logger.info(
            "DB upgrade: widening user_settings.tts_voice from VARCHAR({}) to "
            "VARCHAR(200) on postgresql",
            row[0],
        )
        connection.execute(
            text(
                "ALTER TABLE user_settings "
                "ALTER COLUMN tts_voice TYPE VARCHAR(200)"
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
    _ensure_additive_columns(engine)
    _widen_legacy_tts_voice(engine)
    _ensure_foreign_key_actions(engine)
    _ensure_indexes(engine)
    return engine
