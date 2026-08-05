"""Focused tests for the optional faster-whisper speech provider."""

from __future__ import annotations

import sys
import time
import types
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient

from src.aac_app.providers import local_speech_provider
from src.api.deps import get_llm_provider, get_speech_provider
from src.api.main import app

client = TestClient(app)


class _FakeSegment:
    def __init__(self, text: str):
        self.text = text


def _install_fake_faster_whisper(monkeypatch, *, texts: tuple[str, ...] = ("hello", "world")):
    class FakeModel:
        def __init__(self):
            self.transcribe_calls: list[tuple[str, dict]] = []

        def transcribe(self, path: str, **kwargs):
            self.transcribe_calls.append((path, kwargs))
            return iter(_FakeSegment(text) for text in texts), object()

    fake_model = FakeModel()
    fake_module = types.SimpleNamespace(WhisperModel=lambda *args, **kwargs: fake_model)
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_module)
    monkeypatch.setattr(local_speech_provider, "faster_whisper", None)
    monkeypatch.setattr(local_speech_provider, "FASTER_WHISPER_AVAILABLE", True)
    return fake_model


def test_provider_lazy_loads_faster_whisper_and_joins_segments(monkeypatch, tmp_path):
    fake_model = _install_fake_faster_whisper(monkeypatch)

    provider = local_speech_provider.LocalSpeechProvider(
        lazy_load=True,
        model_cache_dir=tmp_path / "models",
    )

    assert provider.is_available() is True
    assert provider.model is None

    audio_path = tmp_path / "sample.webm"
    audio_path.write_bytes(b"fake audio")
    assert provider.recognize_from_file(str(audio_path)) == "hello world"

    assert provider.model is fake_model
    assert fake_model.transcribe_calls[0][1]["vad_filter"] is True
    assert fake_model.transcribe_calls[0][0] == str(audio_path)
    assert provider.model_cache_dir == tmp_path / "models"


def test_provider_uses_data_models_cache_by_default():
    provider = local_speech_provider.LocalSpeechProvider(lazy_load=True)

    assert provider.model_cache_dir.name == "models"
    assert provider.model_cache_dir.parent.name == "data"


def test_provider_degrades_when_voice_extra_is_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(local_speech_provider, "FASTER_WHISPER_AVAILABLE", False)
    monkeypatch.setattr(local_speech_provider, "faster_whisper", None)

    provider = local_speech_provider.LocalSpeechProvider(
        lazy_load=True,
        model_cache_dir=tmp_path / "models",
    )

    assert provider.is_available() is False
    assert provider.recognize_from_file(str(tmp_path / "invalid.wav")) == ""
    assert provider.is_ready() is False


@pytest.mark.usefixtures("setup_test_db")
def test_voice_answer_gate_uses_availability_before_lazy_model_load(
    regular_user,
    user_token,
):
    """A provider can be available before its model is loaded."""
    llm = Mock()
    llm.generate = AsyncMock(return_value='{"response": "Nice work."}')
    speech = Mock()
    speech.is_available.return_value = True
    speech.model = None
    speech.recognize_from_file.return_value = "hello animals"
    app.dependency_overrides[get_llm_provider] = lambda: llm
    app.dependency_overrides[get_speech_provider] = lambda: speech
    try:
        headers = {"Authorization": f"Bearer {user_token}"}
        started = client.post(
            "/api/learning/start",
            params={"user_id": regular_user.id},
            json={"topic": "animals", "purpose": "practice", "difficulty": "basic"},
            headers=headers,
        )
        assert started.status_code == 200, started.text

        response = client.post(
            f"/api/learning/{started.json()['session_id']}/answer/voice",
            files={"file": ("voice.wav", b"test audio", "audio/wav")},
            headers=headers,
        )

        assert response.status_code == 200, response.text
        assert response.json()["transcription"] == "hello animals"
        speech.recognize_from_file.assert_called_once()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.usefixtures("setup_test_db")
