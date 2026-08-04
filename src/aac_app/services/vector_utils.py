from loguru import logger

from src.aac_app.db import get_session
from src.aac_app.models import Symbol
from src.api.deps import get_vector_store


def index_all_symbols(force: bool = False):
    """Index all symbols into the vector store."""
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

        # Query symbols before loading the embedding model — an empty
        # library needs no model download.
        with get_session() as db:
            symbols = db.query(Symbol).all()

        if not symbols:
            vs.mark_indexed()
            logger.info("No symbols found to index; skipping model load")
            return

        # First run is the only path that may load the embedding model.
        vs.load_index_if_available()
        logger.info("Indexing all symbols into vector store...")
        symbol_embeddings = [_symbol_embedding(sym) for sym in symbols]

        if not force and supports_repair:
            expected_texts = {
                sym.id: text
                for sym, (text, _metadata) in zip(
                    symbols, symbol_embeddings, strict=True
                )
            }
            remove_orphaned = getattr(vs, "remove_orphaned_symbols", None)
            if remove_orphaned is not None:
                remove_orphaned(set(expected_texts))
            stale_ids = vs.get_stale_symbol_ids(expected_texts)
            if not stale_ids:
                vs.mark_indexed()
                logger.info("Vector store embeddings are already current")
                return
            selected = [
                (sym, embedding)
                for sym, embedding in zip(symbols, symbol_embeddings, strict=True)
                if sym.id in stale_ids
            ]
        else:
            selected = list(zip(symbols, symbol_embeddings, strict=True))

        texts = [embedding[0] for _symbol, embedding in selected]
        metadatas = [embedding[1] for _symbol, embedding in selected]

        if texts:
            if vs.add_texts(texts, metadatas):
                vs.mark_indexed()
                logger.info(f"Successfully indexed {len(texts)} symbols")
            else:
                logger.warning("Symbol indexing did not complete; will retry later")
        else:
            vs.mark_indexed()
            logger.info("No symbols found to index")

    except Exception as e:
        logger.error(f"Failed to index symbols: {e}")


def _symbol_embedding(symbol: Symbol) -> tuple[str, dict]:
    """Build the stable text and metadata representation for a symbol."""
    text_parts = [symbol.label]
    if symbol.description:
        text_parts.append(symbol.description)
    if symbol.keywords:
        text_parts.append(symbol.keywords.replace(",", " "))
    if symbol.category:
        text_parts.append(symbol.category)

    text = ". ".join(text_parts)
    return text, {
        "id": symbol.id,
        "type": "symbol",
        "label": symbol.label,
        "text": text,
    }


def index_symbol(symbol: Symbol) -> bool:
    """Index a single symbol into the vector store."""
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
    try:
        vs = get_vector_store()
        if not vs or not vs.is_available():
            return False
        return vs.delete_by_metadata("id", symbol_id)
    except Exception as e:
        logger.error(f"Failed to delete embedding for symbol {symbol_id}: {e}")
        return False
