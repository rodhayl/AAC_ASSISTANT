"""
Integration tests for Critical User Flows and Seeding.
Ensures that the 'Golden Path' for default users is always functional.
"""

import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.aac_app.models import Achievement, Base, User, UserAchievement  # noqa: E402
from src.aac_app.services.auth_service import verify_password  # noqa: E402

# Use a separate test database file for this test to verify seeding logic specifically
TEST_DB_URL = "sqlite:///:memory:"


@pytest.fixture(scope="function")
def db_session():
    """Create an in-memory database and seed it"""
    engine = create_engine(TEST_DB_URL)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Mock the session getter used by init_database if needed,
    # but init_database uses its own context manager.
    # We'll manually verify the seeding logic components here.

    yield session
    session.close()
    engine.dispose()


def test_default_users_exist_and_can_login(monkeypatch):
    """
    Verify sample users exist and respect env-provided seed passwords.
    """
    # Setup: Create in-memory DB
    engine = create_engine(TEST_DB_URL)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    users_to_check = [
        ("student1", "Student123!", "student"),
        ("teacher1", "Teacher123!", "teacher"),
        ("admin1", "Admin123", "admin"),
    ]
    for username, password, _ in users_to_check:
        monkeypatch.setenv(f"AAC_SEED_{username.upper()}_PASSWORD", password)

    # Act: Run seeding logic
    from src.aac_app.seed import _create_sample_users

    _create_sample_users(session)
    session.commit()

    # Assert
    for username, password, role in users_to_check:
        user = session.query(User).filter(User.username == username).first()
        assert user is not None, f"User {username} was not created"
        assert (
            user.user_type == role
        ), f"User {username} has wrong role: {user.user_type}"
        assert verify_password(
            password, user.password_hash
        ), f"Password for {username} is incorrect"

    session.close()
    engine.dispose()


def test_production_bootstrap_rejects_weak_password_before_creation(monkeypatch):
    """A weak production bootstrap password must never create an admin."""
    from src import config
    from src.aac_app.seed import _ensure_bootstrap_admin

    engine = create_engine(TEST_DB_URL)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    monkeypatch.setattr(config, "ENVIRONMENT", "production")
    monkeypatch.setenv("AAC_BOOTSTRAP_ADMIN_ON_FIRST_RUN", "true")
    monkeypatch.setenv("AAC_BOOTSTRAP_ADMIN_USERNAME", "admin1")
    monkeypatch.setenv("AAC_BOOTSTRAP_ADMIN_PASSWORD", "weak-password")

    with pytest.raises(ValueError, match="AAC_BOOTSTRAP_ADMIN_PASSWORD"):
        _ensure_bootstrap_admin(session)
    assert session.query(User).count() == 0

    monkeypatch.setenv("AAC_BOOTSTRAP_ADMIN_PASSWORD", "Admin123")
    with pytest.raises(ValueError, match="development default"):
        _ensure_bootstrap_admin(session)
    assert session.query(User).count() == 0
    session.close()
    engine.dispose()


def test_production_bootstrap_ignores_weak_password_when_admin_exists(monkeypatch):
    """Existing installations are not blocked by an unused bootstrap setting."""
    from src import config
    from src.aac_app.seed import _ensure_bootstrap_admin
    from src.aac_app.services.auth_service import get_password_hash

    engine = create_engine(TEST_DB_URL)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(
        User(
            username="existing-admin",
            display_name="Existing Admin",
            user_type="admin",
            password_hash=get_password_hash("ExistingAdmin123"),
        )
    )
    session.commit()
    monkeypatch.setattr(config, "ENVIRONMENT", "production")
    monkeypatch.setenv("AAC_BOOTSTRAP_ADMIN_ON_FIRST_RUN", "true")
    monkeypatch.setenv("AAC_BOOTSTRAP_ADMIN_PASSWORD", "weak-password")

    _ensure_bootstrap_admin(session)
    assert session.query(User).count() == 1
    session.close()
    engine.dispose()


def test_seed_preserves_custom_achievement_with_system_definition():
    """System cleanup must not delete a custom matching achievement."""
    from src.aac_app.seed import _create_sample_achievements

    engine = create_engine(TEST_DB_URL)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    owner = User(
        username="custom_achievement_owner",
        display_name="Custom Owner",
        user_type="teacher",
        password_hash="test-hash",
    )
    session.add(owner)
    session.flush()
    custom = Achievement(
        name="First Steps",
        description="Complete your first learning session",
        category="beginner",
        criteria_type="sessions_completed",
        criteria_value=1,
        points=99,
        icon="🌈",
        created_by=owner.id,
    )
    session.add(custom)
    session.flush()
    earned = UserAchievement(user_id=owner.id, achievement_id=custom.id)
    session.add(earned)
    session.flush()

    _create_sample_achievements(session)
    session.commit()

    preserved = session.get(Achievement, custom.id)
    assert preserved is not None
    assert preserved.created_by == owner.id
    assert preserved.points == 99
    assert preserved.icon == "🌈"
    assert session.get(UserAchievement, earned.id).achievement_id == custom.id
    assert session.query(Achievement).filter(Achievement.name == "First Steps").count() == 2

    session.close()
    engine.dispose()


def test_ensure_bootstrap_admin_script_reports_rejection_cleanly(monkeypatch):
    """The operator script must surface a rejected production bootstrap
    as a clear message and a non-zero exit code, not a raw traceback."""
    import importlib

    script = importlib.import_module("scripts.ensure_bootstrap_admin")

    def _raise_value_error() -> int:
        raise ValueError("AAC_BOOTSTRAP_ADMIN_PASSWORD is not acceptable in production")

    monkeypatch.setattr(script, "ensure_bootstrap_admin", _raise_value_error)
    assert script.main() == 1


def test_ensure_bootstrap_admin_script_propagates_disabled(monkeypatch):
    """A successful script run exits zero."""
    import importlib

    script = importlib.import_module("scripts.ensure_bootstrap_admin")
    monkeypatch.setattr(script, "ensure_bootstrap_admin", lambda: 0)
    assert script.main() == 0


def test_database_initialization_idempotency():
    """
    Verify that init_database doesn't duplicate data or fail on second run.
    """
    # The component-level seed functions are safe to call repeatedly.  This is
    # the behavior used by every application restart.
    from src.aac_app.seed import (
        _create_sample_achievements,
        _create_sample_symbols,
    )

    engine = create_engine(TEST_DB_URL)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    _create_sample_symbols(session)
    _create_sample_achievements(session)
    first_steps = (
        session.query(Achievement)
        .filter(Achievement.name == "First Steps")
        .first()
    )
    session.add(
        Achievement(
            name=first_steps.name,
            description=first_steps.description,
            category=first_steps.category,
            criteria_type=first_steps.criteria_type,
            criteria_value=first_steps.criteria_value,
        )
    )
    session.flush()
    _create_sample_symbols(session)
    _create_sample_achievements(session)
    session.commit()

    assert session.query(User).count() == 0
    from src.aac_app.models import Symbol

    assert session.query(Symbol).count() == 5
    assert session.query(Achievement).count() == 3
    session.close()
    engine.dispose()
