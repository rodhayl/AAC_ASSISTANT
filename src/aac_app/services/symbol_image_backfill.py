from __future__ import annotations

import asyncio
import os
import re
import threading
from contextlib import suppress
from pathlib import PurePosixPath
from uuid import uuid4

from loguru import logger
from sqlalchemy import func, or_

from src import config
from src.aac_app.db import get_session
from src.aac_app.models import Symbol
from src.aac_app.services.arasaac import ArasaacService
from src.aac_app.services.runtime_translation import normalize_language_code


def _missing_image_clause():
    return or_(Symbol.image_path.is_(None), func.trim(Symbol.image_path) == "")


def _candidate_locales(language: str | None) -> list[str]:
    primary = normalize_language_code(language) or normalize_language_code(
        config.DEFAULT_LOCALE
    ) or "en"
    locales: list[str] = []
    for locale in (primary, "en", "es"):
        if locale and locale not in locales:
            locales.append(locale)
    return locales


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.casefold().split())


def _public_path_exists(public_path: str | None) -> bool:
    if not public_path:
        return False
    if public_path.startswith(("http://", "https://")):
        return True
    if not public_path.startswith("/uploads/"):
        return False
    relative_path = PurePosixPath(public_path.removeprefix("/uploads/"))
    return (config.UPLOADS_DIR / relative_path).exists()


def _reusable_image_paths(
    db, symbols
) -> dict[tuple[str, str | None], list[tuple[int, str]]]:
    """Load reusable image candidates for a batch in one database query."""
    keys = {
        (symbol.label.casefold(), symbol.category)
        for symbol in symbols
        if symbol.label
    }
    if not keys:
        return {}

    labels = {label for label, _category in keys}
    categories = {category for _label, category in keys}
    query = (
        db.query(Symbol.id, Symbol.image_path, Symbol.category, func.lower(Symbol.label))
        .filter(
            func.lower(Symbol.label).in_(labels),
            Symbol.image_path.is_not(None),
            func.trim(Symbol.image_path) != "",
        )
        .order_by(Symbol.id.asc())
    )
    if None not in categories:
        query = query.filter(Symbol.category.in_(categories))

    reusable: dict[tuple[str, str | None], list[tuple[int, str]]] = {}
    for symbol_id, image_path, category, label in query.yield_per(1000):
        key = (label, category)
        if key in keys and _public_path_exists(image_path):
            reusable.setdefault(key, []).append((symbol_id, image_path))
    return reusable


def _best_arasaac_match(label: str, results: list[dict]) -> dict | None:
    wanted = _normalize_text(label)
    if not wanted:
        return None

    for result in results:
        labels = [_normalize_text(result.get("label"))]
        keywords = result.get("keywords")
        if isinstance(keywords, str):
            labels.extend(_normalize_text(part) for part in keywords.split(","))
        if wanted in {candidate for candidate in labels if candidate}:
            return result

    return results[0] if results else None


def _search_queries(symbol: Symbol) -> list[str]:
    seen: set[str] = set()
    queries: list[str] = []
    stopwords = {
        "frontend",
        "comm",
        "communication",
        "symbol",
        "disposable",
        "export",
        "roundtrip",
        "general",
    }

    def add(candidate: str | None) -> None:
        normalized = _normalize_text(candidate)
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        queries.append(normalized)

    add(symbol.label)

    for field in (symbol.keywords, symbol.description, symbol.category):
        if not field:
            continue
        for phrase in re.split(r"[,;/]", field):
            cleaned = re.sub(r"[_-]+", " ", phrase).strip()
            add(cleaned)
            for token in cleaned.split():
                if len(token) < 2 or token.casefold() in stopwords:
                    continue
                if not any(char.isalpha() for char in token):
                    continue
                add(token)

    return queries[:8]


def _store_downloaded_image(symbol_id: int, arasaac_id: int, content: bytes) -> str:
    uploads_dir = config.UPLOADS_DIR / "symbols"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    # Use a unique name so concurrent backfill workers never overwrite a
    # winner's file while racing to fill the same database row.
    filename = f"arasaac_auto_{symbol_id}_{arasaac_id}_{uuid4().hex}.png"
    file_path = uploads_dir / filename
    file_path.write_bytes(content)
    return f"/uploads/symbols/{filename}"


def _set_image_path(db, symbol_id: int, image_path: str) -> bool:
    """Set a still-missing image without reloading the symbol row."""
    updated = (
        db.query(Symbol)
        .filter(Symbol.id == symbol_id, _missing_image_clause())
        .update({Symbol.image_path: image_path}, synchronize_session=False)
    )
    return bool(updated)


def _remove_stored_image_if_unreferenced(db, symbol_id: int, image_path: str) -> None:
    """Remove a lost download unless another worker won with this same path."""
    current_path = db.query(Symbol.image_path).filter(Symbol.id == symbol_id).scalar()
    if current_path == image_path:
        return
    if not image_path.startswith("/uploads/"):
        return
    relative_path = PurePosixPath(image_path.removeprefix("/uploads/"))
    with suppress(OSError):
        (config.UPLOADS_DIR / relative_path).unlink()


