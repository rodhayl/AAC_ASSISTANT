"""Regression tests for startup-time lazy optional dependencies."""

from __future__ import annotations

import subprocess
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_clean_import(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_main_import_does_not_load_optional_heavy_packages() -> None:
    script = """
import sys
import src.api.main

heavy = {
    "fastembed",
    "onnxruntime",
    "faster_whisper",
    "ctranslate2",
    "av",
    "numpy",
}
leaked = sorted(name for name in heavy if name in sys.modules)
assert not leaked, leaked
"""

    result = _run_clean_import(script)

    assert result.returncode == 0, result.stderr or result.stdout


def test_speech_transcription_imports_faster_whisper_on_first_use(monkeypatch) -> None:
    from src.aac_app.providers import local_speech_provider

    class FakeSegment:
        text = "hello"

    class FakeModel:
        def transcribe(self, _path, **_kwargs):
            return iter([FakeSegment()]), object()

    fake_faster_whisper = types.SimpleNamespace(
        WhisperModel=lambda *_args, **_kwargs: FakeModel()
    )
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_faster_whisper)
    monkeypatch.setattr(local_speech_provider, "FASTER_WHISPER_AVAILABLE", True)
    monkeypatch.setattr(local_speech_provider, "faster_whisper", None)

    provider = local_speech_provider.LocalSpeechProvider(lazy_load=True)
    assert provider.model is None

    assert provider.recognize_from_file("sample.wav") == "hello"
    assert provider.model is not None


def test_speech_transcription_never_logs_audio_content(monkeypatch) -> None:
    """A transcribed child answer must never appear verbatim in the logs."""
    from loguru import logger

    from src.aac_app.providers import local_speech_provider

    class FakeSegment:
        text = "confidential child utterance"

    class FakeModel:
        def transcribe(self, _path, **_kwargs):
            return iter([FakeSegment()]), object()

    fake_faster_whisper = types.SimpleNamespace(
        WhisperModel=lambda *_args, **_kwargs: FakeModel()
    )
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_faster_whisper)
    monkeypatch.setattr(local_speech_provider, "FASTER_WHISPER_AVAILABLE", True)
    monkeypatch.setattr(local_speech_provider, "faster_whisper", None)

    captured: list[str] = []
    sink_id = logger.add(
        lambda message: captured.append(str(message)), level="INFO"
    )
    try:
        provider = local_speech_provider.LocalSpeechProvider(lazy_load=True)
        assert (
            provider.recognize_from_file("sample.wav")
            == "confidential child utterance"
        )
    finally:
        logger.remove(sink_id)

    log_text = "\n".join(captured)
    assert "confidential child utterance" not in log_text
    # Only the length is recorded, never the content.
    assert "Transcription result captured" in log_text
    assert "28 chars" in log_text


def test_vector_store_imports_dependencies_on_first_search(monkeypatch, tmp_path) -> None:
    from src.aac_app.services import local_vector_store

    class FakeEmbedder:
        def embed(self, _texts):
            return [[0.0] * 384]

    store = local_vector_store.LocalVectorStore(
        index_path=str(tmp_path / "store.index"),
        metadata_path=str(tmp_path / "store.json"),
        embedder_factory=lambda **_: FakeEmbedder(),
        lazy_load=True,
    )
    assert store.model is None
    assert store.search("hello") == []
    assert store.model is not None


def test_achievement_service_imports_in_clean_process_before_api() -> None:
    """The achievement service must import without src.api being loaded first.

    Regression for the api<->service circular import: the service used to do
    ``from ...api.schemas import ACHIEVEMENT_CRITERIA_TYPES`` while
    src.api.deps.providers imports AchievementSystem, so a script/worker that
    imported the service first blew up with an ImportError. The canonical
    tuple now lives in the models layer, so both import orders must work.
    """
    script = """
from src.aac_app.services.achievement_system import AchievementSystem, _CRITERIA_STAT_KEYS
from src.aac_app.models import ACHIEVEMENT_CRITERIA_TYPES

assert set(_CRITERIA_STAT_KEYS) == set(ACHIEVEMENT_CRITERIA_TYPES)
system = AchievementSystem()
assert isinstance(system, AchievementSystem)
print("service imported cleanly")
"""

    result = _run_clean_import(script)

    assert result.returncode == 0, result.stderr or result.stdout


def test_achievement_service_imports_after_api_in_clean_process() -> None:
    """The api-first import order keeps working with the models-layer tuple."""
    script = """
import src.api.main
from src.aac_app.services.achievement_system import _CRITERIA_STAT_KEYS
from src.aac_app.models import ACHIEVEMENT_CRITERIA_TYPES

assert set(_CRITERIA_STAT_KEYS) == set(ACHIEVEMENT_CRITERIA_TYPES)
print("api-first import ok")
"""

    result = _run_clean_import(script)

    assert result.returncode == 0, result.stderr or result.stdout


def test_prediction_service_loads_bundled_static_ngram_model() -> None:
    script = """
from src.aac_app.services.prediction_service import PredictionService

model = PredictionService()._load_model("en")
assert model["bigrams"]["want"]["cookie"] > model["bigrams"]["want"]["to"]
"""

    result = _run_clean_import(script)

    assert result.returncode == 0, result.stderr or result.stdout


def test_index_all_symbols_reads_existing_metadata_without_loading_model(monkeypatch) -> None:
    from src.aac_app.services import vector_utils

    class MetadataOnlyStore:
        model = None
        metadata = [{"id": 1, "type": "symbol"}]

        def load_index_if_available(self):
            raise AssertionError("metadata was already available")

        def add_texts(self, texts, metadatas):
            raise AssertionError("existing metadata must skip re-indexing")

    store = MetadataOnlyStore()
    monkeypatch.setattr(vector_utils, "get_vector_store", lambda: store)

    vector_utils.index_all_symbols()
