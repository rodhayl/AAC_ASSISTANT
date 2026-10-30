"""
Pytest configuration and fixtures for AAC Assistant tests

This file ensures:
1. Clean database state for each test
2. Proper test isolation
3. Consistent test environment
"""
import pytest
from unittest.mock import Mock, AsyncMock
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.aac_app.models.database import Base, User
from src.aac_app.models.audit_log import AuditLog, FailedLoginAttempt  # Import audit models
from src.api.main import app
from src.api.dependencies import get_db
from src.aac_app.services.auth_service import get_password_hash

@pytest.fixture(scope="function")
def test_db_engine():
    """
    Create a fresh in-memory SQLite database for each test.
    This ensures complete isolation between tests.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
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
    
    # Cleanup
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
def setup_test_db(test_db_session):
    """
    Configure FastAPI app to use test database.
    Use this fixture in test files that need API testing.
    """
    def override_get_db():
        try:
            yield test_db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    # Patch get_session used by services to use the test session
    from unittest.mock import patch
    from contextlib import contextmanager
    
    @contextmanager
    def override_get_session_cm():
        # Yield the same test session
        # We don't close it here because it's managed by the test_db_session fixture
        yield test_db_session
        
    # Patch all modules that use get_session
    patches = [
        patch('src.aac_app.services.learning_companion_service.get_session', side_effect=override_get_session_cm),
        patch('src.aac_app.services.achievement_system.get_session', side_effect=override_get_session_cm),
        patch('src.aac_app.services.symbol_analytics.get_session', side_effect=override_get_session_cm),
        patch('src.aac_app.services.guardian_profile_service.get_session', side_effect=override_get_session_cm),
        patch('src.api.dependencies.get_session', side_effect=override_get_session_cm)
    ]
    
    for p in patches:
        p.start()
        
    yield
    
    for p in patches:
        p.stop()
        
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def reset_production_db():
    """
    Prevent tests from accidentally using the production database.
    This fixture runs automatically for all tests.
    """
    import os
    # Store original environment
    original_env = os.environ.get('DATABASE_URL')
    original_testing = os.environ.get('TESTING')

    # Force test environment (disables rate limiting)
    os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
    os.environ['TESTING'] = '1'

    yield

    # Restore original environment
    if original_env:
        os.environ['DATABASE_URL'] = original_env
    elif 'DATABASE_URL' in os.environ:
        del os.environ['DATABASE_URL']

    if original_testing:
        os.environ['TESTING'] = original_testing
    elif 'TESTING' in os.environ:
        del os.environ['TESTING']


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


@pytest.fixture(scope="function")
def mock_tts_provider():
    """Create a mock TTS provider that doesn't require audio output"""
    mock_tts = Mock()
    mock_tts.speak = Mock()
    return mock_tts


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
