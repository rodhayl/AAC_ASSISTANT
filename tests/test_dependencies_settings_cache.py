from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from src.aac_app.models import AppSettings
from src.api.deps import settings as settings_deps
from src.api.main import app
from tests.test_utils_auth import create_test_headers

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
