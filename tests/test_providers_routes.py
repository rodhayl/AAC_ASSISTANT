"""Real-case API coverage for the providers router (src/api/routers/providers.py).

Covers the provider health summary, STT model selection (valid and invalid),
the guarded automatic-install endpoints (which are unsupported on non-Windows
runtimes), and the LM Studio model listing fallbacks.
"""
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.aac_app.models import AppSettings
from src.api.main import app

client = TestClient(app)

pytestmark = pytest.mark.usefixtures("setup_test_db")


def test_providers_health_reports_all_providers(
    admin_user, admin_token, monkeypatch
):
    """Health summarizes ollama/openrouter/lmstudio without raising."""
    for name in ("ollama", "openrouter", "lmstudio"):
        mock = MagicMock()
        mock.is_available.return_value = False
        mock.is_configured.return_value = False
        monkeypatch.setattr(
            f"src.api.routers.providers.get_{name}_provider", lambda m=mock: m
        )

    response = client.get(
        "/api/providers/health", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"ollama", "openrouter", "lmstudio"}
    assert data["openrouter"]["reason"] == "api_key_missing"
    assert data["lmstudio"]["reason"] == "base_url_missing"


def test_update_stt_model_rejects_unsupported_model(admin_user, admin_token):
    response = client.put(
        "/api/providers/stt/model",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"model": "gigantic"},
    )
    assert response.status_code == 400
    assert "supported_models" in response.json()["detail"]


def test_update_stt_model_persists_selection(
    setup_test_db, test_db_session, admin_user, admin_token
):
    response = client.put(
        "/api/providers/stt/model",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"model": "small"},
    )
    assert response.status_code == 200
    assert response.json()["model"] == "small"

    setting = (
        test_db_session.query(AppSettings)
        .filter(AppSettings.setting_key == "stt_model")
        .first()
    )
    assert setting is not None
    assert setting.setting_value == "small"


def test_update_stt_model_updates_existing_value(
    setup_test_db, test_db_session, admin_user, admin_token
):
    test_db_session.add(
        AppSettings(setting_key="stt_model", setting_value="tiny", updated_by=admin_user.id)
    )
    test_db_session.commit()

    response = client.put(
        "/api/providers/stt/model",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"model": "base"},
    )
    assert response.status_code == 200
    rows = (
        test_db_session.query(AppSettings)
        .filter(AppSettings.setting_key == "stt_model")
        .all()
    )
    assert len(rows) == 1
    assert rows[0].setting_value == "base"


def test_tts_install_unsupported_on_linux(admin_user, admin_token, monkeypatch):
    """On non-Windows runtimes, automatic TTS install is refused with 400."""
    monkeypatch.setattr("src.api.routers.providers.sys.platform", "linux")
    response = client.post(
        "/api/providers/tts/install",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 400


def test_voice_install_unsupported_on_linux(admin_user, admin_token, monkeypatch):
    monkeypatch.setattr("src.api.routers.providers.sys.platform", "linux")
    response = client.post(
        "/api/providers/voice/install",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 400


def test_lmstudio_models_unavailable_returns_empty(
    admin_user, admin_token, monkeypatch
):
    mock = MagicMock()
    mock.is_available.return_value = False
    monkeypatch.setattr("src.api.routers.providers.get_lmstudio_provider", lambda: mock)

    response = client.get(
        "/api/providers/ai/models/lmstudio",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    assert response.json() == {"models": [], "error": "LM Studio is not available"}


def test_lmstudio_models_error_returns_empty_list(
    admin_user, admin_token, monkeypatch
):
    def _boom():
        raise RuntimeError("connection refused")

    monkeypatch.setattr("src.api.routers.providers.get_lmstudio_provider", _boom)
    response = client.get(
        "/api/providers/ai/models/lmstudio",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    assert response.json()["models"] == []
    assert "connection refused" in response.json()["error"]