def test_voice_answer_is_graceful_when_provider_is_unavailable(
    regular_user,
    user_token,
):
    """Core-only installs return a normal voice-unavailable answer."""
    llm = Mock()
    llm.generate = AsyncMock(side_effect=RuntimeError("LLM unavailable"))
    speech = Mock()
    speech.is_available.return_value = False
    app.dependency_overrides[get_llm_provider] = lambda: llm
    app.dependency_overrides[get_speech_provider] = lambda: speech
    try:
        headers = {"Authorization": f"Bearer {user_token}"}
        started = client.post(
            "/api/learning/start",
            params={"user_id": regular_user.id},
            json={"topic": "animals", "purpose": "practice", "difficulty": "basic"},
            headers=headers,
        )
        assert started.status_code == 200, started.text

        response = client.post(
            f"/api/learning/{started.json()['session_id']}/answer/voice",
            files={"file": ("voice.wav", b"test audio", "audio/wav")},
            headers=headers,
        )

        data = response.json()
        assert response.status_code == 200
        assert data["success"] is True
        assert data["transcription"] is None
        assert data["is_correct"] is None
        assert data["feedback_message"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.usefixtures("setup_test_db")
def test_voice_status_reports_faster_whisper_and_browser_tts(monkeypatch, admin_token):
    from src.api.routers import providers

    monkeypatch.setattr(providers, "_module_available", lambda name: name == "faster_whisper")
    monkeypatch.setattr(providers, "_voice_auto_install_support", lambda: (True, None))

    response = client.get(
        "/api/providers/voice-status",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["stt"] == {
        "provider": "faster-whisper",
        "installed": True,
        "available": True,
        "model": "small",
    }
    assert "ffmpeg" in data
    assert data["ffmpeg"]["required"] is False
    assert data["tts"]["provider"] == "browser"
    assert data["tts"]["client_side"] is True
    assert data["tts"]["available"] is True
    assert data["actions"]["install_voice"]["supported"] is True


@pytest.mark.usefixtures("setup_test_db")
def test_voice_install_endpoint_short_circuits_when_already_installed(monkeypatch, admin_token):
    from src.api.routers import providers

    monkeypatch.setattr(providers, "_voice_auto_install_support", lambda: (True, None))
    monkeypatch.setattr(providers, "_module_available", lambda name: name == "faster_whisper")

    called = {"run": False}

    def _unexpected_run(*args, **kwargs):
        called["run"] = True
        raise AssertionError("uv sync should not run when faster-whisper is already installed")

    monkeypatch.setattr(providers.subprocess, "run", _unexpected_run)

    response = client.post(
        "/api/providers/voice/install",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    assert response.json()["installed"] is True
    assert called["run"] is False


@pytest.mark.usefixtures("setup_test_db")
def test_voice_install_endpoint_reports_unsupported_environment(monkeypatch, admin_token):
    from src.api.routers import providers

    monkeypatch.setattr(
        providers,
        "_voice_auto_install_support",
        lambda: (False, "Automatic voice installation is unavailable here."),
    )

    response = client.post(
        "/api/providers/voice/install",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Automatic voice installation is unavailable here."


@pytest.mark.voice
def test_real_faster_whisper_transcribes_spoken_wav_with_warm_model():
    """Exercise the real optional provider when the voice extra is installed."""
    pytest.importorskip("faster_whisper")

    fixture = Path(__file__).parent / "fixtures" / "voice_sample.wav"
    if not fixture.exists():
        pytest.skip("spoken WAV fixture is not available")

    provider = local_speech_provider.LocalSpeechProvider()
    if not provider.is_available():
        pytest.skip("faster-whisper is not installed")

    provider.force_load()
    started = time.perf_counter()
    transcription = provider.recognize_from_file(str(fixture))
    elapsed = time.perf_counter() - started

    assert "hello" in transcription.lower()
    assert "animals" in transcription.lower()
    assert elapsed <= 5.0
