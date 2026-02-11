"""
Ensure local Whisper speech-to-text dependencies are installed.

This is invoked from the Windows startup script (start.bat)
so that core voice dependencies are present without manual pip steps:
- openai-whisper   (speech-to-text model)
- sounddevice      (microphone input)
- soundfile        (saving recorded audio)
- webrtcvad        (optional VAD, but we still try to install it)
"""

from __future__ import annotations

# Suppress the pkg_resources deprecation warning from webrtcvad BEFORE any imports
import warnings
warnings.filterwarnings(
    "ignore",
    message=".*pkg_resources is deprecated.*",
    category=UserWarning,
)
warnings.filterwarnings(
    "ignore",
    message=".*pkg_resources is deprecated.*",
    category=DeprecationWarning,
)

import datetime
import importlib
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

# Core Python packages used by the local speech stack.
# REQUIRED_PACKAGES must all succeed for full voice/microphone support.
REQUIRED_PACKAGES = [
    "openai-whisper",
    "sounddevice",
    "soundfile",
]

# Optional extras – failures here should NEVER block installing required ones.
OPTIONAL_PACKAGES = [
    "webrtcvad",
]

# Map pip package names to the module we try to import
PACKAGE_TO_MODULE: Dict[str, str] = {
    "openai-whisper": "whisper",  # main module name is `whisper`
    "sounddevice": "sounddevice",
    "soundfile": "soundfile",
    "webrtcvad": "webrtcvad",
}


def ensure_logs_dir() -> Path:
    base = Path(__file__).resolve().parent.parent / "logs"
    base.mkdir(parents=True, exist_ok=True)
    return base


def run_install(packages: List[str]) -> subprocess.CompletedProcess:
    """
    Attempt to install packages quietly and return the CompletedProcess so we can log output.
    """
    cmd = [sys.executable, "-m", "pip", "install", "--upgrade", *packages]
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def ffmpeg_available() -> bool:
    """Quick check for ffmpeg on PATH (needed by whisper)."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


def main() -> None:
    logs_dir = ensure_logs_dir()
    log_file = logs_dir / "whisper_dep_install.log"

    def module_missing(pkg: str) -> bool:
        """Return True if the import for this package fails."""
        module_name = PACKAGE_TO_MODULE.get(pkg, pkg.replace("-", "_"))
        try:
            importlib.import_module(module_name)
            return False
        except Exception:
            return True

    # --- Required packages ---
    required_missing: List[str] = [
        pkg for pkg in REQUIRED_PACKAGES if module_missing(pkg)
    ]

    ffmpeg_ok = ffmpeg_available()
    timestamp = datetime.datetime.now().isoformat(timespec="seconds")

    proc_required: subprocess.CompletedProcess | None = None
    if required_missing:
        try:
            proc_required = run_install(required_missing)
        finally:
            try:
                with log_file.open("a", encoding="utf-8") as f:
                    msg = (
                        f"[{timestamp}] Attempted install of REQUIRED: "
                        f"{', '.join(required_missing)} using {sys.executable}\n"
                    )
                    f.write(msg)
                    f.write(f"ffmpeg available: {ffmpeg_ok}\n")
                    if proc_required:
                        f.write(f"pip return code: {proc_required.returncode}\n")
                        if proc_required.stdout:
                            f.write("pip stdout:\n")
                            f.write(proc_required.stdout + "\n")
                        if proc_required.stderr:
                            f.write("pip stderr:\n")
                            f.write(proc_required.stderr + "\n")
                    f.write("\n")
            except Exception:
                pass
    else:
        # Nothing missing from required set – still log ffmpeg status for debugging
        try:
            with log_file.open("a", encoding="utf-8") as f:
                f.write(
                    f"[{timestamp}] REQUIRED packages already present. ffmpeg available: {ffmpeg_ok}\n\n"
                )
        except Exception:
            pass

    # --- Optional packages (best-effort; failures are logged but ignored) ---
    optional_missing: List[str] = [
        pkg for pkg in OPTIONAL_PACKAGES if module_missing(pkg)
    ]
    proc_optional: subprocess.CompletedProcess | None = None
    if optional_missing:
        try:
            proc_optional = run_install(optional_missing)
        finally:
            try:
                with log_file.open("a", encoding="utf-8") as f:
                    msg = (
                        f"[{timestamp}] Attempted install of OPTIONAL: "
                        f"{', '.join(optional_missing)} using {sys.executable}\n"
                    )
                    f.write(msg)
                    if proc_optional:
                        f.write(f"pip return code: {proc_optional.returncode}\n")
                        if proc_optional.stdout:
                            f.write("pip stdout:\n")
                            f.write(proc_optional.stdout + "\n")
                        if proc_optional.stderr:
                            f.write("pip stderr:\n")
                            f.write(proc_optional.stderr + "\n")
                    f.write("\n")
            except Exception:
                pass

    # User-facing console hints (printed when running under python, not pythonw)
    if sys.stdout and sys.stdout.isatty():
        if not ffmpeg_ok:
            sys.stdout.write(
                "ffmpeg is required for Whisper. Install it and ensure ffmpeg.exe is on your PATH.\n"
            )
        if proc_required and proc_required.returncode != 0:
            sys.stdout.write(
                "Voice dependencies failed to install. See logs/whisper_dep_install.log for details.\n"
            )


if __name__ == "__main__":
    main()
