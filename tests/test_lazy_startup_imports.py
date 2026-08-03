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
    "torch",
    "whisper",
    "sentence_transformers",
    "faiss",
    "pyttsx3",
    "sounddevice",
    "soundfile",
    "webrtcvad",
    "numpy",
    "deep_translator",
}
leaked = sorted(name for name in heavy if name in sys.modules)
assert not leaked, leaked
"""

    result = _run_clean_import(script)

    assert result.returncode == 0, result.stderr or result.stdout


def test_tts_provider_import_and_constructor_are_lazy() -> None:
    script = """
import builtins

optional_imports = {"pyttsx3"}
real_import = builtins.__import__
seen = []

def tracking_import(name, *args, **kwargs):
    if name.split(".", 1)[0] in optional_imports:
        seen.append(name)
    return real_import(name, *args, **kwargs)

builtins.__import__ = tracking_import
from src.aac_app.providers.local_tts_provider import LocalTTSProvider

provider = LocalTTSProvider()
assert provider.engine is None
assert not seen, seen
"""

    result = _run_clean_import(script)

    assert result.returncode == 0, result.stderr or result.stdout


def test_tts_synthesize_imports_engine_on_first_use(monkeypatch) -> None:
    from src.aac_app.providers import local_tts_provider

    class FakeEngine:
        def __init__(self):
            self.spoken = []

        def setProperty(self, _name, _value):
            return None

        def getProperty(self, name):
            return [] if name == "voices" else None

        def say(self, text):
            self.spoken.append(text)

        def runAndWait(self):
            return None

    engine = FakeEngine()
    fake_pyttsx3 = types.SimpleNamespace(init=lambda: engine)
    monkeypatch.setitem(sys.modules, "pyttsx3", fake_pyttsx3)
    monkeypatch.setattr(local_tts_provider, "PYTTSX3_AVAILABLE", True)
    monkeypatch.setattr(local_tts_provider, "pyttsx3", None)

    provider = local_tts_provider.LocalTTSProvider()
    assert provider.engine is None

    provider.synthesize("hello", blocking=True)

    assert provider.engine is engine
    assert engine.spoken == ["hello"]


def test_speech_transcription_imports_whisper_on_first_use(monkeypatch) -> None:
    from src.aac_app.providers import local_speech_provider

    class FakeModel:
        def transcribe(self, _path, **_kwargs):
            return {"text": "hello"}

    fake_whisper = types.SimpleNamespace(load_model=lambda *_args, **_kwargs: FakeModel())
    monkeypatch.setitem(sys.modules, "whisper", fake_whisper)
    monkeypatch.setattr(local_speech_provider, "WHISPER_AVAILABLE", True)
    monkeypatch.setattr(local_speech_provider, "whisper", None)

    provider = local_speech_provider.LocalSpeechProvider(lazy_load=True)
    assert provider.model is None

    assert provider.recognize_from_file("sample.wav") == "hello"
    assert provider.model is not None


def test_vector_store_imports_dependencies_on_first_search(monkeypatch, tmp_path) -> None:
    import numpy as numpy_module

    from src.aac_app.services import local_vector_store

    class FakeIndex:
        ntotal = 0

    class FakeFaiss(types.ModuleType):
        def __init__(self):
            super().__init__("faiss")

        @staticmethod
        def IndexFlatL2(_dimension):
            return FakeIndex()

    class FakeSentenceTransformers(types.ModuleType):
        def __init__(self):
            super().__init__("sentence_transformers")

        @staticmethod
        def SentenceTransformer(_name, device):
            return object()

    monkeypatch.setitem(sys.modules, "faiss", FakeFaiss())
    monkeypatch.setitem(sys.modules, "sentence_transformers", FakeSentenceTransformers())
    monkeypatch.setattr(local_vector_store, "FAISS_AVAILABLE", True)
    monkeypatch.setattr(local_vector_store, "SENTENCE_TRANSFORMERS_AVAILABLE", True)
    monkeypatch.setattr(local_vector_store, "NUMPY_AVAILABLE", True)
    monkeypatch.setattr(local_vector_store, "faiss", None)
    monkeypatch.setattr(local_vector_store, "SentenceTransformer", None)
    monkeypatch.setattr(local_vector_store, "np", None)

    store = local_vector_store.LocalVectorStore(
        index_path=str(tmp_path / "store.index"),
        metadata_path=str(tmp_path / "store.json"),
        lazy_load=True,
    )
    assert store.model is None
    assert store.search("hello") == []
    assert store.model is not None
    assert store.index is not None
    assert local_vector_store.np is numpy_module


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
