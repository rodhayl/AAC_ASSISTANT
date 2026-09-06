"""The failed-login-attempt table must self-purge (PROMPT_7 D6).

Failed logins hit an unauthenticated endpoint, so every attempt used to
leave a ``FailedLoginAttempt`` row forever (only same-username success or
admin unlock deleted rows). Bombarding random usernames grew the table
without bound. Rows older than the service's own attempt window can never
affect counting or lock state, so the write path now purges them.
"""

from datetime import UTC, datetime, timedelta

from src.aac_app.models.audit_log import FailedLoginAttempt
from src.aac_app.services.lockout_service import AccountLockoutService


def _row(username: str, minutes_ago: int) -> FailedLoginAttempt:
    return FailedLoginAttempt(
        username=username,
        ip_address="127.0.0.1",
        timestamp=datetime.now(UTC) - timedelta(minutes=minutes_ago),
        attempt_count=1,
        locked_until=None,
    )


def test_purge_removes_expired_rows_and_keeps_recent_ones(
    setup_test_db, test_db_session
):
    test_db_session.add_all(
        [_row("stale-a", 90), _row("stale-b", 61), _row("fresh-a", 10)]
    )
    test_db_session.commit()

    AccountLockoutService.record_failed_attempt(test_db_session, "fresh-a")

    usernames = {row.username for row in test_db_session.query(FailedLoginAttempt).all()}
    assert usernames == {"fresh-a"}


def test_lockout_counting_still_works_after_purge(setup_test_db, test_db_session):
    for _ in range(4):
        AccountLockoutService.record_failed_attempt(test_db_session, "victim")

    is_locked, locked_until, _count = AccountLockoutService.record_failed_attempt(
        test_db_session, "victim"
    )

    assert is_locked is True
    assert locked_until is not None


def test_unauthenticated_username_bombardment_stays_bounded(
    setup_test_db, test_db_session
):
    """Attack simulation: unique stale usernames must not accumulate."""
    now = datetime.now(UTC)

    for index in range(50):
        row = FailedLoginAttempt(
            username=f"ghost-{index}",
            ip_address="10.0.0.1",
            timestamp=now - timedelta(minutes=120),
            attempt_count=1,
            locked_until=None,
        )
        test_db_session.add(row)
    test_db_session.commit()

    for index in range(3):
        AccountLockoutService.record_failed_attempt(test_db_session, f"probe-{index}")

    total = test_db_session.query(FailedLoginAttempt).count()
    assert total == 3
