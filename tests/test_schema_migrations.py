"""Regression tests for runtime schema creation and legacy upgrades."""

from sqlalchemy import create_engine, inspect, text

from src.aac_app import schema


def test_schema_ensure_upgrades_legacy_sqlite_without_losing_data():
    """Legacy columns are added while existing rows remain available."""
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY,
                    username VARCHAR(50) NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    display_name VARCHAR(100) NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE symbols (
                    id INTEGER PRIMARY KEY,
                    label VARCHAR(100) NOT NULL,
                    category VARCHAR(50)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE board_symbols (
                    id INTEGER PRIMARY KEY,
                    board_id INTEGER NOT NULL,
                    symbol_id INTEGER NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE user_settings (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE learning_sessions (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    topic_name VARCHAR(100) NOT NULL,
                    purpose TEXT,
                    mode_key VARCHAR(50),
                    status VARCHAR(20),
                    comprehension_score FLOAT,
                    questions_asked INTEGER,
                    questions_answered INTEGER,
                    correct_answers INTEGER,
                    conversation_history JSON,
                    started_at DATETIME,
                    ended_at DATETIME
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE learning_modes (
                    id INTEGER PRIMARY KEY,
                    created_at DATETIME
                )
                """
            )
        )
        connection.execute(
            text(
                "INSERT INTO users (id, username, password_hash, display_name) "
                "VALUES (1, 'legacy', 'hash', 'Legacy User')"
            )
        )

    schema.ensure(engine)
    inspector = inspect(engine)

    user_columns = {column["name"] for column in inspector.get_columns("users")}
    assert {"security_version", "credentials_changed_at"} <= user_columns

    assert "order_index" in {column["name"] for column in inspector.get_columns("symbols")}
    assert "order_index" in {
        column["name"] for column in inspector.get_columns("board_symbols")
    }
    settings_columns = {column["name"] for column in inspector.get_columns("user_settings")}
    assert {
        "tts_provider",
        "tts_local_voice",
        "tts_local_speed",
        "ui_language",
        "voice_mode_enabled",
        "dwell_time",
        "ignore_repeats",
        "high_contrast",
        "default_learning_mode",
    } <= settings_columns
    assert "updated_at" in {
        column["name"] for column in inspector.get_columns("learning_modes")
    }
    assert "board_id" in {
        column["name"] for column in inspector.get_columns("learning_sessions")
    }

    with engine.connect() as connection:
        assert connection.execute(text("SELECT username FROM users WHERE id = 1")).scalar_one() == (
            "legacy"
        )
        assert connection.execute(
            text("SELECT security_version FROM users WHERE id = 1")
        ).scalar_one() == 1

    # A second ensure is the normal restart path and must remain idempotent.
    schema.ensure(engine)
    engine.dispose()


def test_schema_ensure_skips_indexes_for_partial_legacy_tables():
    """A partial legacy table cannot make startup fail while upgrading."""
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE board_symbols (id INTEGER PRIMARY KEY, symbol_id INTEGER NOT NULL)"))

    schema.ensure(engine)

    with engine.connect() as connection:
        indexes = {row[1] for row in connection.execute(text('PRAGMA index_list("board_symbols")'))}
    assert "ix_board_symbols_symbol_id" in indexes
    assert "ix_board_symbols_board_position" not in indexes
    engine.dispose()


def test_schema_ensure_adds_notification_index_to_legacy_table():
    """Legacy notification tables receive both pagination indexes safely."""
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE notifications ("
                "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, "
                "is_read INTEGER NOT NULL, created_at DATETIME NOT NULL)"
            )
        )

    schema.ensure(engine)

    with engine.connect() as connection:
        indexes = {
            row[1]
            for row in connection.execute(text('PRAGMA index_list("notifications")'))
        }
    assert "ix_notifications_user_created" in indexes
    assert "ix_notifications_user_read_created" in indexes
    engine.dispose()


def test_schema_ensure_adds_targeted_indexes_to_current_schema():
    """Startup adds the measured indexes and remains idempotent."""
    engine = create_engine("sqlite:///:memory:")
    schema.ensure(engine)
    schema.ensure(engine)

    with engine.connect() as connection:
        indexes = {
            row[1]
            for table in (
                "communication_boards",
                "board_symbols",
                "board_assignments",
                "symbol_usage_logs",
                "learning_sessions",
                "notifications",
                "learning_modes",
            )
            for row in connection.execute(text(f'PRAGMA index_list("{table}")'))
        }

    assert {
        "ix_communication_boards_user_public",
        "ix_board_symbols_board_position",
        "ix_board_symbols_symbol_id",
        "ix_board_assignments_student_board",
        "ix_symbol_usage_logs_user_timestamp",
        "ix_symbol_usage_logs_user_session_position",
        "ix_symbol_usage_logs_user_symbol_label",
        "ix_learning_sessions_user_started",
        "ix_learning_sessions_user_status_started",
        "ix_learning_sessions_status_ended",
        "ix_notifications_user_read_created",
        "ix_notifications_user_created",
        "ix_learning_modes_key",
    } <= indexes

    with engine.connect() as connection:
        def index_columns(index_name: str) -> list[str]:
            return [
                row[2]
                for row in connection.execute(
                    text(f'PRAGMA index_info("{index_name}")')
                )
            ]

        assert index_columns("ix_learning_sessions_user_status_started") == [
            "user_id",
            "status",
            "started_at",
        ]
        assert index_columns("ix_learning_sessions_status_ended") == [
            "status",
            "ended_at",
        ]
    engine.dispose()
