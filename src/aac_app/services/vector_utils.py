from loguru import logger
from src.aac_app.models.database import Symbol, get_session
from src.api.dependencies import get_vector_store

def index_all_symbols(force: bool = False):
    """Index all symbols into the vector store."""
    try:
        vs = get_vector_store()
        if not vs or not vs.model:
            logger.warning("Vector store not available, skipping symbol indexing")
            return

        # Check if already indexed (hacky check: if metadata is not empty)
        # In a real system we'd check specifically for type='symbol'
        if not force and len(vs.metadata) > 0:
            logger.info("Vector store already populated, skipping indexing")
            return

        logger.info("Indexing all symbols into vector store...")
        with get_session() as db:
            symbols = db.query(Symbol).all()
            texts = []
            metadatas = []
            
            for sym in symbols:
                # Create a rich text representation for embedding
                text_parts = [sym.label]
                if sym.description:
                    text_parts.append(sym.description)
                if sym.keywords:
                    text_parts.append(sym.keywords.replace(",", " "))
                if sym.category:
                    text_parts.append(sym.category)
                
                text = ". ".join(text_parts)
                texts.append(text)
                metadatas.append({
                    "id": sym.id,
                    "type": "symbol",
                    "label": sym.label,
                    "text": text
                })
            
            if texts:
                # Batch add might be better, but LocalVectorStore adds all at once currently
                vs.add_texts(texts, metadatas)
                logger.info(f"Successfully indexed {len(texts)} symbols")
            else:
                logger.info("No symbols found to index")

    except Exception as e:
        logger.error(f"Failed to index symbols: {e}")

def index_symbol(symbol: Symbol):
    """Index a single symbol into the vector store."""
    try:
        vs = get_vector_store()
        if not vs or not vs.model:
            logger.warning("Vector store not available, skipping symbol indexing")
            return

        # Create a rich text representation for embedding
        text_parts = [symbol.label]
        if symbol.description:
            text_parts.append(symbol.description)
        if symbol.keywords:
            text_parts.append(symbol.keywords.replace(",", " "))
        if symbol.category:
            text_parts.append(symbol.category)
        
        text = ". ".join(text_parts)
        metadata = {
            "id": symbol.id,
            "type": "symbol",
            "label": symbol.label,
            "text": text
        }
        
        # Add to vector store
        vs.add_texts([text], [metadata])
        logger.info(f"Successfully indexed symbol: {symbol.label}")

    except Exception as e:
        logger.error(f"Failed to index symbol {symbol.label}: {e}")
