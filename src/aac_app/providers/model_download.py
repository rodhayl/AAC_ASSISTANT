"""Non-interactive download command for optional local AI models.

Usage:
    uv run python -m src.aac_app.providers.model_download

The faster-whisper model is cached under ``data/models`` so it is retained
between application runs and is not placed in the operating system temp
directory.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import sys
from collections.abc import Iterator
from pathlib import Path

from loguru import logger

from ... import config
from .local_speech_provider import DEFAULT_STT_MODEL, SUPPORTED_STT_MODELS, normalize_stt_model


@contextlib.contextmanager
def _safe_streams() -> Iterator[tuple[io.StringIO | object, io.StringIO | object]]:
    """Redirect stdio to throwaway buffers when ``sys.stdout``/``sys.stderr`` are ``None``.

    Frozen / windowed PyInstaller builds leave both standard streams as
    ``None``; libraries such as faster_whisper, huggingface_hub, and
    onnxruntime write progress to those streams during model download.
    Without a working stream the underlying ``.write`` raises
    ``AttributeError`` and the request fails.  We swap in ``StringIO``
    buffers while the wrapped code runs, then restore the originals.
    """
    saved_out, saved_err = sys.stdout, sys.stderr
    redirect_out = saved_out if saved_out is not None else io.StringIO()
    redirect_err = saved_err if saved_err is not None else io.StringIO()
    try:
        with contextlib.redirect_stdout(redirect_out), contextlib.redirect_stderr(
            redirect_err
        ):
            yield redirect_out, redirect_err
    finally:
        sys.stdout, sys.stderr = saved_out, saved_err


def download_speech_model(
    model_size: str = DEFAULT_STT_MODEL,
    model_cache_dir: str | Path | None = None,
) -> bool:
    """Download a faster-whisper model without prompting for input."""
    if importlib.util.find_spec("faster_whisper") is None:
        logger.error("faster-whisper is not installed. Run `uv sync --extra voice` first.")
        return False

    model_size = normalize_stt_model(model_size)
    cache_dir = Path(model_cache_dir or config.get_data_path("models")).absolute()
    cache_dir.mkdir(parents=True, exist_ok=True)

    try:
        from faster_whisper import WhisperModel

        logger.info("Downloading faster-whisper '{}' into {}", model_size, cache_dir)
        # Frozen windowed builds have no console; wrap the download so
        # tqdm / huggingface_hub progress writes do not crash with
        # AttributeError on a None stream.
        with _safe_streams():
            WhisperModel(
                model_size,
                device="cpu",
                compute_type="int8",
                download_root=str(cache_dir),
            )
    except Exception as exc:
        logger.error("Failed to download faster-whisper model: {}", exc)
        return False

    logger.success("faster-whisper '{}' is ready in {}", model_size, cache_dir)
    return True


def download_kokoro_model() -> bool:
    """Download the optional local neural TTS (Kokoro) model files."""
    from src.aac_app.providers.local_tts_provider import download_kokoro_model as _dl

    return _dl()


def main(argv: list[str] | None = None) -> int:
    """Run the model download CLI and return a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        default=DEFAULT_STT_MODEL,
        choices=tuple(SUPPORTED_STT_MODELS),
        help="faster-whisper model to cache (default: tiny)",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="Override the model cache directory (default: data/models)",
    )
    parser.add_argument(
        "--tts",
        action="store_true",
        help="Download the optional local neural TTS (Kokoro) model instead",
    )
    args = parser.parse_args(argv)
    if args.tts:
        return 0 if download_kokoro_model() else 1
    return 0 if download_speech_model(args.model, args.cache_dir) else 1


if __name__ == "__main__":
    raise SystemExit(main())
