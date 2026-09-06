"""Regression tests for credential revocation on operator/migration paths.

Operator scripts mutate password hashes outside the API request flow. Every
one of those paths must call ``mark_credentials_changed`` so that previously
issued access and refresh tokens are revoked the same way a web password
change would be.

Covered paths:
- ``src.scripts.account_admin.reset_password`` (admin CLI password reset)
- ``scripts.migrate_passwords.migrate_passwords`` (SHA-256 -> bcrypt migration)
- ``scripts.fix_null_passwords.fix_null_password_hashes`` (null-hash repair)

These tests call the script functions with an isolated in-memory database and
assert that both ``security_version`` is incremented and
``credentials_changed_at`` is recorded.
"""

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from src.aac_app.models import Base, User
from src.scripts.account_admin import reset_password

pytestmark = pytest.mark.usefixtures("reset_production_db")


@pytest.fixture()
def op_db():
    """In-memory database and session factory for operator-script tests."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def _get_session():
        from contextlib import contextmanager

        @contextmanager
        def _managed():
            session = factory()
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

        return _managed()

    yield factory, _get_session
    engine.dispose()


@pytest.fixture()
def legacy_null_password_db():
    """A minimal legacy users table whose ``password_hash`` is nullable.

    Current ORM metadata enforces NOT NULL on ``password_hash``, so a null-hash
    row can only exist in a database created before that constraint. This
    fixture recreates that legacy shape with raw SQL so
    ``fix_null_passwords`` can be exercised on its actual target state.
    """
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("PRAGMA foreign_keys=OFF"))
        connection.execute(
            text(
                "CREATE TABLE users ("
                "id INTEGER PRIMARY KEY, "
                "username VARCHAR(50) NOT NULL UNIQUE, "
                "email VARCHAR(100), "
                "password_hash VARCHAR(255), "
                "security_version INTEGER NOT NULL DEFAULT 1, "
                "credentials_changed_at DATETIME, "
                "display_name VARCHAR(100) NOT NULL, "
                "user_type VARCHAR(20), "
                "is_active BOOLEAN, "
                "created_at DATETIME, "
                "updated_at DATETIME)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO users (username, display_name, user_type, "
                "password_hash, security_version, is_active) "
                "VALUES (:username, :display_name, :user_type, NULL, 1, 1)"
            ),
            {"username": "null_hash", "display_name": "User null_hash", "user_type": "student"},
        )
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def _get_session():
        from contextlib import contextmanager

        @contextmanager
        def _managed():
            session = factory()
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

        return _managed()

    yield factory, _get_session
    engine.dispose()


def _make_user(factory, username: str, password_hash: str):
    user = User(
        username=username,
        display_name=f"User {username}",
        user_type="student",
        password_hash=password_hash,
        is_active=True,
        security_version=1,
    )
    session = factory()
    try:
        session.add(user)
        session.commit()
        session.refresh(user)
        return user
    finally:
        session.close()


LEGACY_SHA256_HASH = "a" * 64


def _assert_revoked(session, user_id: int, previous_version: int) -> None:
    """Assert a password mutation recorded the credential-change markers."""
    session.expire_all()
    user = session.query(User).filter(User.id == user_id).first()
    assert user.security_version == previous_version + 1
    assert user.credentials_changed_at is not None


def test_account_admin_reset_password_marks_credentials_changed(op_db):
    """The admin CLI password reset revokes existing sessions."""
    factory, _ = op_db
    user = _make_user(factory, "cli_user", "initial_test_hash")
    session = factory()
    try:
        assert reset_password(session, user.username, "NewPass123") is True
        session.expire_all()
        refreshed = session.query(User).filter(User.id == user.id).first()
        assert refreshed.password_hash != "initial_test_hash"
        _assert_revoked(session, user.id, previous_version=1)
    finally:
        session.close()


def test_account_admin_reset_password_unknown_user_returns_false(op_db):
    """A reset for a missing user does not create or mark anything."""
    factory, _ = op_db
    session = factory()
    try:
        assert reset_password(session, "ghost_user", "NewPass123") is False
        assert session.query(User).count() == 0
    finally:
        session.close()


def test_migrate_passwords_marks_credentials_changed_for_sha256_users(
    op_db, monkeypatch
):
    """The SHA-256 -> bcrypt migration revokes sessions of migrated users."""
    factory, get_session = op_db
    sha_user = _make_user(factory, "legacy_sha", LEGACY_SHA256_HASH)
    bcrypt_user = _make_user(factory, "modern_bcrypt", "$2b$12$abcdefghijklmnopqrstuv")
    # The migration imports the DB accessor lazily inside the function (so
    # ``--help`` stays inert), so the patch target is the source module.
    monkeypatch.setattr("src.aac_app.db.get_session", get_session)

    import scripts.migrate_passwords as migrate_passwords

    migrate_passwords.migrate_passwords(
        "TempPass123!", skip_confirmation=True
    )

    session = factory()
    try:
        migrated = session.query(User).filter(User.id == sha_user.id).first()
        assert migrated.password_hash.startswith("$2b$")
        assert migrated.password_hash != LEGACY_SHA256_HASH
        _assert_revoked(session, sha_user.id, previous_version=1)

        # Users already on bcrypt are left untouched: no hash change, no
        # credential markers, no session revocation.
        untouched = session.query(User).filter(User.id == bcrypt_user.id).first()
        assert untouched.password_hash == "$2b$12$abcdefghijklmnopqrstuv"
        assert untouched.security_version == 1
        assert untouched.credentials_changed_at is None
    finally:
        session.close()


def test_migrate_temp_password_policy_reuses_shared_policy(op_db):
    """The temp-password bar is the shared policy plus temp-only hardening.

    Migration temp passwords are handed out to many accounts at once, so the
    script is deliberately stricter than the shared policy (12+ chars and a
    special char, not just 8+upper+lower+digit). It must never relax below
    that historical bar, and its base requirements must come from the shared
    policy so the two definitions cannot diverge.
    """
    import scripts.migrate_passwords as migrate_passwords

    strong = migrate_passwords._temp_password_is_strong

    # Old bar preserved: 12+ chars with upper/lower/digit/special.
    assert strong("TempPass123!") is True
    # Base shared-policy violations are still rejected.
    assert strong("short1!") is False  # too short for the shared policy too
    assert strong("abcdefghijklm") is False  # no upper/digit/special
    # The temp-only hardening sits on top: meets the shared 8-char policy but
    # lacks 12+ chars / a special character, so it stays rejected.
    assert strong("Abcd1234") is False
    assert strong("Abcdefghijkl1") is False  # 12+ chars, no special char


def test_fix_null_passwords_marks_credentials_changed(legacy_null_password_db, monkeypatch):
    """Repairing a null password hash revokes the affected user's sessions."""
    factory, get_session = legacy_null_password_db
    monkeypatch.setattr("scripts.fix_null_passwords.get_session", get_session)

    import scripts.fix_null_passwords as fix_null_passwords

    assert fix_null_passwords.fix_null_password_hashes(delete_invalid=False) is True

    session = factory()
    try:
        fixed = session.query(User).filter(User.username == "null_hash").first()
        assert fixed is not None
        assert fixed.password_hash is not None
        assert fixed.password_hash != ""
        _assert_revoked(session, fixed.id, previous_version=1)
    finally:
        session.close()


def test_account_admin_reset_password_rejects_weak_password_unless_forced(op_db):
    """The CLI reset enforces the shared policy; --force is the only escape."""
    factory, _ = op_db
    user = _make_user(factory, "weak_cli_user", "initial_test_hash")
    session = factory()
    try:
        # A weak password is refused by default (same policy as API routes).
        assert reset_password(session, user.username, "123") is False
        session.expire_all()
        unchanged = session.query(User).filter(User.id == user.id).first()
        assert unchanged.password_hash == "initial_test_hash"
        assert unchanged.security_version == 1

        # --force is the explicit emergency-recovery override: it hashes and
        # still revokes previously issued sessions like a normal reset.
        assert reset_password(session, user.username, "123", force=True) is True
        session.expire_all()
        refreshed = session.query(User).filter(User.id == user.id).first()
        assert refreshed.password_hash != "initial_test_hash"
        _assert_revoked(session, user.id, previous_version=1)
    finally:
        session.close()
