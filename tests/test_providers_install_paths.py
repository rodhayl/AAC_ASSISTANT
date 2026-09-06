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


def test_uv_command_returns_none_when_uv_missing(monkeypatch, tmp_path):
    """_uv_command returns None when no uv executable is discoverable."""
    from src.api.routers.providers import _uv_command

    monkeypatch.setattr(
        "src.api.routers.providers.shutil.which", lambda name: None
    )
    monkeypatch.setattr(
        "src.api.routers.providers.Path.home",
        lambda: tmp_path / "no-such-home",
    )
    assert _uv_command() is None


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


def test_tts_synthesize_unknown_voice_returns_400_not_500(
    admin_headers, monkeypatch
):
    """An invented voice is a 400 client error, never an unhandled 500."""
    provider = MagicMock()
    provider.is_available.return_value = True

    def _boom(*args, **kwargs):
        raise ValueError("Unknown Kokoro voice: nope")

    provider.synthesize.side_effect = _boom
    monkeypatch.setattr(
        "src.api.routers.providers.get_local_tts_provider", lambda: provider
    )

    response = client.post(
        "/api/providers/tts/synthesize",
        json={"text": "Hola", "lang": "es", "voice": "nope"},
        headers=admin_headers,
    )
    assert response.status_code == 400
    provider.synthesize.assert_not_called()


def test_tts_synthesize_unknown_voice_is_400_even_without_engine(
    admin_headers, monkeypatch
):
    """Voice validation runs before engine availability: 400, not 503/500."""
    provider = MagicMock()
    provider.is_available.return_value = False
    provider.is_installed.return_value = False
    monkeypatch.setattr(
        "src.api.routers.providers.get_local_tts_provider", lambda: provider
    )

    response = client.post(
        "/api/providers/tts/synthesize",
        json={"text": "Hola", "voice": "nope"},
        headers=admin_headers,
    )
    assert response.status_code == 400


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


def test_voice_auto_install_support_platform_limits(monkeypatch):
    """Auto-install is refused on non-Windows, frozen builds, no checkout or no uv."""
    from src.api.routers import providers as providers_module
    from src.api.routers.providers import _voice_auto_install_support

    # Non-Windows runtime.
    monkeypatch.setattr(providers_module.sys, "platform", "linux")
    supported, reason = _voice_auto_install_support()
    assert supported is False
    assert "Windows" in reason

    # Frozen packaged app.
    monkeypatch.setattr(providers_module.sys, "platform", "win32")
    monkeypatch.setattr("src.config.IS_FROZEN", True)
    supported, reason = _voice_auto_install_support()
    assert supported is False
    assert "packaged" in reason

    # Missing source checkout (no pyproject.toml).
    monkeypatch.setattr("src.config.IS_FROZEN", False)
    monkeypatch.setattr(
        "src.api.routers.providers.config.PROJECT_ROOT",
        __import__("pathlib").Path("/nonexistent-checkout"),
    )
    supported, reason = _voice_auto_install_support()
    assert supported is False
    assert "source checkout" in reason

    # uv not available.
    monkeypatch.setattr(
        "src.api.routers.providers.config.PROJECT_ROOT",
        __import__("pathlib").Path.cwd(),
    )
    monkeypatch.setattr("src.api.routers.providers._uv_command", lambda: None)
    supported, reason = _voice_auto_install_support()
    assert supported is False
    assert "uv is not available" in reason


def test_install_endpoints_refuse_unsupported_runtime(admin_headers, monkeypatch):
    """Both install endpoints return 400 when auto-install is unsupported."""
    monkeypatch.setattr("src.api.routers.providers.sys.platform", "linux")
    response = client.post("/api/providers/tts/install", headers=admin_headers)
    assert response.status_code == 400
    response = client.post("/api/providers/voice/install", headers=admin_headers)
    assert response.status_code == 400


def test_tts_synthesize_503_with_install_hints(admin_headers, monkeypatch):
    """Unavailable TTS reports the missing-extra or missing-model hint."""
    provider = MagicMock()
    provider.is_available.return_value = False
    provider.is_installed.return_value = False
    monkeypatch.setattr(
        "src.api.routers.providers.get_local_tts_provider", lambda: provider
    )
    res = client.post(
        "/api/providers/tts/synthesize",
        json={"text": "Hola", "lang": "es"},
        headers=admin_headers,
    )
    assert res.status_code == 503
    assert "Install the TTS extra" in res.json()["detail"]

    provider.is_installed.return_value = True
    monkeypatch.setattr(
        "src.api.routers.providers.model_files_present", lambda: False
    )
    res = client.post(
        "/api/providers/tts/synthesize",
        json={"text": "Hola", "lang": "es"},
        headers=admin_headers,
    )
    assert res.status_code == 503
    assert "Kokoro model has not been downloaded" in res.json()["detail"]


