"""Tests for the optional local neural TTS (Kokoro) provider and endpoint."""

from unittest.mock import Mock

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


class _FakeTokenizer:
    def phonemize(self, text, lang):
        return f"ph:{text}"


class _FakeKokoro:
    """Minimal stand-in for the kokoro_onnx Kokoro class."""

    def __init__(self, *args, **kwargs):
        self.calls: list[dict] = []
        self.tokenizer = _FakeTokenizer()

    def create(self, text, voice, speed, lang, is_phonemes=False, trim=True):
        self.calls.append(
            {
                "text": text,
                "voice": voice,
                "speed": speed,
                "lang": lang,
                "is_phonemes": is_phonemes,
                "trim": trim,
            }
        )
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


def test_failed_model_download_preserves_existing_file_and_cleans_temp(
    monkeypatch, tmp_path
):
    """A failed network response cannot truncate a previously cached file."""
    import urllib.request

    from src.aac_app.providers import local_tts_provider as mod

    directory = tmp_path / "kokoro"
    directory.mkdir()
    model_path = directory / mod.KOKORO_MODEL_FILENAME
    previous = b"previous model bytes"
    model_path.write_bytes(previous)
    monkeypatch.setattr(mod, "kokoro_model_dir", lambda: directory)

    class FailingResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _size):
            raise OSError("connection interrupted")

    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: FailingResponse(),
    )

    assert mod.download_kokoro_model() is False
    assert model_path.read_bytes() == previous
    assert list(directory.glob(".*.tmp")) == []


def test_provider_reports_unavailable_without_dependency(monkeypatch):
    """Without kokoro-onnx the provider must degrade cleanly (no import crash)."""
    from src.aac_app.providers import local_tts_provider as mod

    monkeypatch.setattr(mod, "_available", False)
    monkeypatch.setattr(mod, "_import_attempted", True)
    monkeypatch.setattr(mod, "model_files_present", lambda: True)

    provider = mod.get_local_tts_provider()
    assert provider.is_available() is False
    assert provider.synthesize("hola", lang="es") is None


def test_provider_warmup_loads_model_when_available(monkeypatch):
    """warmup() loads the model when the engine is available and is idempotent."""
    from src.aac_app.providers import local_tts_provider as mod

    fake = _FakeKokoro()
    calls: list[bool] = []
    monkeypatch.setattr(
        mod.LocalTTSProvider,
        "_ensure_loaded",
        lambda self: (calls.append(True), fake)[1],
    )

    provider = mod.LocalTTSProvider()
    assert provider.warmup() is True
    assert provider.warmup() is True  # repeated warmup is safe
    assert calls == [True, True]


def test_provider_warmup_reports_unavailable(monkeypatch):
    """warmup() returns False without touching the model when unavailable."""
    from src.aac_app.providers import local_tts_provider as mod

    monkeypatch.setattr(mod, "_available", False)
    monkeypatch.setattr(mod, "_import_attempted", True)
    monkeypatch.setattr(mod, "model_files_present", lambda: True)

    provider = mod.get_local_tts_provider()
    assert provider.warmup() is False


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
    # Peak-relative trimming clips soft first-word onsets at speed > 1.
    assert fake.calls[-1]["trim"] is False

    # Male English: en-US -> base 'en' -> am_michael; espeak code 'en-us'
    provider.synthesize("hello", lang="en-US", voice="male")
    assert fake.calls[-1]["voice"] == "am_michael"
    assert fake.calls[-1]["lang"] == "en-us"

    # Explicit kokoro voice name passes through
    provider.synthesize("hola", lang="es", voice="em_alex")
    assert fake.calls[-1]["voice"] == "em_alex"


