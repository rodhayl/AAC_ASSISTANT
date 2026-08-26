"""Focused tests for the optional faster-whisper speech provider."""

from __future__ import annotations

import io
import sys
import threading
import time
import types
import wave
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient

from src.aac_app.providers import local_speech_provider
from src.aac_app.providers.local_speech_provider import DEFAULT_STT_MODEL, SUPPORTED_STT_MODELS
from src.api.deps import get_llm_provider, get_speech_provider
from src.api.main import app

client = TestClient(app)


def _minimal_wav() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b"\x00\x00" * 80)
    return buffer.getvalue()


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


def test_stt_model_catalog_defaults_to_tiny_and_normalizes_unknown_values():
    assert DEFAULT_STT_MODEL == "tiny"
    assert set(SUPPORTED_STT_MODELS) == {"tiny", "base", "small", "medium", "large-v3"}
    assert local_speech_provider.normalize_stt_model(None) == "tiny"
    assert local_speech_provider.normalize_stt_model("unknown") == "tiny"
    assert local_speech_provider.LocalSpeechProvider(model_size="small", lazy_load=True).model_size == "small"
    assert local_speech_provider.LocalSpeechProvider(model_size="Whisper-Tiny", lazy_load=True).model_size == "tiny"


@pytest.mark.usefixtures("setup_test_db")
def test_admin_can_select_supported_stt_model_and_status_persists(admin_token):
    response = client.put(
        "/api/providers/stt/model",
        json={"model": "small"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    assert response.json()["model"] == "small"
    assert set(response.json()["models"]) == set(SUPPORTED_STT_MODELS)

    status_response = client.get(
        "/api/providers/voice-status",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert status_response.status_code == 200
    assert status_response.json()["stt"]["model"] == "small"
    assert status_response.json()["stt"]["models"]["small"]["selected"] is True


@pytest.mark.usefixtures("setup_test_db")
def test_stt_model_selection_rejects_unknown_models_and_non_admins(
    admin_token,
    user_token,
):
    invalid_response = client.put(
        "/api/providers/stt/model",
        json={"model": "whisper-tiny"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert invalid_response.status_code == 400
    assert set(invalid_response.json()["detail"]["supported_models"]) == set(SUPPORTED_STT_MODELS)

    forbidden_response = client.put(
        "/api/providers/stt/model",
        json={"model": "base"},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert forbidden_response.status_code == 403


def test_speech_singleton_rebuilds_when_global_model_setting_changes(monkeypatch):
    from src.api.deps import providers as provider_deps

    created_models: list[str] = []
    configured = {"value": "tiny"}

    class FakeSpeechProvider:
        def __init__(self, model_size: str):
            self.model_size = model_size
            created_models.append(model_size)

    monkeypatch.setattr(
        provider_deps,
        "_get_setting_value",
        lambda key, default="": configured["value"] if key == "stt_model" else default,
    )
    monkeypatch.setattr(provider_deps, "LocalSpeechProvider", FakeSpeechProvider)
    monkeypatch.setattr(provider_deps, "_speech_provider", None)

    first = provider_deps.get_speech_provider()
    configured["value"] = "small"
    second = provider_deps.get_speech_provider()
    third = provider_deps.get_speech_provider()

    assert created_models == ["tiny", "small"]
    assert first.model_size == "tiny"
    assert second.model_size == "small"
    assert third is second


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


def test_concurrent_first_use_loads_faster_whisper_once(monkeypatch, tmp_path):
    """Concurrent voice requests wait for one lazy model load."""
    load_started = threading.Event()
    release_load = threading.Event()
    load_count = 0
    load_wait_succeeded: list[bool] = []
    load_count_lock = threading.Lock()

    class BlockingModel:
        def transcribe(self, _path: str, **_kwargs):
            return iter([_FakeSegment("hello")]), object()

    def create_model(*_args, **_kwargs):
        nonlocal load_count
        with load_count_lock:
            load_count += 1
        load_started.set()
        load_wait_succeeded.append(release_load.wait(timeout=2))
        return BlockingModel()

    monkeypatch.setitem(
        sys.modules,
        "faster_whisper",
        types.SimpleNamespace(WhisperModel=create_model),
    )
    monkeypatch.setattr(local_speech_provider, "faster_whisper", None)
    monkeypatch.setattr(local_speech_provider, "FASTER_WHISPER_AVAILABLE", True)
    provider = local_speech_provider.LocalSpeechProvider(
        lazy_load=True,
        model_cache_dir=tmp_path / "models",
    )

    results: list[str] = []

    def transcribe() -> None:
        results.append(provider.recognize_from_file("sample.wav"))

    first = threading.Thread(target=transcribe)
    second = threading.Thread(target=transcribe)
    first.start()
    assert load_started.wait(timeout=2), "first request did not start model loading"
    second.start()
    time.sleep(0.05)
    release_load.set()
    first.join(timeout=2)
    second.join(timeout=2)

    assert not first.is_alive() and not second.is_alive()
    assert load_count == 1
    assert load_wait_succeeded == [True]
    assert results == ["hello", "hello"]


def test_release_waits_for_in_flight_transcription(monkeypatch, tmp_path):
    """Replacing a provider cannot close its native model mid-transcription."""
    transcription_started = threading.Event()
    release_transcription = threading.Event()
    model_closed = threading.Event()
    release_finished = threading.Event()

    class BlockingModel:
        def transcribe(self, _path: str, **_kwargs):
            transcription_started.set()
            release_transcription.wait(timeout=2)
            return iter([_FakeSegment("hello")]), object()

        def close(self):
            model_closed.set()

    model = BlockingModel()
    monkeypatch.setitem(
        sys.modules,
        "faster_whisper",
        types.SimpleNamespace(WhisperModel=lambda *_args, **_kwargs: model),
    )
    monkeypatch.setattr(local_speech_provider, "faster_whisper", None)
    monkeypatch.setattr(local_speech_provider, "FASTER_WHISPER_AVAILABLE", True)
    provider = local_speech_provider.LocalSpeechProvider(
        lazy_load=True,
        model_cache_dir=tmp_path / "models",
    )
    result: list[str] = []
    transcriber = threading.Thread(
        target=lambda: result.append(provider.recognize_from_file("sample.wav")),
    )
    transcriber.start()
    assert transcription_started.wait(timeout=2)

    release_started = threading.Event()

    def release_provider() -> None:
        release_started.set()
        provider.release()
        release_finished.set()

    releaser = threading.Thread(target=release_provider)
    releaser.start()
    assert release_started.wait(timeout=2)
    assert not release_finished.is_set()

    release_transcription.set()
    transcriber.join(timeout=2)
    releaser.join(timeout=2)

    assert not transcriber.is_alive() and not releaser.is_alive()
    assert result == ["hello"]
    assert release_finished.is_set()
    assert model_closed.is_set()


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
            files={"file": ("voice.wav", _minimal_wav(), "audio/wav")},
            headers=headers,
        )

        assert response.status_code == 200, response.text
        assert response.json()["transcription"] == "hello animals"
        speech.recognize_from_file.assert_called_once()

        invalid_upload = client.post(
            f"/api/learning/{started.json()['session_id']}/answer/voice",
            files={"file": ("voice.txt", b"not audio", "text/plain")},
            headers=headers,
        )
        assert invalid_upload.status_code == 400
        invalid_detail = invalid_upload.json()["detail"]
        assert not invalid_detail.startswith("errors.")
        assert "audio" in invalid_detail.lower()
        assert "image" not in invalid_detail.lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.usefixtures("setup_test_db")
def test_voice_answer_reports_provider_unavailable(
    regular_user,
    user_token,
):
    """Core-only installs reject voice answers when speech recognition is unavailable."""
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
            files={"file": ("voice.wav", _minimal_wav(), "audio/wav")},
            headers=headers,
        )

        data = response.json()
        assert response.status_code == 400
        assert data["detail"] == "Voice transcription failed"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.usefixtures("setup_test_db")
def test_voice_status_reports_faster_whisper_and_browser_tts(monkeypatch, admin_token):
    from src.api.routers import providers

    monkeypatch.setattr(providers, "is_faster_whisper_available", lambda: True)
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
        "model_loaded": False,
        "model": "tiny",
        "models": {
            name: {**details, "selected": name == "tiny"}
            for name, details in SUPPORTED_STT_MODELS.items()
        },
    }
    assert "ffmpeg" in data
    assert data["ffmpeg"]["required"] is False
    assert data["tts"]["provider"] == "browser"
    assert data["tts"]["client_side"] is True
    assert data["tts"]["available"] is True
    assert data["actions"]["install_voice"]["supported"] is True
    assert set(data["stt"]["models"]) == set(SUPPORTED_STT_MODELS)
    assert data["stt"]["models"]["tiny"]["selected"] is True


@pytest.mark.usefixtures("setup_test_db")
def test_voice_install_endpoint_short_circuits_when_already_installed(monkeypatch, admin_token):
    from src.api.routers import providers

    monkeypatch.setattr(providers, "_voice_auto_install_support", lambda: (True, None))
    monkeypatch.setattr(providers, "is_faster_whisper_available", lambda: True)

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

    # The tiny model is intentionally optimized for speed and may vary in
    # punctuation/word choice across CPU and faster-whisper versions. Verify
    # reliable speech extraction rather than pinning one unstable hallucinated
    # word from this short fixture.
    assert transcription.strip()
    assert "hello" in transcription.lower()
    assert elapsed <= 5.0
