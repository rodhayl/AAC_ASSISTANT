"""Real-case API coverage for the providers install flow and TTS branches.

The automatic install endpoints are Windows-only; these tests simulate the
Windows runtime with mocks to exercise the lock acquisition, uv invocation,
error mapping, and success responses without running real subprocesses.
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)

pytestmark = pytest.mark.usefixtures("setup_test_db")


def _mock_windows_runtime(monkeypatch, uv_path="/fake/uv"):
    """Simulate a source checkout on Windows with uv on PATH."""
    monkeypatch.setattr("src.api.routers.providers.sys.platform", "win32")
    monkeypatch.setattr("src.config.IS_FROZEN", False)
    # The real project root contains pyproject.toml, satisfying the
    # source-checkout requirement.
    monkeypatch.setattr(
        "src.api.routers.providers._uv_command", lambda: uv_path
    )


@pytest.fixture
def admin_headers(admin_user, admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


def test_uv_command_finds_uv(monkeypatch):
    """_uv_command returns the first uv executable that exists on disk."""
    import shutil

    from src.api.routers.providers import _uv_command

    real_uv = shutil.which("uv")
    assert real_uv, "uv must be on PATH to test _uv_command"
    monkeypatch.setattr(
        "src.api.routers.providers.shutil.which",
        lambda name: real_uv if name == "uv" else None,
    )
    assert _uv_command() == real_uv


def test_voice_install_success_path(admin_headers, monkeypatch):
    """Simulated Windows install invokes uv and reports success."""
    _mock_windows_runtime(monkeypatch)
    with patch(
        "src.api.routers.providers.is_faster_whisper_available",
        side_effect=[False, True],  # not installed before, installed after
    ), patch(
        "src.api.routers.providers.subprocess.run",
        return_value=MagicMock(),
    ) as run_mock:
        response = client.post(
            "/api/providers/voice/install", headers=admin_headers
        )
    assert response.status_code == 200
    assert response.json()["installed"] is True
    assert run_mock.call_args.args[0] == ["/fake/uv", "sync", "--extra", "voice"]


def test_voice_install_subprocess_failure_maps_to_500(
    admin_headers, monkeypatch
):
    """A failing uv invocation surfaces as a 500 with a stable message."""
    _mock_windows_runtime(monkeypatch)
    with patch(
        "src.api.routers.providers.is_faster_whisper_available", return_value=False
    ), patch(
        "src.api.routers.providers.subprocess.run",
        side_effect=__import__("subprocess").CalledProcessError(1, "uv"),
    ):
        response = client.post(
            "/api/providers/voice/install", headers=admin_headers
        )
    assert response.status_code == 500


def test_tts_install_success_path(admin_headers, monkeypatch):
    """Simulated Windows TTS install syncs the extra and downloads the model."""
    _mock_windows_runtime(monkeypatch)
    with patch(
        "src.api.routers.providers.get_local_tts_provider",
        return_value=MagicMock(is_installed=lambda: True, is_available=lambda: True),
    ), patch(
        "src.api.routers.providers.model_files_present", side_effect=[False, True]
    ), patch(
        "src.api.routers.providers.subprocess.run", return_value=MagicMock()
    ), patch(
        # download_kokoro_model is imported lazily inside the route.
        "src.aac_app.providers.local_tts_provider.download_kokoro_model",
        return_value=True,
    ) as download_mock:
        response = client.post(
            "/api/providers/tts/install", headers=admin_headers
        )
    assert response.status_code == 200
    assert response.json()["installed"] is True
    download_mock.assert_called_once()


def test_tts_install_reports_409_when_already_running(
    admin_headers, monkeypatch
):
    """A concurrent install request is refused with 409."""
    _mock_windows_runtime(monkeypatch)
    from src.api.routers import providers as providers_module

    busy_lock = MagicMock()
    busy_lock.acquire.return_value = False
    monkeypatch.setattr(providers_module, "_tts_download_lock", busy_lock)
    response = client.post("/api/providers/tts/install", headers=admin_headers)
    assert response.status_code == 409


def test_tts_synthesize_failure_returns_503(admin_headers, monkeypatch):
    """When the local engine fails to produce audio, return 503."""
    provider = MagicMock()
    provider.is_available.return_value = True
    provider.synthesize.return_value = None
    monkeypatch.setattr(
        "src.api.routers.providers.get_local_tts_provider", lambda: provider
    )
    response = client.post(
        "/api/providers/tts/synthesize",
        json={"text": "Hola", "lang": "es"},
        headers=admin_headers,
    )
    assert response.status_code == 503


def test_tts_synthesize_success_returns_wav(admin_headers, monkeypatch):
    """A successful synthesis returns the WAV bytes with no-store caching."""
    provider = MagicMock()
    provider.is_available.return_value = True
    provider.synthesize.return_value = b"RIFF-wave-bytes"
    monkeypatch.setattr(
        "src.api.routers.providers.get_local_tts_provider", lambda: provider
    )
    response = client.post(
        "/api/providers/tts/synthesize",
        json={"text": "Hola", "lang": "es", "voice": "ef_dora", "speed": 1.2},
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.content == b"RIFF-wave-bytes"
    assert response.headers["cache-control"] == "no-store"


def test_lmstudio_models_success(admin_headers, monkeypatch):
    """An available LM Studio returns its model list."""
    from unittest.mock import AsyncMock

    provider = MagicMock()
    provider.is_available.return_value = True
    provider.get_available_models = AsyncMock(return_value={"data": [{"id": "m1"}]})
    monkeypatch.setattr(
        "src.api.routers.providers.get_lmstudio_provider", lambda: provider
    )
    response = client.get(
        "/api/providers/ai/models/lmstudio", headers=admin_headers
    )
    assert response.status_code == 200
    assert response.json() == {"models": [{"id": "m1"}]}
