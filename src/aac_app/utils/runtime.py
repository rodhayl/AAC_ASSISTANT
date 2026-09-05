"""Small runtime helpers shared by application and maintenance entry points."""

from __future__ import annotations

import contextlib
import io
import shutil
import sys
from collections.abc import Iterator


@contextlib.contextmanager
def safe_streams() -> Iterator[None]:
    """Temporarily provide writable stdout/stderr for windowed frozen builds.

    PyInstaller windowed builds can expose ``None`` for the standard streams,
    while optional model/download libraries still call ``write`` on them.
    Existing streams are preserved and restored exactly after the wrapped work.
    """
    saved_out, saved_err = sys.stdout, sys.stderr
    redirect_out = saved_out if saved_out is not None else io.StringIO()
    redirect_err = saved_err if saved_err is not None else io.StringIO()
    try:
        with contextlib.redirect_stdout(redirect_out), contextlib.redirect_stderr(
            redirect_err
        ):
            yield
    finally:
        sys.stdout, sys.stderr = saved_out, saved_err


def npm_command() -> str | None:
    """Return npm's Windows shim or platform-neutral executable."""
    return shutil.which("npm.cmd") or shutil.which("npm")


__all__ = ["npm_command", "safe_streams"]
