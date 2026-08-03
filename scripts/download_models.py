#!/usr/bin/env python3
"""Compatibility wrapper for the non-interactive model download command."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.aac_app.providers.model_download import main


if __name__ == "__main__":
    raise SystemExit(main())
