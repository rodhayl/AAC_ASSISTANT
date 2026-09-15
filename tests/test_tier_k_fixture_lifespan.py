"""Tier K (H24) — test-fixture fidelity.

The shared ``client`` fixture must run the real ASGI lifespan (startup and
shutdown), and ``setup_test_db`` must point the *process-wide* database seam at
the test database instead of patching a handful of call sites.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from src.aac_app.models import User
from src.api.main import app


def test_client_fixture_runs_startup(client):
    """The ``client`` fixture must have executed the app's startup phase."""
    assert app.state.lifespan_active is True
    assert app.state.database_ready is True
    assert app.state.shutdown_event.is_set() is False


def test_lifespan_shutdown_clears_active_state(test_db_session):
    """Exiting the TestClient context must run the shutdown phase."""
    with TestClient(app):
        assert app.state.lifespan_active is True
    assert app.state.lifespan_active is False


def test_setup_test_db_points_the_shared_factory_at_the_test_database(
    setup_test_db, test_db_engine, test_db_session
):
    """``create_session_factory`` (the single seam all services resolve) is test-bound."""
    from src.aac_app import db as db_module

    factory = db_module.create_session_factory()
    with factory() as session:
        assert session.get_bind() is test_db_engine


def test_module_bound_get_session_reaches_the_test_database(
    setup_test_db, test_db_session
):
    """A service the old four-patch list missed still uses the test database.

    ``vector_utils`` binds ``get_session`` at import time; before H24 it
    resolved against the uninitialised process-wide engine.
    """
    from src.aac_app.services.vector_utils import get_session

    test_db_session.add(
        User(
            username="lifespan_seam_user",
            email="lifespan-seam@test.com",
            password_hash="x",
            display_name="Lifespan Seam",
            user_type="standard",
            is_active=True,
        )
    )
    test_db_session.commit()

    with get_session() as session:
        count = session.scalar(
            select(func.count())
            .select_from(User)
            .where(User.username == "lifespan_seam_user")
        )

    assert count == 1
