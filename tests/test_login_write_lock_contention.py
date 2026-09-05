"""Regression tests for SQLite write-lock contention fixes.

Two fixes are covered:

1. ``login_for_access_token`` commits its writes (lockout reset + audit)
   inline, before issuing the token, instead of deferring the commit to the
   ``get_db`` teardown.  With the old behavior the request session held
   SQLite's single write lock across token generation; a long-running
   background writer (the ARASAAC library import) blocked holding a read
   snapshot while waiting for the write lock, and the login's teardown commit
   needed the exclusive lock the import was waiting on — a circular wait that
   only broke when one side's 30s busy_timeout fired.  The invariant tested
   here: the login's writes are durable *before* the endpoint returns, so a
   teardown that is blocked (or bypassed) cannot lose them.

2. ``import_arasaac_library`` retries a transient "database is locked" on a
   batch commit instead of aborting the whole import, without duplicating
   rows or files.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from src.aac_app.models import AuditLog, FailedLoginAttempt, Symbol
from src.aac_app.services import arasaac_library_import as import_mod
from src.api.deps import get_db
from src.api.main import app

client = TestClient(app)

pytestmark = pytest.mark.usefixtures("setup_test_db")

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x08\x00\x00\x00\x08\x08\x06"
    b"\x00\x00\x00\xc4\x0f\xbe\x8b\x00\x00\x00\x0bIDAT\x08\xd7c\xf8\xff\xff?\x03"
    b"\x05\x00\t\xfb\x02\xfe\x8a\xd0\xb7V\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _login(username: str = "admin_test", password: str = "TestPassword123"):
    return client.post(
        "/api/auth/token",
        data={"username": username, "password": password},
    )


def test_successful_login_persists_writes_independent_of_teardown(
    test_db_engine, admin_user
):
    """Login writes are committed inline, not by the get_db teardown.

    Override get_db with a teardown that deliberately does NOT commit (the
    shape of a teardown blocked by SQLite write-lock contention, or one that
    rolls back).  Before the fix, the audit insert and lockout reset were
    only flushed inside the request session and persisted by the teardown
    commit, so they would be lost here; the fix commits them before the token
    is issued, so they survive regardless of teardown behavior.
    """
    # Pre-seed a failed-attempt row so reset_attempts has something to delete.

    factory = sessionmaker(
        bind=test_db_engine, expire_on_commit=False, autocommit=False, autoflush=False
    )
    with factory() as seed:
        seed.add(FailedLoginAttempt(username="admin_test", attempt_count=3))
        seed.commit()

    def override_get_db():
        session = factory()
        try:
            yield session
            # Deliberately no commit and no rollback: simulates a teardown
            # that is stuck waiting on the SQLite write lock.
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = _login()
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200, response.text

    # The writes were committed inside the endpoint, before teardown: they
    # are visible from an independent session.
    with factory() as check:
        audit_count = (
            check.query(AuditLog)
            .filter(AuditLog.event_type == "login_success")
            .count()
        )
        attempt_count = (
            check.query(FailedLoginAttempt)
            .filter(FailedLoginAttempt.username == "admin_test")
            .count()
        )
    assert audit_count == 1
    assert attempt_count == 0


def test_successful_login_writes_are_durable_after_teardown_commit(
    test_db_session, admin_user
):
    """Sanity: with the normal teardown commit the writes still persist."""
    test_db_session.add(
        FailedLoginAttempt(username="admin_test", attempt_count=1)
    )
    test_db_session.commit()

    response = _login()
    assert response.status_code == 200, response.text

    test_db_session.expire_all()
    audit_count = (
        test_db_session.query(AuditLog)
        .filter(AuditLog.event_type == "login_success")
        .count()
    )
    assert audit_count == 1


# ---------------------------------------------------------------------------
# ARASAAC import lock-retry regression
# ---------------------------------------------------------------------------

def _override_get_session(test_db_session):
    @contextmanager
    def override():
        try:
            yield test_db_session
            test_db_session.commit()
        except Exception:
            test_db_session.rollback()
            raise

    return override


def _fake_service(catalog):
    class FakeService:
        async def list_all_symbols(self, locale="es"):
            return catalog

        async def download_symbol_image_500(self, arasaac_id):
            return PNG_BYTES

        async def close(self):
            return None

    return FakeService


def test_import_retries_transient_database_locked_without_duplicating_rows(
    test_db_session, monkeypatch, tmp_path
):
    """A transient "database is locked" on one batch is retried, not fatal."""
    catalog = [
        {
            "_id": 3001,
            "keywords": [{"keyword": "casa", "meaning": "building"}],
            "categories": ["home"],
        },
        {
            "_id": 3002,
            "keywords": [{"keyword": "sol", "meaning": "star"}],
            "categories": ["nature"],
        },
    ]

    success_get_session = _override_get_session(test_db_session)
    calls = {"count": 0}

    def flaky_get_session():
        # Call 1 = _existing_labels() (must succeed); call 2 = the batch
        # commit (fails once with a lock error, then succeeds on retry).
        calls["count"] += 1
        if calls["count"] == 2:
            raise OperationalError(
                "INSERT INTO symbols", {}, Exception("database is locked")
            )
        return success_get_session()

    monkeypatch.setattr(import_mod, "get_session", flaky_get_session)
    monkeypatch.setattr(import_mod, "ArasaacService", _fake_service(catalog))
    monkeypatch.setattr(import_mod.config, "UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(import_mod, "_LOCK_RETRY_DELAY_SECONDS", 0)

    summary = asyncio.run(import_mod.import_arasaac_library("es"))

    assert summary == {"imported": 2, "failed": 0, "skipped": 0}
    rows = test_db_session.query(Symbol).filter(
        Symbol.label.in_(["casa", "sol"])
    ).all()
    assert len(rows) == 2
    # Only one row per term — a failed-then-retried batch must not duplicate.
    assert len(test_db_session.query(Symbol).filter(Symbol.label == "casa").all()) == 1


def test_import_gives_up_after_retry_exhaustion(
    test_db_session, monkeypatch, tmp_path
):
    """Persistent lock contention raises after the retry budget is exhausted."""
    catalog = [
        {
            "_id": 4001,
            "keywords": [{"keyword": "pan", "meaning": "bread"}],
            "categories": ["food"],
        },
    ]

    success_get_session = _override_get_session(test_db_session)
    calls = {"count": 0}

    def always_locked():
        calls["count"] += 1
        # Only fail on the batch commit (call 2+); allow the initial read.
        if calls["count"] >= 2:
            raise OperationalError("INSERT", {}, Exception("database is locked"))
        return success_get_session()

    monkeypatch.setattr(import_mod, "get_session", always_locked)
    monkeypatch.setattr(import_mod, "ArasaacService", _fake_service(catalog))
    monkeypatch.setattr(import_mod.config, "UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(import_mod, "_LOCK_RETRY_DELAY_SECONDS", 0)

    with pytest.raises(OperationalError):
        asyncio.run(import_mod.import_arasaac_library("es"))

    assert test_db_session.query(Symbol).filter(Symbol.label == "pan").count() == 0
