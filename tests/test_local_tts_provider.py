"""Tests for the optional local neural TTS (Kokoro) provider and endpoint."""

import numpy as np
import pytest
from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_local_tts_singleton():
    """Drop the provider singleton between tests."""
    from src.aac_app.providers import local_tts_provider as mod

    mod.reset_local_tts_provider()
    yield
    mod.reset_local_tts_provider()


class _FakeKokoro:
    """Minimal stand-in for the kokoro_onnx Kokoro class."""

    def __init__(self, *args, **kwargs):
        self.calls: list[dict] = []

    def create(self, text, voice, speed, lang):
        self.calls.append({"text": text, "voice": voice, "speed": speed, "lang": lang})
        return np.zeros(12000, dtype=np.float32), 24000


def _inject_fake_kokoro(monkeypatch, model: _FakeKokoro) -> None:
    """Make the provider believe kokoro is installed and return ``model``."""
    from src.aac_app.providers import local_tts_provider as mod

    monkeypatch.setattr(mod, "_available", True)
    monkeypatch.setattr(mod, "_import_attempted", True)
    monkeypatch.setattr(mod, "model_files_present", lambda: True)
    monkeypatch.setattr(
        mod.LocalTTSProvider,
        "_ensure_loaded",
        lambda self: model,
    )


def test_model_cache_permission_errors_degrade_to_unavailable(monkeypatch):
    """A broken model cache must not make provider status fail with 500."""
    from src.aac_app.providers import local_tts_provider as mod

    class BrokenPath:
        def is_file(self):
            raise OSError("cache is unavailable")

    monkeypatch.setattr(mod, "kokoro_model_path", lambda: BrokenPath())
    assert mod.model_files_present() is False


def test_provider_reports_unavailable_without_dependency(monkeypatch):
    """Without kokoro-onnx the provider must degrade cleanly (no import crash)."""
    from src.aac_app.providers import local_tts_provider as mod

    monkeypatch.setattr(mod, "_available", False)
    monkeypatch.setattr(mod, "_import_attempted", True)
    monkeypatch.setattr(mod, "model_files_present", lambda: True)

    provider = mod.get_local_tts_provider()
    assert provider.is_available() is False
    assert provider.synthesize("hola", lang="es") is None


def test_provider_voice_resolution_and_wav_encoding(monkeypatch):
    """Voice style resolution and WAV encoding work with a fake kokoro model."""
    from src.aac_app.providers import local_tts_provider as mod

    fake = _FakeKokoro()
    _inject_fake_kokoro(monkeypatch, fake)

    provider = mod.LocalTTSProvider(lazy_load=False)

    # Female Spanish: es-ES -> base 'es' -> ef_dora; espeak code 'es'
    wav = provider.synthesize("hola", lang="es-ES", voice="female")
    assert wav is not None
    assert wav[:4] == b"RIFF"  # valid WAV header
    assert fake.calls[-1]["voice"] == "ef_dora"
    assert fake.calls[-1]["lang"] == "es"

    # Male English: en-US -> base 'en' -> am_michael; espeak code 'en-us'
    provider.synthesize("hello", lang="en-US", voice="male")
    assert fake.calls[-1]["voice"] == "am_michael"
    assert fake.calls[-1]["lang"] == "en-us"

    # Explicit kokoro voice name passes through
    provider.synthesize("hola", lang="es", voice="em_alex")
    assert fake.calls[-1]["voice"] == "em_alex"


