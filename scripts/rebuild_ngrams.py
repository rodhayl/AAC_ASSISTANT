"""
Rebuild n-gram prediction models from real symbol usage logs.

Writes the learned (bundled-seed-fused) models to the writable data/ngrams
directory, which the prediction service prefers over the bundled JSON files.
Run manually to refresh models without restarting the server:

    uv run python -m scripts.rebuild_ngrams
"""

from __future__ import annotations

from src import config
from src.aac_app.services.ngram_builder import rebuild_ngram_models


def main() -> int:
    """Rebuild models for the configured ARASAAC locales and report paths."""
    locales = tuple(
        locale.strip()
        for locale in str(config.get("AAC_ARASAAC_LIBRARY_LOCALES", "es")).split(",")
        if locale.strip()
    ) or ("es",)
    written = rebuild_ngram_models(locales=locales)
    for locale, path in sorted(written.items()):
        size = path.stat().st_size if path.exists() else 0
        print(f"locale={locale} -> {path} ({size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
