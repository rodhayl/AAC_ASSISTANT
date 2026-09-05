"""Bulk-import the full ARASAAC library into the local symbol catalog.

Operator maintenance script. Runs the same idempotent import used by startup,
but unconditionally (ignoring the completion marker) so an operator can
refresh or top up the catalog on demand.

The import **writes to the configured database** (and downloads pictogram
images into the uploads directory). It is additive and idempotent — existing
labels are skipped, nothing is deleted — but it is still a bulk write, so
pass ``--dry-run`` to preview the work first.

Usage:
    uv run python scripts/import_arasaac_library.py [locale] [--dry-run]
    uv run python scripts/import_arasaac_library.py es           # writes
    uv run python scripts/import_arasaac_library.py es --dry-run # report only
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "locale",
        nargs="?",
        default="es",
        help="ARASAAC locale to import (default: es)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "report how many terms would be imported without writing to the "
            "database or downloading images"
        ),
    )
    args = parser.parse_args(argv)

    # Imported after parsing so ``--help`` stays inert: the import service
    # module pulls in app config/DB modules that create runtime directories
    # as an import side effect.
    from loguru import logger
    from sqlalchemy.exc import OperationalError

    from src.aac_app.services.arasaac_library_import import (
        count_importable_arasaac_terms,
        import_arasaac_library,
    )

    if args.dry_run:
        try:
            report = asyncio.run(count_importable_arasaac_terms(args.locale))
        except OperationalError as exc:
            # Strictly read-only: a missing schema is reported, not created
            # (creating it would write to the database).
            print(
                "DRY RUN failed: the database schema does not exist yet "
                f"({exc.orig}). Initialize it first with "
                "scripts/ensure_bootstrap_admin.py, then re-run."
            )
            raise SystemExit(1) from exc
        print(
            "DRY RUN — nothing written. "
            f"locale={args.locale} new={report['importable']} "
            f"already_present={report['skipped']} catalog_total={report['catalog']}"
        )
        return

    summary = asyncio.run(import_arasaac_library(args.locale))
    logger.info("ARASAAC library import summary: {}", summary)


if __name__ == "__main__":
    main()
