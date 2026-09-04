"""Prepare the required local voice runtime before the server starts.

The source-checkout launcher installs the optional voice packages separately;
this module verifies that installation and downloads the Kokoro model files so
the first spoken panel never triggers a network download or a browser fallback.
"""

from __future__ import annotations

import argparse
import sys


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse runtime options before importing optional voice dependencies."""
    parser = argparse.ArgumentParser(
        description=(
            "Prepare the optional faster-whisper and Kokoro voice runtime. "
            "With no flags, missing model files are downloaded."
        )
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="check installed packages and model files without downloading them",
    )
    return parser.parse_args(argv)


def _prepare_voice_runtime(*, check_only: bool = False) -> int:
    """Verify and, unless checking, prepare the optional voice runtime."""
    # Make direct execution work from the repository root only after argument
    # parsing; ``--help`` must not resolve paths, import application modules,
    # inspect model files, or touch the network.
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    # Keep these imports inside the work path: argparse --help must be fast and
    # must not import optional native stacks or inspect/download model files.
    from src.aac_app.providers.local_speech_provider import is_faster_whisper_available
    from src.aac_app.providers.local_tts_provider import (
        download_kokoro_model,
        get_local_tts_provider,
        model_files_present,
    )

    if not is_faster_whisper_available():
        print(
            "ERROR: faster-whisper voice dependencies are unavailable. "
            "Run: uv sync --extra voice --extra tts",
            file=sys.stderr,
        )
        return 1

    provider = get_local_tts_provider()
    if not provider.is_installed():
        print(
            "ERROR: Kokoro is unavailable. Run: uv sync --python 3.13 "
            "--extra voice --extra tts",
            file=sys.stderr,
        )
        return 1

    if not model_files_present():
        if check_only:
            print(
                "ERROR: Kokoro model files are missing. Run this command without "
                "--check to prepare them.",
                file=sys.stderr,
            )
            return 1
        print("Preparing Kokoro model files...")
        if not download_kokoro_model():
            print(
                "ERROR: Kokoro model preparation failed. Check network access and "
                "the writable data/models/kokoro directory.",
                file=sys.stderr,
            )
            return 1

    if check_only:
        print("Voice runtime check passed: faster-whisper, Kokoro, and model files.")
    else:
        print("Voice runtime ready: faster-whisper and Kokoro.")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, keeping the no-argument preparation path unchanged."""
    args = _parse_args(argv)
    return _prepare_voice_runtime(check_only=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