def test_synthesize_guards_first_word_onset_above_normal_speed(monkeypatch):
    """Legacy path (no PyAV): at speed > 1, pause phonemes shield the first
    word from Kokoro's initial-generation corruption; at normal speed no
    guard is added."""
    from src.aac_app.providers import local_tts_provider as mod

    fake = _FakeKokoro()
    _inject_fake_kokoro(monkeypatch, fake)
    monkeypatch.setattr(mod, "_atempo_available", lambda: False)
    provider = mod.LocalTTSProvider(lazy_load=False)

    provider.synthesize("hola", lang="es", speed=1.0)
    assert fake.calls[-1]["text"] == "ph:hola"
    assert fake.calls[-1]["is_phonemes"] is True
    assert fake.calls[-1]["trim"] is False

    provider.synthesize("hola", lang="es", speed=1.5)
    assert fake.calls[-1]["text"] == ":" * 5 + "ph:hola"
    assert fake.calls[-1]["speed"] == 1.5

    provider.synthesize("hola", lang="es", speed=0.5)
    assert fake.calls[-1]["text"] == "ph:hola"
    assert fake.calls[-1]["speed"] == 0.5


def test_synthesize_stretches_with_atempo_instead_of_model_speed(monkeypatch):
    """Primary path (PyAV present): the model always runs at speed 1.0 —
    its own speed parameter voices the resized BOS token as a phantom
    leading vowel (hexgrad/kokoro#344) — and atempo stretches the result."""
    from src.aac_app.providers import local_tts_provider as mod

    fake = _FakeKokoro()
    _inject_fake_kokoro(monkeypatch, fake)
    monkeypatch.setattr(mod, "_atempo_available", lambda: True)
    stretched: list[tuple[int, float]] = []

    def fake_atempo(samples, sample_rate, speed):
        stretched.append((sample_rate, speed))
        return samples

    monkeypatch.setattr(mod, "_apply_atempo", fake_atempo)
    provider = mod.LocalTTSProvider(lazy_load=False)

    wav = provider.synthesize("hola", lang="es", speed=1.5)
    assert wav is not None and wav[:4] == b"RIFF"
    assert fake.calls[-1]["text"] == "ph:hola"  # no pause-phoneme guard
    assert fake.calls[-1]["speed"] == 1.0
    assert stretched == [(24000, 1.5)]

    # Normal speed never stretches.
    provider.synthesize("hola", lang="es", speed=1.0)
    assert fake.calls[-1]["speed"] == 1.0
    assert stretched == [(24000, 1.5)]


