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

        # Metadata is enough to know that indexing already happened. Do this
        # before loading the embedding model so startup stays light.
        has_persisted_metadata = getattr(vs, "has_persisted_metadata", lambda: False)
        if not force and (
            has_persisted_metadata() or len(getattr(vs, "metadata", [])) > 0
        ):
            logger.info("Vector store metadata already exists, skipping indexing")
            return

        if not vs.is_available():
            logger.warning("Vector store not available, skipping symbol indexing")
            return

        # First run is the only path that may load the embedding model.
        vs.load_index_if_available()
        logger.info("Indexing all symbols into vector store...")
        with get_session() as db:
            symbols = db.query(Symbol).all()
            texts = []
            metadatas = []

            for sym in symbols:
                text, metadata = _symbol_embedding(sym)
                texts.append(text)
                metadatas.append(metadata)

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
