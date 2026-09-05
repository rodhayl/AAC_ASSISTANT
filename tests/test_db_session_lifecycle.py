"""Unit coverage for the real ``get_db`` request-scoped session lifecycle.

``setup_test_db`` overrides ``get_db`` for API tests, so the production
dependency's commit/rollback/close behavior is otherwise never exercised.
These tests drive the real generator against the isolated test engine.
"""
from unittest.mock import patch

import pytest
from sqlalchemy.orm import sessionmaker

from src.aac_app.models import User
from src.api.deps.db import get_db


def _test_factory(test_db_engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=test_db_engine)


def test_get_db_commits_successful_session(test_db_engine):
    with patch(
        "src.api.deps.db.create_session_factory", return_value=_test_factory(test_db_engine)
    ):
        generator = get_db()
        db = next(generator)
        db.add(
            User(
                username="get_db_commit",
                display_name="Commit User",
                user_type="student",
                password_hash="test-hash",
            )
        )
        # Resuming the request-scoped session generator commits the transaction.
        with pytest.raises(StopIteration):
            next(generator)

    with _test_factory(test_db_engine)() as verify:
        assert verify.query(User).filter_by(username="get_db_commit").count() == 1


def test_get_db_rolls_back_on_exception(test_db_engine):
    with patch(
        "src.api.deps.db.create_session_factory", return_value=_test_factory(test_db_engine)
    ):
        generator = get_db()
        db = next(generator)
        db.add(
            User(
                username="get_db_rollback",
                display_name="Rollback User",
                user_type="student",
                password_hash="test-hash",
            )
        )
        with pytest.raises(RuntimeError):
            generator.throw(RuntimeError("boom"))

    with _test_factory(test_db_engine)() as verify:
        assert verify.query(User).filter_by(username="get_db_rollback").count() == 0
