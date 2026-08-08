from __future__ import annotations

import re
from contextlib import suppress
from pathlib import PurePosixPath

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


def _reusable_image_path(db, symbol: Symbol) -> str | None:
    candidate = (
        db.query(Symbol.image_path)
        .filter(
            Symbol.id != symbol.id,
            func.lower(Symbol.label) == symbol.label.casefold(),
            Symbol.category == symbol.category,
            Symbol.image_path.is_not(None),
            func.trim(Symbol.image_path) != "",
        )
        .order_by(Symbol.id.asc())
        .first()
    )
    if not candidate:
        return None
    public_path = candidate[0]
    return public_path if _public_path_exists(public_path) else None


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
    filename = f"arasaac_auto_{symbol_id}_{arasaac_id}.png"
    file_path = uploads_dir / filename
    file_path.write_bytes(content)
    return f"/uploads/symbols/{filename}"


async def backfill_missing_symbol_images(limit: int = 100) -> dict[str, int]:
    summary = {
        "processed": 0,
        "updated": 0,
        "downloaded": 0,
        "reused": 0,
        "failed": 0,
    }
    if limit <= 0:
        return summary

    with get_session() as db:
        symbol_ids = [
            symbol_id
            for symbol_id, in (
                db.query(Symbol.id)
                .filter(_missing_image_clause())
                .order_by(Symbol.is_builtin.desc(), Symbol.id.asc())
                .limit(limit)
                .all()
            )
        ]

    if not symbol_ids:
        return summary

    service = ArasaacService()
    try:
        for symbol_id in symbol_ids:
            summary["processed"] += 1
            try:
                with get_session() as db:
                    symbol = db.query(Symbol).filter(Symbol.id == symbol_id).first()
                    if symbol is None or (symbol.image_path and symbol.image_path.strip()):
                        continue

                    reusable_path = _reusable_image_path(db, symbol)
                    if reusable_path:
                        symbol.image_path = reusable_path
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

                    symbol.image_path = _store_downloaded_image(
                        symbol.id, int(arasaac_id), image_content
                    )
                    summary["updated"] += 1
                    summary["downloaded"] += 1
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