def test_apply_atempo_changes_duration_without_resampling(monkeypatch):
    """The atempo stretch keeps the sample rate and scales the duration."""
    pytest.importorskip("av")
    from src.aac_app.providers import local_tts_provider as mod

    rate = 24000
    t = np.arange(rate // 2, dtype=np.float32) / rate  # 0.5 s tone
    samples = 0.2 * np.sin(2 * np.pi * 220 * t)

    stretched = mod._apply_atempo(samples, rate, 2.0)
    assert len(stretched) < len(samples) * 0.75

    slowed = mod._apply_atempo(samples, rate, 0.5)
    assert len(slowed) > len(samples) * 1.5


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


def test_synthesize_voice_drives_language_and_unknown_voice_fails(monkeypatch):
    """A specific voice selects its own language; unknown names fail explicitly."""
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

    # A browser voiceURI is not a Kokoro voice and must fail explicitly.
    with pytest.raises(ValueError, match="Unknown Kokoro voice"):
        provider.synthesize("hola", lang="es", voice="Google US English")


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
    """With auth but the engine missing the endpoint returns 503.

    Mocked at the router boundary so the result is deterministic in every
    environment: it must not depend on whether kokoro-onnx happens to be
    installed here. A missing engine maps to the "install the TTS extra"
    message (``errors.providers.ttsNotInstalled``), never to the
    "not available" message, which is reserved for an installed engine that
    cannot synthesize.
    """
    provider = Mock()
    provider.is_available.return_value = False
    provider.is_installed.return_value = False
    monkeypatch.setattr(
        "src.api.routers.providers.get_local_tts_provider", lambda: provider
    )

    response = client.post(
        "/api/providers/tts/synthesize",
        json={"text": "hola", "lang": "es", "voice": "female"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 503
    assert "Install the TTS extra" in response.json()["detail"]


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
def test_warmup_endpoint_requires_auth():
    """The batched warmup endpoint requires authentication."""
    response = client.post("/api/providers/warmup")
    assert response.status_code == 401


@pytest.mark.usefixtures("setup_test_db")
def test_warmup_endpoint_noop_when_unavailable(admin_token, monkeypatch):
    """Unavailable targets report not warmed and never load their models."""
    from src.aac_app.providers import local_tts_provider as mod
    from src.api.routers import providers

    loaded: list[bool] = []
    monkeypatch.setattr(mod, "model_files_present", lambda: False)
    monkeypatch.setattr(
        mod.LocalTTSProvider,
        "_ensure_loaded",
        lambda self: (loaded.append(True), None)[1],
    )
    mod.reset_local_tts_provider()
    monkeypatch.setattr(providers, "is_faster_whisper_available", lambda: False)
    monkeypatch.setattr(
        providers.provider_deps,
        "get_speech_provider",
        lambda: Mock(force_load=lambda: loaded.append(True)),
    )
    monkeypatch.setattr(
        providers.provider_deps,
        "get_vector_store",
        lambda: Mock(
            is_available=lambda: False,
            force_load=lambda: loaded.append(True),
            is_ready=lambda: False,
        ),
    )

    response = client.post(
        "/api/providers/warmup",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "tts": {"warmed": False},
        "speech": {"warmed": False},
        "vector": {"warmed": False},
    }
    assert loaded == []


@pytest.mark.usefixtures("setup_test_db")
def test_warmup_endpoint_loads_both_models(admin_token, monkeypatch):
    """Healthy engines are loaded eagerly by the batched warmup endpoint."""
    from src.aac_app.providers import local_tts_provider as mod
    from src.api.routers import providers

    loaded: list[bool] = []
    monkeypatch.setattr(mod, "_available", True)
    monkeypatch.setattr(mod, "_import_attempted", True)
    monkeypatch.setattr(mod, "model_files_present", lambda: True)
    monkeypatch.setattr(
        mod.LocalTTSProvider,
        "_ensure_loaded",
        lambda self: (loaded.append(True), _FakeKokoro())[1],
    )
    mod.reset_local_tts_provider()
    monkeypatch.setattr(providers, "is_faster_whisper_available", lambda: True)
    monkeypatch.setattr(
        providers.provider_deps,
        "get_speech_provider",
        lambda: Mock(force_load=lambda: loaded.append(True)),
    )
    monkeypatch.setattr(
        providers.provider_deps,
        "get_vector_store",
        lambda: Mock(
            is_available=lambda: True,
            force_load=lambda: loaded.append(True),
            is_ready=lambda: True,
        ),
    )

    response = client.post(
        "/api/providers/warmup",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "tts": {"warmed": True},
        "speech": {"warmed": True},
        "vector": {"warmed": True},
    }
    assert loaded == [True, True, True]


@pytest.mark.usefixtures("setup_test_db")
def test_warmup_endpoint_reports_targets_independently(admin_token, monkeypatch):
    """An unavailable target never hides a healthy one."""
    from src.aac_app.providers import local_tts_provider as mod
    from src.api.routers import providers

    loaded: list[bool] = []
    monkeypatch.setattr(mod, "_available", True)
    monkeypatch.setattr(mod, "_import_attempted", True)
    monkeypatch.setattr(mod, "model_files_present", lambda: True)
    monkeypatch.setattr(
        mod.LocalTTSProvider,
        "_ensure_loaded",
        lambda self: (loaded.append(True), _FakeKokoro())[1],
    )
    mod.reset_local_tts_provider()
    monkeypatch.setattr(providers, "is_faster_whisper_available", lambda: False)
    monkeypatch.setattr(
        providers.provider_deps,
        "get_vector_store",
        lambda: Mock(
            is_available=lambda: False,
            force_load=lambda: loaded.append(True),
            is_ready=lambda: False,
        ),
    )

    response = client.post(
        "/api/providers/warmup",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "tts": {"warmed": True},
        "speech": {"warmed": False},
        "vector": {"warmed": False},
    }
    assert loaded == [True]


@pytest.mark.usefixtures("setup_test_db")
def test_warmup_endpoint_targets_filter(admin_token, monkeypatch):
    """The request body can select a subset of targets."""
    from src.aac_app.providers import local_tts_provider as mod
    from src.api.routers import providers

    loaded: list[bool] = []
    monkeypatch.setattr(mod, "_available", True)
    monkeypatch.setattr(mod, "_import_attempted", True)
    monkeypatch.setattr(mod, "model_files_present", lambda: True)
    monkeypatch.setattr(
        mod.LocalTTSProvider,
        "_ensure_loaded",
        lambda self: (loaded.append(True), _FakeKokoro())[1],
    )
    mod.reset_local_tts_provider()
    monkeypatch.setattr(providers, "is_faster_whisper_available", lambda: True)
    monkeypatch.setattr(
        providers.provider_deps,
        "get_speech_provider",
        lambda: Mock(force_load=lambda: loaded.append(True)),
    )

    response = client.post(
        "/api/providers/warmup",
        json={"targets": ["speech"]},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    assert response.json() == {"speech": {"warmed": True}}
    assert loaded == [True]  # only the speech provider loaded


@pytest.mark.usefixtures("setup_test_db")
def test_warmup_endpoint_failure_isolation(admin_token, monkeypatch):
    """A failing target is reported with an error and does not break the rest."""
    from src.aac_app.providers import local_tts_provider as mod
    from src.api.routers import providers

    loaded: list[bool] = []

    def boom(self):
        raise RuntimeError("model exploded")

    monkeypatch.setattr(mod, "_available", True)
    monkeypatch.setattr(mod, "_import_attempted", True)
    monkeypatch.setattr(mod, "model_files_present", lambda: True)
    monkeypatch.setattr(mod.LocalTTSProvider, "_ensure_loaded", boom)
    mod.reset_local_tts_provider()
    monkeypatch.setattr(providers, "is_faster_whisper_available", lambda: True)
    monkeypatch.setattr(
        providers.provider_deps,
        "get_speech_provider",
        lambda: Mock(force_load=lambda: loaded.append(True)),
    )
    monkeypatch.setattr(
        providers.provider_deps,
        "get_vector_store",
        lambda: Mock(
            is_available=lambda: False,
            force_load=lambda: loaded.append(True),
            is_ready=lambda: False,
        ),
    )

    response = client.post(
        "/api/providers/warmup",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["tts"] == {"warmed": False, "error": "model exploded"}
    assert body["speech"] == {"warmed": True}
    assert body["vector"] == {"warmed": False}
    assert loaded == [True]


@pytest.mark.usefixtures("setup_test_db")
def test_warmup_endpoint_vector_reports_ready_state(admin_token, monkeypatch):
    """The vector target reports the model's real ready state, not the call."""
    from src.api.routers import providers

    loaded: list[bool] = []
    monkeypatch.setattr(
        providers.provider_deps,
        "get_vector_store",
        lambda: Mock(
            is_available=lambda: True,
            force_load=lambda: loaded.append(True),
            is_ready=lambda: False,  # fastembed model failed to load
        ),
    )

    response = client.post(
        "/api/providers/warmup",
        json={"targets": ["vector"]},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    assert response.json() == {"vector": {"warmed": False}}
    assert loaded == [True]


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
    # The model is lazy: nothing has warmed it, so it is not loaded yet.
    assert data["tts_local"]["model_loaded"] is False
    assert "actions" in data
    assert "install_tts" in data["actions"]
    # The per-language voice catalog is exposed for the Settings picker.
    voices = data["tts_local"]["voices"]
    assert isinstance(voices, list) and voices
    assert {v["name"] for v in voices} >= {"ef_dora", "em_santa", "em_alex"}
    assert all({"name", "language", "gender"} <= set(v) for v in voices)
