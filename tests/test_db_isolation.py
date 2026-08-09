
import os

from sqlalchemy import text

from src.aac_app.db import (
    create_engine_instance,
    create_session_factory,
)


def test_database_isolation(test_db_session, monkeypatch, tmp_path):
    """
    Verify that tests use an isolated temporary database and never the
    production database file.
    """
    # 1. Verify environment variable is set by fixture
    database_url = os.environ.get("DATABASE_URL", "")
    assert database_url.startswith("sqlite:///")
    assert database_url != "sqlite:///:memory:"
    assert str(tmp_path).replace("\\", "/").casefold() in database_url.casefold()
    assert os.environ.get("TESTING") == "1"

    # 2. Verify the process-wide engine uses the same isolated temp database.
    engine = create_engine_instance()
    assert str(engine.url) == database_url

    # 3. Verify we can write to this DB
    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS test_isolation (id INTEGER PRIMARY KEY)"))
        conn.execute(text("INSERT INTO test_isolation (id) VALUES (1)"))
        conn.commit()

        result = conn.execute(text("SELECT * FROM test_isolation")).fetchall()
        assert len(result) == 1

    # 4. The fixture URL is under pytest's temporary directory, so production
    # data cannot be touched by process-wide database helpers.

    # 5. Switching URLs remains temporary and isolated as well.

    # Switching URLs must remain within pytest's temporary directory; never
    # remove DATABASE_URL here because that would resolve to the real app DB.
    alternate_path = tmp_path / "alternate.sqlite3"
    alternate_url = f"sqlite:///{alternate_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", alternate_url)
    engine_file = create_engine_instance()
    assert str(engine_file.url) == alternate_url


def test_session_factory_is_cached():
    """Request-level session creation reuses one process-wide factory."""
    assert create_session_factory() is create_session_factory()

