"""AuditLog is write-only, so retention must be bounded (PROMPT_12 D8).

``AuditLog`` rows are written on every login outcome and admin action but
nothing reads the table (lockout uses ``FailedLoginAttempt`` instead). With
no reader, unbounded growth would be pure waste; the successful-login path
now trims the oldest rows beyond ``AUDIT_LOG_MAX_ROWS`` in bounded batches.
"""

from sqlalchemy.orm import sessionmaker

from src.aac_app.models import User
from src.aac_app.models.audit_log import AuditLog
from src.aac_app.services.audit_service import (
    AUDIT_LOG_MAX_ROWS,
    AUDIT_LOG_PURGE_BATCH,
    AuditLogService,
)
from src.aac_app.services.auth_service import get_password_hash


def _seed_rows(session, count: int) -> list[AuditLog]:
    rows = [
        AuditLog(
            event_type="login_failed",
            severity="warning",
            username=f"ghost-{i}",
            description=f"seed row {i}",
            success=False,
        )
        for i in range(count)
    ]
    session.add_all(rows)
    session.commit()
    return rows


def test_purge_old_entries_trims_oldest_beyond_cap(setup_test_db, test_db_session):
    _seed_rows(test_db_session, 120)

    deleted = AuditLogService.purge_old_entries(
        test_db_session, max_rows=100, batch_limit=500
    )

    assert deleted == 20
    remaining_ids = [
        row.id for row in test_db_session.query(AuditLog.id).order_by(AuditLog.id)
    ]
    assert len(remaining_ids) == 100
    # The 20 newest survive; the 20 oldest are gone.
    assert remaining_ids[0] == 21
    assert remaining_ids[-1] == 120


def test_purge_old_entries_respects_batch_limit_and_converges(
    setup_test_db, test_db_session
):
    _seed_rows(test_db_session, 120)

    first = AuditLogService.purge_old_entries(
        test_db_session, max_rows=100, batch_limit=5
    )
    assert first == 5

    second = AuditLogService.purge_old_entries(
        test_db_session, max_rows=100, batch_limit=5
    )
    assert second == 5

    # Repeated passes converge to the cap.
    while True:
        deleted = AuditLogService.purge_old_entries(
            test_db_session, max_rows=100, batch_limit=5
        )
        if deleted == 0:
            break
    assert test_db_session.query(AuditLog).count() == 100


def test_purge_old_entries_is_noop_below_cap(setup_test_db, test_db_session):
    _seed_rows(test_db_session, 50)

    deleted = AuditLogService.purge_old_entries(
        test_db_session, max_rows=100, batch_limit=500
    )

    assert deleted == 0
    assert test_db_session.query(AuditLog).count() == 50


def test_successful_login_trims_audit_log_to_bounded_cap(
    setup_test_db, test_db_engine
):
    """The real login path runs the purge: > cap rows converge to the cap."""
    from fastapi.testclient import TestClient

    from src.api.main import app

    # Seed rows beyond the cap in a dedicated session over the same engine the
    # API requests will use.
    session_factory = sessionmaker(bind=test_db_engine)
    seed_session = session_factory()
    try:
        _seed_rows(seed_session, AUDIT_LOG_MAX_ROWS + AUDIT_LOG_PURGE_BATCH)
        seed_session.add(
            User(
                username="audit_login_user",
                email="audit_login@test.com",
                password_hash=get_password_hash("TestPassword123"),
                user_type="admin",
                is_active=True,
                display_name="Audit Login",
            )
        )
        seed_session.commit()
    finally:
        seed_session.close()

    with TestClient(app) as client:
        def _login():
            response = client.post(
                "/api/auth/token",
                data={"username": "audit_login_user", "password": "TestPassword123"},
            )
            assert response.status_code == 200, response.text

        # First login appends one row and purges a single bounded batch of the
        # oldest excess (not the whole excess at once).
        _login()
        verify_session = session_factory()
        try:
            assert verify_session.query(AuditLog).count() == (
                AUDIT_LOG_MAX_ROWS + 1
            )
        finally:
            verify_session.close()

        # A second login converges the table to exactly the cap.
        _login()

    verify_session = session_factory()
    try:
        total = verify_session.query(AuditLog).count()
        # Each login-success row survives (never purged as "oldest" while the
        # seeded rows still exceed the cap) and the table is bounded at the cap.
        assert total == AUDIT_LOG_MAX_ROWS
        login_rows = (
            verify_session.query(AuditLog)
            .filter(AuditLog.event_type == "login_success")
            .count()
        )
        assert login_rows == 2
    finally:
        verify_session.close()
