"""Non-interactive download command for optional local AI models.

Usage:
    uv run python -m src.aac_app.providers.model_download

The faster-whisper model is cached under ``data/models`` so it is retained
between application runs and is not placed in the operating system temp
directory.
"""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

from loguru import logger

from ... import config


def download_speech_model(
    model_size: str = "small",
    model_cache_dir: str | Path | None = None,
) -> bool:
    """Download a faster-whisper model without prompting for input."""
    if importlib.util.find_spec("faster_whisper") is None:
        logger.error("faster-whisper is not installed. Run `uv sync --extra voice` first.")
        return False

    cache_dir = Path(model_cache_dir or config.get_data_path("models")).absolute()
    cache_dir.mkdir(parents=True, exist_ok=True)

    try:
        from faster_whisper import WhisperModel

        logger.info("Downloading faster-whisper '{}' into {}", model_size, cache_dir)
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


def main(argv: list[str] | None = None) -> int:
    """Run the model download CLI and return a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        default="small",
        choices=("tiny", "base", "small", "medium", "large-v3"),
        help="faster-whisper model to cache (default: small)",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="Override the model cache directory (default: data/models)",
    )
    args = parser.parse_args(argv)
    return 0 if download_speech_model(args.model, args.cache_dir) else 1


if __name__ == "__main__":
    raise SystemExit(main())
