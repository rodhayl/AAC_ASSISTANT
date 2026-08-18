"""Bulk-import the full ARASAAC library into the local symbol catalog.

Operator maintenance script. Runs the same idempotent import used by startup,
but unconditionally (ignoring the completion marker) so an operator can
refresh or top up the catalog on demand.

Usage: ``uv run python scripts/import_arasaac_library.py [es|en|...]``
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger  # noqa: E402

from src.aac_app.services.arasaac_library_import import (  # noqa: E402
    import_arasaac_library,
)


def main() -> None:
    locale = sys.argv[1] if len(sys.argv) > 1 else "es"
    summary = asyncio.run(import_arasaac_library(locale))
    logger.info("ARASAAC library import summary: {}", summary)


if __name__ == "__main__":
    main()
