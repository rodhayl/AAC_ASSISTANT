"""Schema migration and award-race regression tests (PROMPT_6 D10).

Older databases allowed duplicate ``user_achievements`` rows, which
double-counted leaderboard points. The migration must deduplicate (keeping
the earliest award) and enforce the user/achievement unique invariant at the
database boundary, matching the existing board_assignments/student_teachers
pattern. The award route must report a lost award race as 400, never 500.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.aac_app.models import Achievement, User, UserAchievement
from src.aac_app.schema import ensure
from src.aac_app.services.achievement_system import AchievementSystem
from src.api.main import app
from tests.auth_helpers import create_test_headers

client = TestClient(app)


def test_user_achievements_migration_dedups_and_enforces_unique(tmp_path):
    """Legacy duplicate award rows collapse to the earliest and stay unique."""
    engine = __import__("sqlalchemy").create_engine(
        f"sqlite:///{(tmp_path / 'legacy.db').as_posix()}"
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE user_achievements ("
                "id INTEGER PRIMARY KEY, "
                "user_id INTEGER NOT NULL, "
                "achievement_id INTEGER NOT NULL, "
                "earned_at DATETIME, "
                "progress FLOAT)"
            )
        )
        conn.execute(
            text("INSERT INTO user_achievements (id, user_id, achievement_id) VALUES (1, 7, 3)")
        )
        conn.execute(
            text("INSERT INTO user_achievements (id, user_id, achievement_id) VALUES (2, 7, 3)")
        )
        conn.execute(
            text("INSERT INTO user_achievements (id, user_id, achievement_id) VALUES (3, 8, 3)")
        )

    ensure(engine)

    with engine.connect() as conn:
        # The duplicate (user 7, achievement 3) collapses to its earliest row.
        assert conn.execute(text("SELECT COUNT(*) FROM user_achievements")).scalar() == 2
        kept = conn.execute(
            text("SELECT id FROM user_achievements WHERE user_id = 7")
        ).scalar()
        assert kept == 1

        index_sql = conn.execute(
            text(
                "SELECT sql FROM sqlite_master "
                "WHERE type = 'index' AND name = 'uq_user_achievements_user_achievement'"
            )
        ).scalar()
        assert index_sql is not None and "UNIQUE" in index_sql.upper()

        # The invariant is enforced at the database boundary from now on.
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO user_achievements (id, user_id, achievement_id) "
                    "VALUES (9, 7, 3)"
                )
            )

    engine.dispose()


def test_award_race_returns_400_not_500(test_db_session, test_db_engine, admin_token):
    """A lost concurrent-award race reports the conflict, not a server error.

    The commit is forced to raise the integrity error a losing concurrent
    award would produce; without the route's IntegrityError handling this
    escapes as an unhandled exception instead of a 400 response.
    """
    student = User(
        username="award_race_student",
        display_name="Award race student",
        user_type="student",
        password_hash="not-used-in-this-test",
        is_active=True,
    )
    achievement = Achievement(name="award_race_achievement", points=10)
    test_db_session.add_all([student, achievement])
    test_db_session.commit()

    from src.api.deps import get_db

    def override_get_db():
        session = Session(bind=test_db_engine)

        def losing_commit():
            raise IntegrityError(
                "INSERT INTO user_achievements",
                {},
                Exception(
                    "UNIQUE constraint failed: user_achievements.user_id, "
                    "user_achievements.achievement_id"
                ),
            )

        session.commit = losing_commit
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = client.post(
            f"/api/achievements/{achievement.id}/award",
            json={"user_id": student.id},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 400, response.text
    assert response.json()["detail"]


def test_check_batch_survives_lost_award_race(test_db_session, admin_user, monkeypatch):
    """A conflicting award in the batch skips cleanly; the rest are granted.

    Two concurrent checks can both read "not yet earned" and then race on the
    user/achievement unique constraint. Pre-fix the losing flush poisoned the
    whole session (PendingRollbackError on the batch's final flush → 500) and
    discarded the legitimate awards. The criteria guard is bypassed here as
    the deterministic stand-in for that lost pre-read; the already-earned
    ``First Steps`` row makes the award insert hit the real constraint.
    """
    from src.aac_app.services.achievement_catalog import PREDEFINED_ACHIEVEMENTS

    monkeypatch.setattr(
        AchievementSystem,
        "_check_achievement_criteria",
        lambda self, *args, **kwargs: True,
    )

    first = PREDEFINED_ACHIEVEMENTS["first_steps"]
    earned = Achievement(
        name=first["name"],
        description=first["description"],
        category=first["category"],
        criteria_type=first["criteria_type"],
        criteria_value=first["criteria_value"],
        points=first["points"],
        icon=first["icon"],
    )
    test_db_session.add(earned)
    test_db_session.commit()
    test_db_session.add(
        UserAchievement(user_id=admin_user.id, achievement_id=earned.id)
    )
    test_db_session.commit()

    headers = create_test_headers(admin_user.id, admin_user.username, "admin")
    response = client.post(
        f"/api/achievements/user/{admin_user.id}/check", headers=headers
    )

    assert response.status_code == 200, response.text
    # The already-earned achievement was not double awarded.
    duplicate_rows = (
        test_db_session.query(UserAchievement)
        .filter(
            UserAchievement.user_id == admin_user.id,
            UserAchievement.achievement_id == earned.id,
        )
        .count()
    )
    assert duplicate_rows == 1
    # The rest of the batch was still granted (def + award rows for the other
    # catalog achievements the race did not touch).
    granted = (
        test_db_session.query(UserAchievement)
        .filter(UserAchievement.user_id == admin_user.id)
        .count()
    )
    assert granted == len(PREDEFINED_ACHIEVEMENTS)
