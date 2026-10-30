import json
import os
from typing import Any, Dict, List

import numpy as np
from loguru import logger

try:
    import faiss

    FAISS_AVAILABLE = True
except ImportError:
    logger.warning("faiss not installed. Vector store will be disabled.")
    FAISS_AVAILABLE = False

try:
    from sentence_transformers import SentenceTransformer

    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    logger.warning(
        "sentence-transformers not installed. Vector store will be disabled."
    )
    SENTENCE_TRANSFORMERS_AVAILABLE = False


class LocalVectorStore:
    """
    Local vector store using FAISS and Sentence Transformers.
    Stores embeddings for semantic search and predictions.
    
    Uses LAZY LOADING - model is only loaded on first actual use,
    not during initialization. This dramatically improves startup time.
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        index_path: str = "data/vector_store.index",
        metadata_path: str = "data/vector_store_metadata.json",
        device: str = None,
        lazy_load: bool = True,
    ):
        self.model_name = model_name
        self.index_path = index_path
        self.metadata_path = metadata_path
        self.model = None
        self.index = None
        self.metadata: List[Dict[str, Any]] = []
        self._model_loaded = False
        self._index_loaded = False
        self._lazy_load = lazy_load
        
        # Auto-detect device if not specified
        if device is None:
            try:
                import torch
                self.device = "cuda" if torch.cuda.is_available() else "cpu"
            except ImportError:
                self.device = "cpu"
        else:
            self.device = device

        if not FAISS_AVAILABLE or not SENTENCE_TRANSFORMERS_AVAILABLE:
            logger.warning("Vector store disabled due to missing dependencies")
        elif not lazy_load:
            # Immediate loading (backwards compatible for warmup)
            self._load_model()
            self._load_index()

    def _ensure_model_loaded(self):
        """Ensure model is loaded (lazy loading)"""
        if self._model_loaded or not SENTENCE_TRANSFORMERS_AVAILABLE:
            return
        self._load_model()
        
    def _ensure_index_loaded(self):
        """Ensure index is loaded (lazy loading)"""
        if self._index_loaded or not FAISS_AVAILABLE:
            return
        self._load_index()

    def _load_model(self):
        """Load Sentence Transformer model"""
        if not SENTENCE_TRANSFORMERS_AVAILABLE or self._model_loaded:
            return
        try:
            logger.info(f"Loading embedding model: {self.model_name} on {self.device}")
            self.model = SentenceTransformer(self.model_name, device=self.device)
            self._model_loaded = True
            logger.info(f"Embedding model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            self.model = None
            self._model_loaded = True  # Mark as attempted to avoid retry loops

    def _load_index(self):
        """Load FAISS index and metadata"""
        if not FAISS_AVAILABLE or self._index_loaded:
            return
        if os.path.exists(self.index_path) and os.path.exists(self.metadata_path):
            try:
                self.index = faiss.read_index(self.index_path)

                if self.metadata_path.endswith(".json"):
                    with open(self.metadata_path, "r", encoding="utf-8") as f:
                        self.metadata = json.load(f)
                else:
                    # Legacy format not supported for security reasons
                    logger.warning(
                        f"Metadata file {self.metadata_path} is not JSON. Starting with empty metadata."
                    )
                    self.metadata = []

                self._index_loaded = True
                logger.info(f"Loaded vector store with {self.index.ntotal} items")
            except Exception as e:
                logger.error(f"Failed to load vector store: {e}")
                self._create_new_index()
        else:
            self._create_new_index()
        self._index_loaded = True

    def _create_new_index(self):
        """Create a new FAISS index"""
        if not FAISS_AVAILABLE:
            return
        # Dimension for all-MiniLM-L6-v2 is 384
        dimension = 384
        self.index = faiss.IndexFlatL2(dimension)
        self.metadata = []
        # Update metadata path to use .json if it was default
        if self.metadata_path.endswith(".pkl"):
            self.metadata_path = self.metadata_path.replace(".pkl", ".json")
        logger.info("Created new vector store index")

    def save(self):
        """Save index and metadata to disk"""
        if not self.index or not FAISS_AVAILABLE:
            return
        try:
            os.makedirs(os.path.dirname(self.index_path), exist_ok=True)
            faiss.write_index(self.index, self.index_path)

            # Force using JSON for metadata
            if self.metadata_path.endswith(".pkl"):
                self.metadata_path = self.metadata_path.replace(".pkl", ".json")

            with open(self.metadata_path, "w", encoding="utf-8") as f:
                json.dump(self.metadata, f, ensure_ascii=False, indent=2)
            logger.info("Saved vector store to disk")
        except Exception as e:
            logger.error(f"Failed to save vector store: {e}")

    def add_texts(self, texts: List[str], metadatas: List[Dict[str, Any]]):
        """Add texts and metadata to the store"""
        # Lazy load model and index on first use
        self._ensure_model_loaded()
        self._ensure_index_loaded()
        
        if not self.model or not self.index:
            logger.error("Vector store not initialized")
            return

        if len(texts) != len(metadatas):
            raise ValueError("Number of texts and metadatas must match")

        try:
            # Ensure text is stored in metadata for reconstruction/debugging
            enriched_metadatas = []
            for text, meta in zip(texts, metadatas):
                meta_copy = meta.copy()
                if "text" not in meta_copy:
                    meta_copy["text"] = text
                enriched_metadatas.append(meta_copy)

            embeddings = self.model.encode(texts)
            self.index.add(np.array(embeddings).astype("float32"))
            self.metadata.extend(enriched_metadatas)
            self.save()
            logger.info(f"Added {len(texts)} items to vector store")
        except Exception as e:
            logger.error(f"Failed to add texts to vector store: {e}")

    def search(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        """Search for similar texts"""
        # Lazy load model and index on first use
        self._ensure_model_loaded()
        self._ensure_index_loaded()
        
        if not self.model or not self.index or self.index.ntotal == 0:
            return []

        try:
            query_vector = self.model.encode([query])
            distances, indices = self.index.search(
                np.array(query_vector).astype("float32"), k
            )

            results = []
            for i, idx in enumerate(indices[0]):
                if idx != -1 and idx < len(self.metadata):
                    item = self.metadata[idx].copy()
                    item["score"] = float(distances[0][i])
                    results.append(item)
            return results
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

    def delete_by_metadata(self, key: str, value: Any):
        """Delete items matching metadata criteria (Rebuilds index)"""
        # Lazy load on first use
        self._ensure_model_loaded()
        self._ensure_index_loaded()
        
        if not self.index:
            return

        new_metadata = []
        texts_to_reindex = []
        deleted_count = 0

        for meta in self.metadata:
            if meta.get(key) != value:
                new_metadata.append(meta)
                # If we have the text, we can re-index it. 
                # If not, we keep the metadata but we can't add it back to the vector index 
                # without the text! This implies we MUST have text in metadata.
                if "text" in meta:
                    texts_to_reindex.append(meta["text"])
                else:
                    logger.warning(f"Skipping item in rebuild: Missing 'text' in metadata: {meta}")
            else:
                deleted_count += 1

        if deleted_count == 0:
            return  # Nothing to delete

        logger.info(f"Deleting {deleted_count} items matching {key}={value}. Rebuilding index...")

        # Rebuild index
        self._create_new_index()
        
        if texts_to_reindex:
            try:
                embeddings = self.model.encode(texts_to_reindex)
                self.index.add(np.array(embeddings).astype("float32"))
                self.metadata = new_metadata
                self.save()
                logger.info(f"Rebuilt vector store with {len(texts_to_reindex)} items")
            except Exception as e:
                logger.error(f"Failed to rebuild index during deletion: {e}")
                # We might be in a bad state here if save() fails, but metadata is in memory
        else:
            self.metadata = []
            self.save()
            logger.info("Vector store empty after deletion")

    def is_available(self) -> bool:
        """Check if vector store dependencies are available (without loading model)"""
        return FAISS_AVAILABLE and SENTENCE_TRANSFORMERS_AVAILABLE
    
    def is_ready(self) -> bool:
        """Check if vector store is fully initialized and ready"""
        return self._model_loaded and self._index_loaded and self.model is not None
    
    def force_load(self):
        """Force immediate loading of model and index (for warmup)"""
        self._ensure_model_loaded()
        self._ensure_index_loaded()
