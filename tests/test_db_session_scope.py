"""Regression tests for shared service-session transaction ownership."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.aac_app import db
from src.aac_app.models import Base, SymbolUsageLog, User
from src.aac_app.services.symbol_analytics import SymbolAnalytics


def test_session_scope_keeps_supplied_transaction_caller_owned():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    with db.session_scope(session) as scoped:
        scoped.add(
            SymbolUsageLog(
                user_id=1,
                symbol_label="hello",
                position_in_utterance=0,
                utterance_length=1,
            )
        )
        scoped.flush()

    assert session.query(SymbolUsageLog).count() == 1
    session.rollback()
    assert session.query(SymbolUsageLog).count() == 0
    session.close()
    engine.dispose()


def test_symbol_analytics_without_session_commits_internally(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    user_session = factory()
    user_session.add(
        User(
            username="analytics-user",
            password_hash="test",
            display_name="Analytics User",
        )
    )
    user_session.commit()
    user_session.close()

    monkeypatch.setattr(db, "create_session_factory", lambda: factory)
    analytics = SymbolAnalytics()

    assert analytics.log_symbol_usage(
        user_id=1,
        symbols=[{"label": "hello", "category": "social"}],
    )

    session = factory()
    try:
        assert session.query(SymbolUsageLog).count() == 1
    finally:
        session.close()
        engine.dispose()


def test_symbol_analytics_with_session_does_not_commit():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    session = factory()
    session.add(
        User(
            username="analytics-user",
            password_hash="test",
            display_name="Analytics User",
        )
    )
    session.commit()
    analytics = SymbolAnalytics()

    assert analytics.log_symbol_usage(
        user_id=1,
        symbols=[{"label": "hello", "category": "social"}],
        db=session,
    )
    session.rollback()
    assert session.query(SymbolUsageLog).count() == 0
    session.close()
    engine.dispose()


def test_symbol_analytics_skips_unknown_user_without_poisoning_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    assert SymbolAnalytics().log_symbol_usage(
        user_id=999,
        symbols=[{"label": "hello", "category": "social"}],
        db=session,
    )
    assert session.query(SymbolUsageLog).count() == 0
    session.rollback()
    session.close()
    engine.dispose()