def test_list_kokoro_voices_returns_catalog(monkeypatch):
    """The voice catalog is deterministic and covers the Spanish voices."""
    from src.aac_app.providers import local_tts_provider as mod

    # Force the static fallback catalog so the test is independent of whether
    # the real model pack is downloaded on this machine.
    monkeypatch.setattr(mod, "_pack_voice_names", lambda: None)

    voices = mod.list_kokoro_voices()
    assert isinstance(voices, list) and voices
    names = {v["name"] for v in voices}
    assert {"ef_dora", "em_santa", "em_alex"} <= names
    assert {"af_sarah", "am_michael"} <= names

    ef_dora = next(v for v in voices if v["name"] == "ef_dora")
    assert ef_dora["language"] == "es"
    assert ef_dora["gender"] == "female"
    em_santa = next(v for v in voices if v["name"] == "em_santa")
    assert em_santa["language"] == "es"
    assert em_santa["gender"] == "male"

    # American English voices carry a region; Spanish voices do not.
    af_sarah = next(v for v in voices if v["name"] == "af_sarah")
    assert af_sarah["region"] == "american"
    assert ef_dora["region"] is None

    # Catalog is sorted by language then name for stable optgroups.
    languages = [v["language"] for v in voices]
    assert languages == sorted(languages)


def test_synthesize_voice_drives_language_and_unknown_voice_falls_back(monkeypatch):
    """A specific voice selects its own language; unknown names degrade safely."""
    from src.aac_app.providers import local_tts_provider as mod

    fake = _FakeKokoro()
    _inject_fake_kokoro(monkeypatch, fake)
    provider = mod.LocalTTSProvider(lazy_load=False)

    # A specific Spanish voice speaks Spanish even when the UI language is en.
    provider.synthesize("hola", lang="en-US", voice="ef_dora")
    assert fake.calls[-1]["voice"] == "ef_dora"
    assert fake.calls[-1]["lang"] == "es"

    # A male English voice drives English espeak code.
    provider.synthesize("hello", lang="es", voice="am_michael")
    assert fake.calls[-1]["voice"] == "am_michael"
    assert fake.calls[-1]["lang"] == "en-us"

    # An unknown name (e.g. a browser voiceURI leaking through) degrades to
    # the requested language's default instead of failing synthesis.
    provider.synthesize("hola", lang="es", voice="Google US English")
    assert fake.calls[-1]["voice"] == "ef_dora"
    assert fake.calls[-1]["lang"] == "es"


@pytest.mark.usefixtures("setup_test_db")
def test_tts_synthesize_endpoint_requires_auth(admin_token):
    """The synthesize endpoint requires authentication."""
    response = client.post(
        "/api/providers/tts/synthesize",
        json={"text": "hola", "lang": "es"},
    )
    assert response.status_code == 401


@pytest.mark.usefixtures("setup_test_db")
def test_tts_synthesize_endpoint_degrades_when_engine_missing(
    admin_token, monkeypatch
):
    """With auth but the engine unavailable the endpoint returns 503."""
    from src.aac_app.providers import local_tts_provider as mod

    monkeypatch.setattr(mod, "model_files_present", lambda: False)
    mod.reset_local_tts_provider()

    response = client.post(
        "/api/providers/tts/synthesize",
        json={"text": "hola", "lang": "es", "voice": "female"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 503
    assert "not available" in response.json()["detail"].lower()


@pytest.mark.usefixtures("setup_test_db")
def test_tts_synthesize_endpoint_returns_wav(admin_token, monkeypatch):
    """A healthy engine returns a playable WAV via the endpoint."""
    from src.aac_app.providers import local_tts_provider as mod

    _inject_fake_kokoro(monkeypatch, _FakeKokoro())
    mod.reset_local_tts_provider()

    response = client.post(
        "/api/providers/tts/synthesize",
        json={"text": "hola mundo", "lang": "es", "voice": "female"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")
    assert response.content[:4] == b"RIFF"
    assert len(response.content) > 100


@pytest.mark.usefixtures("setup_test_db")
def test_voice_status_reports_local_tts(admin_token):
    """voice-status exposes the local TTS capability block."""
    response = client.get(
        "/api/providers/voice-status",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "tts_local" in data
    assert data["tts_local"]["provider"] == "kokoro"
    assert "actions" in data
    assert "install_tts" in data["actions"]
    # The per-language voice catalog is exposed for the Settings picker.
    voices = data["tts_local"]["voices"]
    assert isinstance(voices, list) and voices
    assert {v["name"] for v in voices} >= {"ef_dora", "em_santa", "em_alex"}
    assert all({"name", "language", "gender"} <= set(v) for v in voices)