async def backfill_missing_symbol_images(
    limit: int = 100,
    symbol_ids: list[int] | None = None,
) -> dict[str, int]:
    summary = {
        "processed": 0,
        "updated": 0,
        "downloaded": 0,
        "reused": 0,
        "failed": 0,
    }
    if limit <= 0:
        return summary

    # Take one bounded, detached snapshot before network work. The previous
    # implementation selected IDs and then issued one ORM lookup per symbol;
    # keeping the columns needed by the worker avoids that N+1 pattern while
    # preserving short per-symbol write transactions.
    with get_session() as db:
        query = (
            db.query(
                Symbol.id,
                Symbol.label,
                Symbol.category,
                Symbol.language,
                Symbol.image_path,
                Symbol.keywords,
                Symbol.description,
            )
            .filter(_missing_image_clause())
        )
        if symbol_ids:
            query = query.filter(Symbol.id.in_(symbol_ids))
        symbols = (
            query.order_by(Symbol.is_builtin.desc(), Symbol.id.asc())
            .limit(limit)
            .all()
        )

    if not symbols:
        return summary

    with get_session() as db:
        reusable_paths = _reusable_image_paths(db, symbols)

    service = ArasaacService()
    try:
        for symbol in symbols:
            symbol_id = symbol.id
            summary["processed"] += 1
            try:
                with get_session() as db:
                    reusable_candidates = reusable_paths.get(
                        (symbol.label.casefold(), symbol.category), []
                    )
                    reusable_path = next(
                        (
                            image_path
                            for candidate_id, image_path in reusable_candidates
                            if candidate_id != symbol_id
                        ),
                        None,
                    )
                    if reusable_path:
                        if _set_image_path(db, symbol_id, reusable_path):
                            summary["updated"] += 1
                            summary["reused"] += 1
                        continue

                    match = None
                    for query in _search_queries(symbol):
                        for locale in _candidate_locales(symbol.language):
                            results = await service.search_symbols(query, locale)
                            match = _best_arasaac_match(query, results)
                            if match:
                                break
                        if match:
                            break

                    arasaac_id = match.get("id") if match else None
                    if arasaac_id is None:
                        summary["failed"] += 1
                        continue

                    image_content = await service.download_symbol_image(int(arasaac_id))
                    if not image_content:
                        summary["failed"] += 1
                        continue

                    image_path = _store_downloaded_image(
                        symbol_id, int(arasaac_id), image_content
                    )
                    if _set_image_path(db, symbol_id, image_path):
                        summary["updated"] += 1
                        summary["downloaded"] += 1
                    else:
                        # Another worker filled the row while the network
                        # request was in flight; do not leak our unused file.
                        _remove_stored_image_if_unreferenced(db, symbol_id, image_path)
            except Exception as exc:
                summary["failed"] += 1
                logger.warning(
                    "Symbol image backfill failed for symbol {}: {}", symbol_id, exc
                )
    finally:
        with suppress(Exception):
            await service.close()

    logger.info(
        "Symbol image backfill processed={processed} updated={updated} downloaded={downloaded} reused={reused} failed={failed}",
        **summary,
    )
    return summary


_scheduled_tasks: set[asyncio.Task] = set()


def schedule_symbol_image_download(symbol_ids: list[int] | None = None) -> None:
    """Schedule an ARASAAC image download for newly created symbols.

    Auto-download is the same opt-in maintenance work as the startup backfill:
    it is skipped during tests and unless ``AAC_ENABLE_SYMBOL_IMAGE_BACKFILL``
    is enabled, so normal requests never trigger unexpected network work. When
    enabled, the bounded download runs in the background so symbol creation is
    never blocked by an external image service.
    """
    if os.environ.get("TESTING") == "1":
        return
    if not config.get_bool("AAC_ENABLE_SYMBOL_IMAGE_BACKFILL", False):
        return
    ids = [int(sid) for sid in (symbol_ids or []) if sid]
    if not ids:
        return

    async def _run() -> None:
        try:
            await backfill_missing_symbol_images(symbol_ids=ids)
        except Exception as exc:  # pragma: no cover - defensive logging only
            logger.warning("Scheduled symbol image download failed: {}", exc)

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # Sync FastAPI handlers run on a threadpool without a running loop, so
        # run the download on a short-lived daemon thread instead of blocking.
        def _run_in_thread() -> None:
            try:
                asyncio.run(_run())
            except Exception as exc:  # pragma: no cover - defensive logging only
                logger.warning("Threaded symbol image download failed: {}", exc)

        threading.Thread(
            target=_run_in_thread,
            name="symbol-image-download",
            daemon=True,
        ).start()
        return

    task = asyncio.create_task(_run(), name="symbol-image-download")
    _scheduled_tasks.add(task)
    task.add_done_callback(_scheduled_tasks.discard)
