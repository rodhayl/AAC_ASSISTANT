"""One-time bulk import of the ARASAAC pictogram library.

Reuses :class:`~src.aac_app.services.arasaac.ArasaacService` and the ``Symbol``
model to download every *distinct* ARASAAC term (deduped by primary keyword,
case-insensitive) together with its 500px image.

The import is idempotent and resumable:

- a term whose label already exists in the catalog is skipped (linked, not
  duplicated);
- an image file that already exists on disk is not downloaded again;
- failed downloads leave neither a ``Symbol`` row nor a file, so a later run
  retries them.

``import_arasaac_library_if_needed`` is the startup entry point: it records a
per-locale completion marker in ``app_settings`` so the catalog is fetched only
until the first successful import.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from loguru import logger
from sqlalchemy.exc import OperationalError

from src import config
from src.aac_app.db import get_session
from src.aac_app.models import AppSettings, Symbol
from src.aac_app.services.arasaac import ArasaacService
from src.aac_app.services.runtime_translation import normalize_language_code

MAX_CONCURRENCY = 10
COMMIT_BATCH = 200
# A concurrent request (e.g. a login) holds SQLite's single write lock for a
# few milliseconds while it commits; the bulk import retries a batch instead
# of aborting the whole 17k-row import on a transient collision.
_LOCK_RETRY_ATTEMPTS = 3
_LOCK_RETRY_DELAY_SECONDS = 0.5


def _is_locked_error(exc: OperationalError) -> bool:
    """Return True when the failure is SQLite write-lock contention."""
    message = str(exc.orig if exc.orig is not None else exc)
    return "locked" in message.lower()


def _imported_key(locale: str) -> str:
    return f"arasaac_library_imported_{locale}"


def _existing_labels() -> set[str]:
    with get_session() as db:
        return {
            label.casefold()
            for (label,) in db.query(Symbol.label).all()
            if label
        }


def _already_imported(locale: str) -> bool:
    key = _imported_key(locale)
    with get_session() as db:
        row = (
            db.query(AppSettings)
            .filter(AppSettings.setting_key == key)
            .first()
        )
        return bool(row and row.setting_value == "1")


def _mark_imported(locale: str) -> None:
    key = _imported_key(locale)
    with get_session() as db:
        row = (
            db.query(AppSettings)
            .filter(AppSettings.setting_key == key)
            .first()
        )
        if row is None:
            db.add(AppSettings(setting_key=key, setting_value="1"))
        else:
            row.setting_value = "1"


async def import_arasaac_library(locale: str = "es") -> dict[str, int]:
    """Download every distinct ARASAAC term and its image for a locale.

    Returns a summary with ``imported``, ``failed``, and ``skipped`` counts.
    """
    locale = normalize_language_code(locale) or "es"
    service = ArasaacService()
    imported = 0
    failed = 0
    try:
        logger.info("Fetching ARASAAC pictogram catalog for locale={}", locale)
        pictograms = await service.list_all_symbols(locale)
        logger.info("ARASAAC returned {} pictograms", len(pictograms))

        # Labels are scoped by locale: the Spanish and English catalogs must
        # both be materialized even when their primary terms happen to match.
        with get_session() as db:
            existing = {
                label.casefold()
                for (label,) in db.query(Symbol.label)
                .filter(Symbol.language == locale)
                .all()
                if label
            }
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

        def image_path(entry: dict) -> Path:
            return uploads_dir / f"arasaac_{entry['_id']}.png"

        async def download(entry: dict) -> tuple[dict, bytes | None]:
            # Pictogram images are locale-independent; a prior locale's import
            # may already have stored this exact file, so skip the network fetch.
            if image_path(entry).exists():
                return entry, None
            async with semaphore:
                return entry, await service.download_symbol_image_500(entry["_id"])

        for offset in range(0, len(chosen), COMMIT_BATCH):
            batch = chosen[offset : offset + COMMIT_BATCH]
            results = await asyncio.gather(*(download(entry) for entry, _ in batch))

            # Write one batch inside a single transaction. A concurrent request
            # may hold the SQLite write lock for a few milliseconds; retry a
            # bounded number of times instead of letting one collision abort
            # the entire library import. File writes are idempotent (skipped
            # when the file exists), so a retried batch cannot duplicate rows
            # or files. Counters are updated only after the commit succeeds.
            batch_imported = 0
            batch_failed = 0
            for attempt in range(_LOCK_RETRY_ATTEMPTS):
                try:
                    with get_session() as db:
                        for (entry, label), (_, content) in zip(
                            batch, results, strict=True
                        ):
                            path = image_path(entry)
                            if content is None and not path.exists():
                                batch_failed += 1
                                continue
                            if content is not None and not path.exists():
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
                                    image_path=f"/uploads/symbols/{path.name}",
                                    is_builtin=False,
                                )
                            )
                            batch_imported += 1
                    break
                except OperationalError as exc:
                    if not _is_locked_error(exc) or attempt == _LOCK_RETRY_ATTEMPTS - 1:
                        raise
                    logger.warning(
                        "ARASAAC import batch {} hit a transient write lock; "
                        "retrying (attempt {}/{})",
                        offset // COMMIT_BATCH + 1,
                        attempt + 1,
                        _LOCK_RETRY_ATTEMPTS,
                    )
                    await asyncio.sleep(_LOCK_RETRY_DELAY_SECONDS * (attempt + 1))
                    batch_imported = 0
                    batch_failed = 0

            imported += batch_imported
            failed += batch_failed

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
        return {"imported": imported, "failed": failed, "skipped": skipped}
    finally:
        await service.close()


async def count_importable_arasaac_terms(locale: str = "es") -> dict[str, int]:
    """Report how many catalog terms an import would add, without writing.

    Used by the operator script's ``--dry-run``: fetches the catalog and
    applies the same skip rules as :func:`import_arasaac_library` (missing
    keywords, duplicate labels, labels already stored for the locale) but
    touches neither the database nor the image files.
    """
    locale = normalize_language_code(locale) or "es"
    service = ArasaacService()
    try:
        pictograms = await service.list_all_symbols(locale)
        with get_session() as db:
            existing = {
                label.casefold()
                for (label,) in db.query(Symbol.label)
                .filter(Symbol.language == locale)
                .all()
                if label
            }
    finally:
        await service.close()

    seen = set(existing)
    importable = 0
    for entry in pictograms:
        keywords = entry.get("keywords") or []
        if not keywords:
            continue
        label = (keywords[0].get("keyword") or "").strip()
        if not label:
            continue
        key = label.casefold()
        if key in seen:
            continue
        seen.add(key)
        importable += 1
    return {
        "importable": importable,
        "skipped": len(pictograms) - importable,
        "catalog": len(pictograms),
    }


async def import_arasaac_library_if_needed(
    locale: str = "es",
) -> dict[str, int] | None:
    """Run the import once per locale and record completion.

    Returns the import summary, or ``None`` when the library was already
    imported for this locale.
    """
    locale = normalize_language_code(locale) or "es"
    if _already_imported(locale):
        logger.info("ARASAAC library already imported for locale={}; skipping", locale)
        return None

    summary = await import_arasaac_library(locale)
    if summary.get("failed", 0) == 0:
        _mark_imported(locale)
        logger.info("Marked ARASAAC library import complete for locale={}", locale)
    return summary
