
import os
from sqlalchemy import text
from src.aac_app.models.database import create_engine_instance, get_database_path

def test_database_isolation(test_db_session):
    """
    Verify that tests are running against an in-memory database
    and not the production database file.
    """
    # 1. Verify environment variable is set by fixture
    assert os.environ.get("DATABASE_URL") == "sqlite:///:memory:"
    assert os.environ.get("TESTING") == "1"

    # 2. Verify engine is using in-memory DB
    engine = create_engine_instance()
    assert str(engine.url) == "sqlite:///:memory:"

    # 3. Verify we can write to this DB
    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS test_isolation (id INTEGER PRIMARY KEY)"))
        conn.execute(text("INSERT INTO test_isolation (id) VALUES (1)"))
        conn.commit()
        
        result = conn.execute(text("SELECT * FROM test_isolation")).fetchall()
        assert len(result) == 1

    # 4. Verify production DB file is NOT touched (optional, but good sanity check)
    # We can't easily check file modification time here reliably without race conditions,
    # but we can ensure the code path would lead to memory.
    
    # 5. Verify that removing the env var falls back to file (sanity check for logic)
    # We need to be careful not to actually create a file if we can avoid it, 
    # or use a temp file.
    
    current_url = os.environ.pop("DATABASE_URL")
    try:
        # Now it should default to file
        engine_file = create_engine_instance()
        expected_path = get_database_path()
        assert str(engine_file.url) == f"sqlite:///{expected_path}"
    finally:
        os.environ["DATABASE_URL"] = current_url

