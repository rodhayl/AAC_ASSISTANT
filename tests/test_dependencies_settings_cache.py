from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from src.aac_app.models import AppSettings
from src.api.deps import settings as settings_deps
from src.api.main import app
from tests.auth_helpers import create_test_headers

client = TestClient(app)
pytestmark = pytest.mark.usefixtures("setup_test_db")


def test_get_setting_value_queries_database_once_for_repeated_reads(
    test_db_session, monkeypatch
):
    setting = AppSettings(setting_key="cache_test_value", setting_value="cached")
    test_db_session.add(setting)
    test_db_session.commit()

    query_calls = 0
    original_query = test_db_session.query

    def counted_query(*args, **kwargs):
        nonlocal query_calls
        query_calls += 1
        return original_query(*args, **kwargs)

    monkeypatch.setattr(test_db_session, "query", counted_query)

    @contextmanager
    def use_test_session():
        yield test_db_session

    monkeypatch.setattr(settings_deps, "get_session", use_test_session)
    settings_deps.clear_settings_cache()

    assert settings_deps.get_setting_value("cache_test_value") == "cached"
    assert settings_deps.get_setting_value("cache_test_value") == "cached"
    assert query_calls == 1


def test_ai_settings_put_invalidates_cached_setting(
    test_db_session, admin_user, admin_token, monkeypatch
):
    test_db_session.add(
        AppSettings(
            setting_key="ollama_model",
            setting_value="before",
            updated_by=admin_user.id,
        )
    )
    test_db_session.commit()

    @contextmanager
    def use_test_session():
        yield test_db_session

    monkeypatch.setattr(settings_deps, "get_session", use_test_session)
    settings_deps.clear_settings_cache()
    assert settings_deps.get_setting_value("ollama_model") == "before"

    response = client.put(
        "/api/settings/ai",
        headers=create_test_headers(admin_user.id, admin_user.username, "admin"),
        json={"provider": "ollama", "ollama_model": "after"},
    )

    assert response.status_code == 200
    assert settings_deps.get_setting_value("ollama_model") == "after"


def test_transient_failure_does_not_cache_default(test_db_session, monkeypatch):
    """A failed read must return the fallback without poisoning the cache.

    Regression: a transient query error (e.g. the provider-warmup race) used to
    cache the *default* value for the whole process lifetime, permanently
    hiding a configured value stored in the database.
    """
    test_db_session.add(AppSettings(setting_key="stt_model", setting_value="small"))
    test_db_session.commit()

    calls = {"count": 0}

    def flaky_session():
        @contextmanager
        def use_test_session():
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("deque mutated during iteration")
            yield test_db_session

        return use_test_session()

    monkeypatch.setattr(settings_deps, "get_session", flaky_session)
    settings_deps.clear_settings_cache()

    # First call fails -> default is returned but must NOT be cached.
    assert settings_deps.get_setting_value("stt_model", "tiny") == "tiny"
    # Second call retries the query and reaches the configured value.
    assert settings_deps.get_setting_value("stt_model", "tiny") == "small"
