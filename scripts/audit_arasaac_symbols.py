"""Audit local ARASAAC symbols against the Spanish and English catalogs.

The command is read-only: it never inserts, updates, deletes, or downloads
files. It fetches both ARASAAC catalogs, compares their primary labels with
local symbols, verifies every local image path, and checks that each catalog
has a corresponding local symbol in its language.

Usage::

    uv run python scripts/audit_arasaac_symbols.py
    uv run python scripts/audit_arasaac_symbols.py --offline-catalog data/reports/arasaac_catalogs_es_en.json
    uv run python scripts/audit_arasaac_symbols.py --json report.json

Exit status is non-zero when a catalog cannot be fetched, a catalog label is
missing locally, or a local symbol has a missing image.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config  # noqa: E402
from src.aac_app.db import get_session  # noqa: E402
from src.aac_app.models import Symbol  # noqa: E402
from src.aac_app.services.arasaac import ArasaacService  # noqa: E402
from src.aac_app.services.runtime_translation import normalize_language_code  # noqa: E402

SUPPORTED_LOCALES = ("es", "en")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--offline-catalog",
        type=Path,
        help="Use a previously saved JSON catalog instead of contacting ARASAAC.",
    )
    parser.add_argument(
        "--json",
        dest="json_path",
        type=Path,
        help="Write the audit report as JSON as well as printing the summary.",
    )
    return parser.parse_args(argv)


def _primary_labels(entries: list[dict]) -> dict[int, str]:
    labels: dict[int, str] = {}
    for entry in entries:
        keywords = entry.get("keywords") or []
        if not keywords:
            continue
        label = str(keywords[0].get("keyword") or "").strip()
        if label:
            labels[int(entry["_id"])] = label
    return labels


def _load_catalog(path: Path) -> dict[str, list[dict]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("catalog JSON must be an object keyed by locale")
    return {locale: payload[locale] for locale in SUPPORTED_LOCALES}


async def _fetch_catalogs() -> dict[str, list[dict]]:
    service = ArasaacService()
    try:
        return {
            locale: await service.list_all_symbols(locale)
            for locale in SUPPORTED_LOCALES
        }
    finally:
        await service.close()


def _local_image_exists(image_path: str | None) -> bool:
    if not image_path:
        return False
    if image_path.startswith(("http://", "https://")):
        return True
    if not image_path.startswith("/uploads/"):
        return False
    return (config.UPLOADS_DIR / image_path.removeprefix("/uploads/")).is_file()


def audit(catalogs: dict[str, list[dict]]) -> dict:
    catalog_labels = {
        locale: _primary_labels(catalogs[locale]) for locale in SUPPORTED_LOCALES
    }
    with get_session() as db:
        local_rows = db.query(Symbol).all()

    local_by_language: dict[str, list[Symbol]] = defaultdict(list)
    for symbol in local_rows:
        local_by_language[normalize_language_code(symbol.language) or ""].append(symbol)

    languages: dict[str, dict] = {}
    failures = 0
    for locale in SUPPORTED_LOCALES:
        local_symbols = local_by_language[locale]
        local_labels = {symbol.label.casefold() for symbol in local_symbols if symbol.label}
        catalog = catalog_labels[locale]
        missing_labels = sorted(
            label for label in catalog.values() if label.casefold() not in local_labels
        )
        missing_images = [
            {
                "id": symbol.id,
                "label": symbol.label,
                "image_path": symbol.image_path,
            }
            for symbol in local_symbols
            if not _local_image_exists(symbol.image_path)
        ]
        duplicate_labels = sorted(
            label for label, count in _count_labels(local_symbols).items() if count > 1
        )
        languages[locale] = {
            "catalog_entries": len(catalogs[locale]),
            "catalog_unique_primary_labels": len(catalog),
            "local_symbols": len(local_symbols),
            "missing_catalog_labels": len(missing_labels),
            "missing_label_sample": missing_labels[:20],
            "missing_images": len(missing_images),
            "missing_image_sample": missing_images[:20],
            "duplicate_local_labels": len(duplicate_labels),
            "duplicate_label_sample": duplicate_labels[:20],
        }
        failures += len(missing_labels) + len(missing_images)

    es_ids = set(catalog_labels["es"])
    en_ids = set(catalog_labels["en"])
    report = {
        "ok": failures == 0 and es_ids == en_ids,
        "catalogs": {
            locale: {
                "entries": len(catalogs[locale]),
                "unique_primary_labels": len(catalog_labels[locale]),
            }
            for locale in SUPPORTED_LOCALES
        },
        "equivalence": {
            "es_ids": len(es_ids),
            "en_ids": len(en_ids),
            "shared_ids": len(es_ids & en_ids),
            "es_only_ids": len(es_ids - en_ids),
            "en_only_ids": len(en_ids - es_ids),
        },
        "languages": languages,
    }
    return report


def _count_labels(symbols: list[Symbol]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for symbol in symbols:
        if symbol.label:
            counts[symbol.label.casefold()] += 1
    return counts


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        catalogs = _load_catalog(args.offline_catalog) if args.offline_catalog else asyncio.run(_fetch_catalogs())
        report = audit(catalogs)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.json_path:
        args.json_path.parent.mkdir(parents=True, exist_ok=True)
        args.json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
