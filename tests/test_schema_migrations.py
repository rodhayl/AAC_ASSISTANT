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

    assert "order_index" in {column["name"] for column in inspector.get_columns("symbols")}
    assert "order_index" in {
        column["name"] for column in inspector.get_columns("board_symbols")
    }
    settings_columns = {column["name"] for column in inspector.get_columns("user_settings")}
    assert {
        "ui_language",
        "voice_mode_enabled",
        "dwell_time",
        "ignore_repeats",
        "high_contrast",
    } <= settings_columns
    assert "updated_at" in {
        column["name"] for column in inspector.get_columns("learning_modes")
    }

    with engine.connect() as connection:
        assert connection.execute(text("SELECT username FROM users WHERE id = 1")).scalar_one() == (
            "legacy"
        )

    # A second ensure is the normal restart path and must remain idempotent.
    schema.ensure(engine)
