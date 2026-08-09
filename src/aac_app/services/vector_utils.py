from loguru import logger

from src.aac_app.db import get_session
from src.aac_app.models import Symbol
from src.aac_app.services.local_vector_store import vector_store_operation_lock

_INDEX_BATCH_SIZE = 1000


def get_vector_store():
    """Resolve the provider lazily to avoid an API-router import cycle."""
    from src.api.deps import get_vector_store as resolve_vector_store

    return resolve_vector_store()


def index_all_symbols(force: bool = False):
    """Index all symbols into the vector store."""
    with vector_store_operation_lock:
        return _index_all_symbols(force=force)


def _index_all_symbols(force: bool = False):
    try:
        vs = get_vector_store()
        if not vs:
            return

        # A complete marker plus exact symbol/vector ids is enough to know
        # indexing already happened. Do this before loading the model so
        # healthy startup stays light.
        has_persisted_metadata = getattr(vs, "has_persisted_metadata", lambda: False)
        persisted = has_persisted_metadata()
        supports_repair = callable(getattr(type(vs), "get_stale_symbol_ids", None))
        if not force and not supports_repair and (
            persisted or len(getattr(vs, "metadata", [])) > 0
        ):
            logger.info("Vector store metadata already exists, skipping indexing")
            return

        if not vs.is_available():
            logger.warning("Vector store not available, skipping symbol indexing")
            return

        # Read only fields needed for embeddings and stream bounded batches.
        # Keeping ORM rows and vectors out of one giant list matters on low-RAM
        # desktop deployments with a large symbol catalog.
        def symbol_rows(db):
            query = db.query(
                Symbol.id,
                Symbol.label,
                Symbol.description,
                Symbol.keywords,
                Symbol.category,
            )
            if hasattr(query, "order_by"):
                query = query.order_by(Symbol.id)
            return query.yield_per(_INDEX_BATCH_SIZE)

        selected_ids: set[int] | None = None
        expected_texts: dict[int, str] | None = None
        if force or not supports_repair:
            # Preserve the empty-catalog fast path without materializing rows.
            with get_session() as db:
                query = symbol_rows(db)
                first_row = query.first() if hasattr(query, "first") else next(iter(query), None)
            if first_row is None:
                vs.mark_indexed()
                logger.info("No symbols found to index; skipping model load")
                return
        if not force and supports_repair:
            # Repair mode needs a scalar snapshot to identify stale/orphaned
            # vectors. This is intentionally the only full-catalog allocation.
            with get_session() as db:
                expected_texts = {
                    row[0]: _symbol_embedding_values(
                        row[0], row[1], row[2], row[3], row[4]
                    )[0]
                    for row in symbol_rows(db)
                }
            if not expected_texts:
                vs.mark_indexed()
                logger.info("No symbols found to index; skipping model load")
                return
            remove_orphaned = getattr(vs, "remove_orphaned_symbols", None)
            if remove_orphaned is not None:
                remove_orphaned(set(expected_texts))
            selected_ids = vs.get_stale_symbol_ids(expected_texts)
            if not selected_ids:
                vs.mark_indexed()
                logger.info("Vector store embeddings are already current")
                return

        # First run is the only path that may load the embedding model.
        vs.load_index_if_available()
        logger.info("Indexing all symbols into vector store...")

        def read_batch(last_id: int, fallback_offset: int) -> tuple[list[tuple], bool]:
            with get_session() as db:
                query = symbol_rows(db)
                if hasattr(query, "filter") and hasattr(query, "limit"):
                    # Keyset pagination keeps each batch bounded and avoids
                    # rescanning all preceding rows as the catalog grows.
                    if last_id >= 0:
                        query = query.filter(Symbol.id > last_id)
                    return list(query.limit(_INDEX_BATCH_SIZE)), True
                if hasattr(query, "offset"):
                    # Keep older/simple test doubles compatible without
                    # affecting the SQLAlchemy production path above.
                    return list(query.offset(fallback_offset).limit(_INDEX_BATCH_SIZE)), False
                # A one-shot iterable is enough for minimal test doubles and
                # must not be replayed indefinitely.
                return (list(query), False) if fallback_offset == 0 else ([], False)

        indexed_count = 0
        last_id = -1
        fallback_offset = 0
        while True:
            rows, used_keyset = read_batch(last_id, fallback_offset)
            if not rows:
                break
            if used_keyset:
                last_id = rows[-1][0]
            else:
                fallback_offset += len(rows)

            texts: list[str] = []
            metadatas: list[dict] = []
            for row in rows:
                if selected_ids is not None and row[0] not in selected_ids:
                    continue
                text, metadata = _symbol_embedding_values(
                    row[0], row[1], row[2], row[3], row[4]
                )
                texts.append(text)
                metadatas.append(metadata)

            if texts:
                if not vs.add_texts(texts, metadatas):
                    logger.warning("Symbol indexing did not complete; will retry later")
                    return
                indexed_count += len(texts)

        vs.mark_indexed()
        logger.info("Successfully indexed {} symbols", indexed_count)

    except Exception as e:
        logger.error(f"Failed to index symbols: {e}")


def _symbol_embedding_values(
    symbol_id: int,
    label: str,
    description: str | None,
    keywords: str | None,
    category: str | None,
) -> tuple[str, dict]:
    """Build the stable text and metadata representation from scalar fields."""
    text_parts = [label]
    if description:
        text_parts.append(description)
    if keywords:
        text_parts.append(keywords.replace(",", " "))
    if category:
        text_parts.append(category)

    text = ". ".join(text_parts)
    return text, {
        "id": symbol_id,
        "type": "symbol",
        "label": label,
        "text": text,
    }


def _symbol_embedding(symbol: Symbol) -> tuple[str, dict]:
    """Build an embedding from a Symbol object for single-symbol callers."""
    return _symbol_embedding_values(
        symbol.id,
        symbol.label,
        symbol.description,
        symbol.keywords,
        symbol.category,
    )


def index_symbol(symbol: Symbol) -> bool:
    """Index a single symbol into the vector store."""
    with vector_store_operation_lock:
        return _index_symbol(symbol)


def _index_symbol(symbol: Symbol) -> bool:
    try:
        vs = get_vector_store()
        if not vs or not vs.is_available():
            logger.warning("Vector store not available, skipping symbol indexing")
            return False

        text, metadata = _symbol_embedding(symbol)
        indexed = vs.add_texts([text], [metadata])
        if indexed:
            logger.info(f"Successfully indexed symbol: {symbol.label}")
        return indexed

    except Exception as e:
        logger.error(f"Failed to index symbol {symbol.label}: {e}")
        return False


def delete_symbol(symbol_id: int) -> bool:
    """Remove a symbol's embedding after the ORM record is deleted."""
    with vector_store_operation_lock:
        return _delete_symbol(symbol_id)


def _delete_symbol(symbol_id: int) -> bool:
    try:
        vs = get_vector_store()
        if not vs or not vs.is_available():
            return False
        return vs.delete_by_metadata("id", symbol_id)
    except Exception as e:
        logger.error(f"Failed to delete embedding for symbol {symbol_id}: {e}")
        return False
