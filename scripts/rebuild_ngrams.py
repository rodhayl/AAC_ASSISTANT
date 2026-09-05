"""
Rebuild n-gram prediction models from real symbol usage logs.

Writes the learned (bundled-seed-fused) models to the writable data/ngrams
directory, which the prediction service prefers over the bundled JSON files.
Run manually to refresh models without restarting the server:

    uv run python -m scripts.rebuild_ngrams

The rebuild writes to the configured data directory; pass ``--dry-run`` to
report the locales that would be rebuilt without writing any model files.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make direct execution work from the repository root. The import is only a
# path adjustment; application/config modules remain deferred until after
# argparse so ``--help`` stays inert.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main(argv: list[str] | None = None) -> int:
    """Rebuild models for the configured ARASAAC locales and report paths."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report the locales that would be rebuilt without writing files",
    )
    args = parser.parse_args(argv)

    # Imported after parsing so ``--help`` stays inert: importing the app
    # config module creates the data/logs/uploads directories as a side
    # effect, which an informational help run must not do.
    from src import config
    from src.aac_app.services.ngram_builder import rebuild_ngram_models

    locales = tuple(
        locale.strip()
        for locale in str(config.get("AAC_ARASAAC_LIBRARY_LOCALES", "es")).split(",")
        if locale.strip()
    ) or ("es",)
    if args.dry_run:
        print("DRY RUN — nothing written. locales=" + ",".join(locales))
        return 0
    written = rebuild_ngram_models(locales=locales)
    for locale, path in sorted(written.items()):
        size = path.stat().st_size if path.exists() else 0
        print(f"locale={locale} -> {path} ({size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