def test_tts_install_runs_uv_sync_when_not_installed(admin_headers, monkeypatch):
    """A missing tts extra triggers uv sync and provider reset."""
    _mock_windows_runtime(monkeypatch)
    with patch(
        "src.api.routers.providers.get_local_tts_provider",
        return_value=MagicMock(
            is_installed=lambda: False, is_available=lambda: True
        ),
    ), patch(
        "src.api.routers.providers.model_files_present", return_value=True
    ), patch(
        "src.api.routers.providers.subprocess.run", return_value=MagicMock()
    ) as run_mock, patch(
        "src.api.routers.providers.provider_deps.reset_providers"
    ) as reset_mock:
        response = client.post(
            "/api/providers/tts/install", headers=admin_headers
        )
    assert response.status_code == 200
    assert run_mock.call_args.args[0] == ["/fake/uv", "sync", "--extra", "tts"]
    reset_mock.assert_called_once()


def test_tts_install_model_download_failure_maps_to_500(admin_headers, monkeypatch):
    """A failed Kokoro download surfaces as a 500."""
    _mock_windows_runtime(monkeypatch)
    with patch(
        "src.api.routers.providers.get_local_tts_provider",
        return_value=MagicMock(is_installed=lambda: True),
    ), patch(
        "src.api.routers.providers.model_files_present", return_value=False
    ), patch(
        "src.aac_app.providers.local_tts_provider.download_kokoro_model",
        return_value=False,
    ):
        response = client.post(
            "/api/providers/tts/install", headers=admin_headers
        )
    assert response.status_code == 500


def test_tts_install_subprocess_failure_maps_to_500(admin_headers, monkeypatch):
    """A failing uv sync for the tts extra surfaces as a 500."""
    _mock_windows_runtime(monkeypatch)
    with patch(
        "src.api.routers.providers.get_local_tts_provider",
        return_value=MagicMock(is_installed=lambda: False),
    ), patch(
        "src.api.routers.providers.subprocess.run",
        side_effect=__import__("subprocess").CalledProcessError(2, "uv"),
    ):
        response = client.post(
            "/api/providers/tts/install", headers=admin_headers
        )
    assert response.status_code == 500
    assert "Automatic TTS installation failed" in response.json()["detail"]


def test_tts_install_generic_failure_maps_to_500(admin_headers, monkeypatch):
    """Any other install failure surfaces as a 500 with the error detail."""
    _mock_windows_runtime(monkeypatch)
    with patch(
        "src.api.routers.providers.get_local_tts_provider",
        return_value=MagicMock(is_installed=lambda: True),
    ), patch(
        "src.api.routers.providers.model_files_present", return_value=False
    ), patch(
        "src.aac_app.providers.local_tts_provider.download_kokoro_model",
        side_effect=RuntimeError("boom"),
    ):
        response = client.post(
            "/api/providers/tts/install", headers=admin_headers
        )
    assert response.status_code == 500
    # Stable client message; the raw exception is not echoed to the client.
    assert "Automatic TTS installation failed" in response.json()["detail"]
    assert "boom" not in response.json()["detail"]


def test_voice_install_409_when_lock_busy(admin_headers, monkeypatch):
    """A concurrent voice install is refused with 409."""
    _mock_windows_runtime(monkeypatch)
    from src.api.routers import providers as providers_module

    busy_lock = MagicMock()
    busy_lock.acquire.return_value = False
    monkeypatch.setattr(providers_module, "_voice_install_lock", busy_lock)
    with patch(
        "src.api.routers.providers.is_faster_whisper_available", return_value=False
    ):
        response = client.post(
            "/api/providers/voice/install", headers=admin_headers
        )
    assert response.status_code == 409


def test_voice_install_400_when_uv_missing(admin_headers, monkeypatch):
    """A Windows checkout without uv on PATH returns 400."""
    _mock_windows_runtime(monkeypatch, uv_path=None)
    with patch(
        "src.api.routers.providers.is_faster_whisper_available", return_value=False
    ):
        response = client.post(
            "/api/providers/voice/install", headers=admin_headers
        )
    assert response.status_code == 400
    assert "uv is not available" in response.json()["detail"]


def test_voice_install_400_when_uv_disappears_after_support_check(
    admin_headers, monkeypatch
):
    """The route-level uv guard refuses when uv vanishes mid-request."""
    _mock_windows_runtime(monkeypatch)
    uv_results = iter(["/fake/uv", None])
    monkeypatch.setattr(
        "src.api.routers.providers._uv_command", lambda: next(uv_results)
    )
    with patch(
        "src.api.routers.providers.is_faster_whisper_available", return_value=False
    ):
        response = client.post(
            "/api/providers/voice/install", headers=admin_headers
        )
    assert response.status_code == 400
    assert "uv is not available" in response.json()["detail"]
