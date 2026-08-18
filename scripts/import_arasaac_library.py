"""Bulk-import the full ARASAAC library into the local symbol catalog.

Operator maintenance script. It reuses :class:`ArasaacService` and the
existing ``Symbol`` model to download every *distinct* ARASAAC term (deduped
by primary keyword, case-insensitive) together with its 500px image.

The script is idempotent and resumable:

- a term whose label already exists in the catalog is skipped (linked, not
  duplicated);
- an image file that already exists on disk is not downloaded again;
- failed downloads leave neither a Symbol row nor a file, so a re-run retries
  them.

Usage: ``uv run python scripts/import_arasaac_library.py [es|en|...]``
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger  # noqa: E402

from src import config  # noqa: E402
from src.aac_app.db import get_session  # noqa: E402
from src.aac_app.models import Symbol  # noqa: E402
from src.aac_app.services.arasaac import ArasaacService  # noqa: E402

MAX_CONCURRENCY = 10
COMMIT_BATCH = 200


def _existing_labels() -> set[str]:
    with get_session() as db:
        return {
            label.casefold()
            for (label,) in db.query(Symbol.label).all()
            if label
        }


async def _run(locale: str) -> None:
    service = ArasaacService()
    try:
        logger.info("Fetching ARASAAC pictogram catalog for locale={}", locale)
        pictograms = await service.list_all_symbols(locale)
        logger.info("ARASAAC returned {} pictograms", len(pictograms))

        existing = _existing_labels()
        seen = set(existing)
        chosen: list[tuple[dict, str]] = []
        for entry in pictograms:
            keywords = entry.get("keywords") or []
            if not keywords:
                continue
            label = (keywords[0].get("keyword") or "").strip()
            key = label.casefold()
            if not label or key in seen:
                continue
            seen.add(key)
            chosen.append((entry, label))

        skipped = len(pictograms) - len(chosen)
        logger.info(
            "Importing {} new terms ({} already exist or are duplicate labels)",
            len(chosen),
            skipped,
        )

        uploads_dir = config.UPLOADS_DIR / "symbols"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
        imported = 0
        failed = 0

        async def download(entry: dict) -> tuple[dict, bytes | None]:
            async with semaphore:
                return entry, await service.download_symbol_image_500(entry["_id"])

        for offset in range(0, len(chosen), COMMIT_BATCH):
            batch = chosen[offset : offset + COMMIT_BATCH]
            results = await asyncio.gather(*(download(entry) for entry, _ in batch))

            with get_session() as db:
                for (entry, label), (_, content) in zip(batch, results, strict=True):
                    if not content:
                        failed += 1
                        continue
                    filename = f"arasaac_{entry['_id']}.png"
                    path = uploads_dir / filename
                    if not path.exists():
                        path.write_bytes(content)

                    all_keywords = ", ".join(
                        k.get("keyword", "")
                        for k in (entry.get("keywords") or [])
                        if k.get("keyword")
                    )
                    categories = entry.get("categories") or []
                    meaning = (entry.get("keywords") or [{}])[0].get("meaning")
                    db.add(
                        Symbol(
                            label=label,
                            description=meaning or None,
                            category=categories[0] if categories else "general",
                            keywords=all_keywords or None,
                            language=locale,
                            image_path=f"/uploads/symbols/{filename}",
                            is_builtin=False,
                        )
                    )
                    imported += 1

            logger.info(
                "progress: {} imported / {} total, {} failed",
                imported,
                len(chosen),
                failed,
            )

        logger.info(
            "Bulk import finished: imported={} failed={} skipped={}",
            imported,
            failed,
            skipped,
        )
    finally:
        await service.close()


def main() -> None:
    locale = sys.argv[1] if len(sys.argv) > 1 else "es"
    asyncio.run(_run(locale))


if __name__ == "__main__":
    main()
