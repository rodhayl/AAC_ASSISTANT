"""
Regression tests for secure first-run administrator setup and bootstrap.

Proves that:
1. A fresh packaged/default configuration cannot create admin1/Admin123 automatically.
2. Production and packaged first-run paths require secure setup.
3. The /api/auth/setup endpoint creates the initial admin with strong credentials and locks.
4. Weak and development default passwords are rejected by the setup endpoint.
5. Explicit test credentials continue to work only in test workflows.
6. No bootstrap password is printed or stored in plaintext.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src import config
from src.aac_app.models import Base, User
from src.aac_app.seed import init_database
from src.aac_app.services.auth_service import verify_password
from src.api.main import app


@pytest.fixture
def fresh_db(tmp_path: Path, monkeypatch):
    db_file = tmp_path / "first_run_test.sqlite3"
    db_url = f"sqlite:///{db_file.as_posix()}"
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    # Isolate dotenv candidates so local dev .env doesn't leak into tests
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(config, "LEGACY_ENV_FILE", tmp_path / "env.properties")

    yield engine, session_factory
    engine.dispose()


def test_default_runtime_does_not_create_admin_with_default_password(fresh_db, monkeypatch):
    """A fresh default runtime without configured password must not seed admin1/Admin123."""
    engine, session_factory = fresh_db
    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("AAC_BOOTSTRAP_ADMIN_PASSWORD", raising=False)
    monkeypatch.setattr(config, "ENVIRONMENT", "development")

    from contextlib import contextmanager

    @contextmanager
    def _override_session():
        session = session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    monkeypatch.setattr("src.aac_app.seed.get_session", _override_session)

    # Initialize database as if on first startup
    init_database(ensure_schema=False)

    with _override_session() as session:
        admin = session.query(User).filter(User.user_type == "admin").first()
        assert admin is None, "First-run default runtime must not automatically create an admin user."
        assert session.query(User).filter(User.username == "admin1").first() is None


def test_test_environment_supports_explicit_test_bootstrap(fresh_db, monkeypatch):
    """Explicit test environments continue to support deterministic test credentials."""
    engine, session_factory = fresh_db
    monkeypatch.setenv("TESTING", "1")
    monkeypatch.delenv("AAC_BOOTSTRAP_ADMIN_PASSWORD", raising=False)

    from contextlib import contextmanager

    @contextmanager
    def _override_session():
        session = session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    monkeypatch.setattr("src.aac_app.seed.get_session", _override_session)

    init_database(ensure_schema=False)

    with _override_session() as session:
        admin = session.query(User).filter(User.user_type == "admin").first()
        assert admin is not None
        assert admin.username == "admin1"
        assert verify_password("Admin123", admin.password_hash)


def test_initial_setup_endpoint_lifecycle(fresh_db, monkeypatch):
    """The /api/auth/setup-status and /api/auth/setup endpoints drive first-run onboarding."""
    engine, session_factory = fresh_db
    from src.api.deps import get_db

    def override_get_db():
        session = session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    try:
        # Step 1: Check setup status on fresh DB - setup must be required
        status_res = client.get("/api/auth/setup-status")
        assert status_res.status_code == 200
        assert status_res.json()["setup_required"] is True
        assert status_res.json()["has_admin"] is False

        # Step 2: Attempt setup with mismatched passwords - must fail 400
        mismatch_res = client.post(
            "/api/auth/setup",
            json={
                "username": "admin1",
                "display_name": "System Admin",
                "password": "StrongPassword123!",
                "confirm_password": "DifferentPassword123!",
            },
        )
        assert mismatch_res.status_code == 400
        assert "Passwords do not match" in mismatch_res.json()["detail"]

        # Step 3: Attempt setup with insecure default password (case-insensitive variants) - must fail 400
        for bad_pw in ["Admin123", "admin123", "AdMiN123", "ADMIN123"]:
            default_pw_res = client.post(
                "/api/auth/setup",
                json={
                    "username": "admin1",
                    "display_name": "System Admin",
                    "password": bad_pw,
                    "confirm_password": bad_pw,
                },
            )
            assert default_pw_res.status_code == 400
            assert "development default" in default_pw_res.json()["detail"]

        # Step 4: Attempt setup with weak password (< 8 chars) - must fail 400
        weak_res = client.post(
            "/api/auth/setup",
            json={
                "username": "admin1",
                "display_name": "System Admin",
                "password": "short",
                "confirm_password": "short",
            },
        )
        assert weak_res.status_code == 400

        # Step 5: Attempt setup from non-loopback remote client - must be rejected with 403 Forbidden
        remote_client = TestClient(app, client=("192.168.1.105", 54321))
        remote_res = remote_client.post(
            "/api/auth/setup",
            json={
                "username": "remote_attacker",
                "display_name": "Remote Attacker",
                "password": "StrongPassword123!",
                "confirm_password": "StrongPassword123!",
            },
        )
        assert remote_res.status_code == 403
        assert "local loopback" in remote_res.json()["detail"]

        # Step 6: Successful setup with strong password from loopback client
        setup_res = client.post(
            "/api/auth/setup",
            json={
                "username": "superadmin",
                "display_name": "Primary Administrator",
                "email": "admin@example.com",
                "password": "SecurePassword123!",
                "confirm_password": "SecurePassword123!",
            },
        )
        assert setup_res.status_code == 200
        data = setup_res.json()
        assert data["user"]["username"] == "superadmin"
        assert data["user"]["user_type"] == "admin"
        assert "access_token" in data
        assert "refresh_token" in data

        # Step 7: Setup status must now report setup_required = False
        status_res2 = client.get("/api/auth/setup-status")
        assert status_res2.status_code == 200
        assert status_res2.json()["setup_required"] is False
        assert status_res2.json()["has_admin"] is True

        # Step 8: Subsequent setup attempt must be locked with 403 Forbidden even from loopback
        repeat_res = client.post(
            "/api/auth/setup",
            json={
                "username": "anotheradmin",
                "display_name": "Second Admin",
                "password": "AnotherStrongPassword123!",
                "confirm_password": "AnotherStrongPassword123!",
            },
        )
        assert repeat_res.status_code == 403
        assert "already been completed" in repeat_res.json()["detail"]

    finally:
        app.dependency_overrides.pop(get_db, None)


def test_production_environment_requires_explicit_bootstrap_password(fresh_db, monkeypatch):
    """Production environment refuses to bootstrap an admin when AAC_BOOTSTRAP_ADMIN_PASSWORD is unset."""
    engine, session_factory = fresh_db
    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("AAC_BOOTSTRAP_ADMIN_PASSWORD", raising=False)
    monkeypatch.setattr(config, "ENVIRONMENT", "production")

    from contextlib import contextmanager

    @contextmanager
    def _override_session():
        session = session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    monkeypatch.setattr("src.aac_app.seed.get_session", _override_session)

    with pytest.raises(ValueError, match="AAC_BOOTSTRAP_ADMIN_PASSWORD is not acceptable in production"):
        init_database(ensure_schema=False)

    with _override_session() as session:
        admin = session.query(User).filter(User.user_type == "admin").first()
        assert admin is None, "Production without configured bootstrap password must not seed an admin."


def test_production_environment_with_explicit_password_bootstraps_admin(fresh_db, monkeypatch):
    """Production environment creates admin when explicit strong password is provided."""
    engine, session_factory = fresh_db
    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("AAC_BOOTSTRAP_ADMIN_PASSWORD", "ProductionSuperSecret999!")
    monkeypatch.setattr(config, "ENVIRONMENT", "production")

    from contextlib import contextmanager

    @contextmanager
    def _override_session():
        session = session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    monkeypatch.setattr("src.aac_app.seed.get_session", _override_session)

    init_database(ensure_schema=False)

    with _override_session() as session:
        admin = session.query(User).filter(User.user_type == "admin").first()
        assert admin is not None
        assert admin.username == "admin1"
        assert verify_password("ProductionSuperSecret999!", admin.password_hash)


def test_ensure_bootstrap_admin_script_no_plaintext_persistence(
    tmp_path: Path, monkeypatch, capsys, request
):
    """ensure_bootstrap_admin script reports cleanly without printing or storing plaintext credentials."""
    from scripts import ensure_bootstrap_admin as script_module

    db_file = tmp_path / "script_test.sqlite3"
    db_url = f"sqlite:///{db_file.as_posix()}"
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    request.addfinalizer(engine.dispose)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    from contextlib import contextmanager

    @contextmanager
    def _override_session():
        session = session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    monkeypatch.setattr(script_module, "get_session", _override_session)
    monkeypatch.setattr("src.aac_app.seed.get_session", _override_session)
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(config, "LEGACY_ENV_FILE", tmp_path / "env.properties")
    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("AAC_BOOTSTRAP_ADMIN_PASSWORD", raising=False)
    monkeypatch.setattr(config, "ENVIRONMENT", "development")

    exit_code = script_module.ensure_bootstrap_admin()
    assert exit_code == 0

    captured = capsys.readouterr()
    assert "Admin123" not in captured.out
    assert "Admin123" not in captured.err
    assert "setup" in captured.out.lower()
