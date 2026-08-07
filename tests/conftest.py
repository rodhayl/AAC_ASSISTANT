"""
Pytest configuration and fixtures for AAC Assistant tests

This file ensures:
1. Clean database state for each test
2. Proper test isolation
3. Consistent test environment
"""
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from src.aac_app import db as database
from src.aac_app.models import Base, User
from src.aac_app.services.auth_service import get_password_hash
from src.api.deps import clear_settings_cache, get_db
from src.api.main import app


@pytest.fixture(scope="session", autouse=True)
def cleanup_process_resources():
    """Dispose process-wide database resources after all tests finish."""
    yield
    database.dispose_engine_instance()


@pytest.fixture(scope="function")
def test_db_engine(tmp_path: Path, monkeypatch, reset_production_db):
    """
    Create a fresh temporary file-backed SQLite database for each test.
    This ensures complete isolation between tests while allowing cross-thread
    access from FastAPI's test client.
    """
    # A temporary file-backed database avoids StaticPool's single immortal
    # sqlite3 connection while retaining cross-thread access for TestClient.
    database_path = tmp_path / "test.sqlite3"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )

    # Enable foreign key constraints for SQLite
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Create all tables
    Base.metadata.create_all(bind=engine)

    yield engine

    # This finalizer runs after dependent sessions have closed. Dispose any
    # process-wide engine opened by API/service code before forcing collection.
    database.dispose_engine_instance()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def test_db_session(test_db_engine):
    """
    Create a database session for testing.
    Automatically rolls back after each test.
    """
    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=test_db_engine
    )

    session = TestingSessionLocal()

    yield session

    session.close()


@pytest.fixture(autouse=False)
def setup_test_db(test_db_engine):
    """
    Configure FastAPI app to use test database.
    Use this fixture in test files that need API testing.
    """
    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=test_db_engine,
    )

    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db

    # Patch get_session used by services to use the test session
    from contextlib import contextmanager
    from unittest.mock import patch

    @contextmanager
    def override_get_session_cm():
        session = TestingSessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # Patch all modules that use get_session
    patches = [
        patch('src.aac_app.services.achievement_system.get_session', side_effect=override_get_session_cm),
        patch('src.aac_app.services.symbol_analytics.get_session', side_effect=override_get_session_cm),
        patch('src.aac_app.services.guardian_profile_service.get_session', side_effect=override_get_session_cm),
        patch('src.api.deps.settings.get_session', side_effect=override_get_session_cm),
    ]

    for p in patches:
        p.start()

    yield

    for p in patches:
        p.stop()

    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def reset_production_db(monkeypatch):
    """
    Prevent tests from accidentally using the production database.
    This fixture runs automatically for all tests.
    """
    # Force test environment (disables rate limiting) and use a strong,
    # deterministic attack-test secret so PyJWT never warns about HS256 keys.
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("TESTING", "1")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-jwt-secret-" + ("x" * 48))
    clear_settings_cache()

    yield

    clear_settings_cache()


@pytest.fixture(scope="function")
def mock_llm_provider():
    """
    Create a mock LLM provider for testing learning service.
    Returns predictable responses without making real API calls.
    """
    mock_provider = Mock()
    mock_provider.generate = AsyncMock(return_value="This is a test response from the mock LLM.")
    mock_provider.is_available = Mock(return_value=True)
    return mock_provider


@pytest.fixture(scope="function")
def mock_speech_provider():
    """Create a mock speech provider that doesn't require audio processing"""
    mock_speech = Mock()
    mock_speech.transcribe = AsyncMock(return_value="transcribed text")
    return mock_speech


@pytest.fixture(scope="session")
def test_password():
    """Return a consistent password for all test users that meets security requirements."""
    return "TestPassword123"  # Fixed: Added uppercase T and P to meet complexity requirements


@pytest.fixture(scope="function")
def admin_user(test_db_session, test_password):
    """Create an admin user for testing."""
    user = User(
        username="admin_test",
        email="admin@test.com",
        password_hash=get_password_hash(test_password),
        user_type="admin",
        is_active=True,
        display_name="Admin Test"
    )
    test_db_session.add(user)
    test_db_session.commit()
    test_db_session.refresh(user)
    return user


@pytest.fixture(scope="function")
def regular_user(test_db_session, test_password):
    """Create a regular user for testing."""
    user = User(
        username="user_test",
        email="user@test.com",
        password_hash=get_password_hash(test_password),
        user_type="standard",
        is_active=True,
        display_name="User Test"
    )
    test_db_session.add(user)
    test_db_session.commit()
    test_db_session.refresh(user)
    return user


@pytest.fixture(scope="function")
def admin_token(admin_user):
    """Create a valid JWT access token for the admin user."""
    from src.aac_app.utils.jwt_utils import create_access_token
    return create_access_token(data={"sub": admin_user.username, "user_id": admin_user.id, "user_type": admin_user.user_type})


@pytest.fixture(scope="function")
def user_token(regular_user):
    """Create a valid JWT access token for the regular user."""
    from src.aac_app.utils.jwt_utils import create_access_token
    return create_access_token(data={"sub": regular_user.username, "user_id": regular_user.id, "user_type": regular_user.user_type})
