"""Prepare the required local voice runtime before the server starts.

The source-checkout launcher installs the optional voice packages separately;
this module verifies that installation and downloads the Kokoro model files so
the first spoken panel never triggers a network download or a browser fallback.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make direct execution work from the repository root:
# ``uv run python scripts/ensure_voice_runtime.py``.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.aac_app.providers.local_speech_provider import is_faster_whisper_available
from src.aac_app.providers.local_tts_provider import (
    download_kokoro_model,
    get_local_tts_provider,
    model_files_present,
)


def main() -> int:
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
        print("Preparing Kokoro model files...")
        if not download_kokoro_model():
            print(
                "ERROR: Kokoro model preparation failed. Check network access and "
                "the writable data/models/kokoro directory.",
                file=sys.stderr,
            )
            return 1

    print("Voice runtime ready: faster-whisper and Kokoro.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
