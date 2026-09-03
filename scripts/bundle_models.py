"""Download optional AI models into the release bundle for offline packaging.

Usage:
    uv run python scripts/bundle_models.py [--output DIR] [--stt-model tiny]

Downloads the fastembed semantic-search model, the faster-whisper
speech-to-text model, and the Kokoro text-to-speech model files into a single
directory. The release build bundles that directory under ``models`` so the
packaged application works fully offline; ``build_package.bat`` runs this
before PyInstaller.

The download is skipped when the target cache directories already exist, so
rebuilds are idempotent.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make direct execution work from the repository root:
# ``uv run python scripts/bundle_models.py``.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loguru import logger

from src.aac_app.providers.local_speech_provider import DEFAULT_STT_MODEL  # noqa: E402
from src.aac_app.providers.local_tts_provider import (  # noqa: E402
    KOKORO_MODEL_FILENAME,
    KOKORO_VOICES_FILENAME,
    download_kokoro_model,
)
from src.aac_app.services.local_vector_store import MODEL_NAME  # noqa: E402


def _fastembed_ready(cache_dir: Path) -> bool:
    """Return whether the fastembed model cache already exists."""
    return (cache_dir / "models--qdrant--all-MiniLM-L6-v2-onnx").is_dir()


def _whisper_ready(cache_dir: Path, stt_model: str) -> bool:
    """Return whether the faster-whisper model cache already exists."""
    return (cache_dir / f"models--Systran--faster-whisper-{stt_model}").is_dir()


def _kokoro_ready(bundle_models_dir: Path) -> bool:
    """Return whether both Kokoro model files are present in the bundle."""
    return (
        (bundle_models_dir / "kokoro" / KOKORO_MODEL_FILENAME).is_file()
        and (bundle_models_dir / "kokoro" / KOKORO_VOICES_FILENAME).is_file()
    )


def _download_kokoro_to_bundle(bundle_models_dir: Path) -> bool:
    """Download Kokoro model files into the bundle directory.

    Uses the existing ``download_kokoro_model`` function, which normally
    writes to ``data/models/kokoro``. We temporarily redirect the model
    directory by patching ``kokoro_model_dir``.
    """
    import src.aac_app.providers.local_tts_provider as tts_mod

    kokoro_dir = bundle_models_dir / "kokoro"
    kokoro_dir.mkdir(parents=True, exist_ok=True)

    original = tts_mod.kokoro_model_dir
    tts_mod.kokoro_model_dir = lambda: kokoro_dir
    try:
        return download_kokoro_model()
    finally:
        tts_mod.kokoro_model_dir = original


def _download_step(label: str, ready: bool, action) -> bool:
    """Run one model download unless its cache is already present.

    Returns True when the model is ready (previously cached or just
    downloaded). Any download failure is logged and reported as False so
    ``download_all`` can finish the remaining models before failing.
    """
    if ready:
        logger.info("{} already cached; skipping download", label)
        return True
    try:
        return bool(action())
    except Exception as exc:  # noqa: BLE001 - report any download failure
        logger.error("Failed to download {}: {}", label, exc)
        return False


def _download_fastembed(output_dir: Path) -> bool:
    from fastembed import TextEmbedding

    logger.info("Downloading fastembed model '{}' into {}", MODEL_NAME, output_dir)
    TextEmbedding(model_name=MODEL_NAME, cache_dir=str(output_dir), lazy_load=True)
    logger.success("fastembed model ready")
    return True


def _download_whisper(output_dir: Path, stt_model: str) -> bool:
    from faster_whisper import WhisperModel

    logger.info("Downloading faster-whisper '{}' into {}", stt_model, output_dir)
    WhisperModel(
        stt_model,
        device="cpu",
        compute_type="int8",
        download_root=str(output_dir),
    )
    logger.success("faster-whisper '{}' ready", stt_model)
    return True


def _download_kokoro_bundle(output_dir: Path) -> bool:
    logger.info("Downloading Kokoro model files into {}", output_dir / "kokoro")
    if _download_kokoro_to_bundle(output_dir):
        logger.success("Kokoro model files ready")
        return True
    logger.error("Kokoro model download did not produce valid files")
    return False


def download_all(output_dir: Path, stt_model: str = DEFAULT_STT_MODEL) -> bool:
    """Download all models into ``output_dir``; returns True when all are ready."""
    from functools import partial

    output_dir.mkdir(parents=True, exist_ok=True)

    steps = (
        ("fastembed model", _fastembed_ready(output_dir), partial(_download_fastembed, output_dir)),
        (
            f"faster-whisper '{stt_model}'",
            _whisper_ready(output_dir, stt_model),
            partial(_download_whisper, output_dir, stt_model),
        ),
        ("Kokoro model files", _kokoro_ready(output_dir), partial(_download_kokoro_bundle, output_dir)),
    )
    # Evaluate every step even when one fails (no short-circuit): a failed
    # model must not skip the remaining downloads.
    results = [_download_step(label, ready, action) for label, ready, action in steps]
    return all(results)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("bundled_models/models"),
        help="Output Hugging Face cache directory (default: bundled_models/models)",
    )
    parser.add_argument(
        "--stt-model",
        default=DEFAULT_STT_MODEL,
        help=f"faster-whisper model to bundle (default: {DEFAULT_STT_MODEL})",
    )
    args = parser.parse_args(argv)
    return 0 if download_all(args.output, args.stt_model) else 1


if __name__ == "__main__":
    raise SystemExit(main())
