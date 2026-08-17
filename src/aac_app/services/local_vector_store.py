"""SQLite-backed semantic search for the local symbol library.

The embedding model is intentionally lazy. The SQLite extension and virtual
table are initialized only when the store is first used, which keeps a
core-only/offline startup healthy even when the model cannot be downloaded.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from loguru import logger
from sqlalchemy import event, text
from sqlalchemy.engine import Engine

from src import config
from src.aac_app.utils.module_availability import module_available
from src.aac_app.utils.runtime import safe_streams


def _load_text_embedding_class() -> Any:
    """Import and cache the fastembed ``TextEmbedding`` symbol lazily."""
    global TextEmbedding
    from fastembed import TextEmbedding as text_embedding

    TextEmbedding = text_embedding
    return TextEmbedding


MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIMENSION = 384
VECTOR_TABLE = "symbol_embeddings"
METADATA_TABLE = "symbol_embedding_metadata"
STATE_TABLE = "symbol_embedding_state"
DEFAULT_DISTANCE_THRESHOLD = 1.15


FASTEMBED_AVAILABLE = module_available("fastembed")
SQLITE_VEC_AVAILABLE = module_available("sqlite_vec")
TextEmbedding: Any | None = None
sqlite_vec: Any | None = None
_engine_listener_lock = threading.Lock()
# Warmup and background indexing may both touch the singleton. Serialize
# replacement/close and index operations so one thread cannot close a store
# while another is using it.
vector_store_operation_lock = threading.RLock()


def _load_sqlite_vec_extension(
    dbapi_connection: sqlite3.Connection,
    connection_record: Any | None,
) -> bool:
    """Load sqlite-vec once for a SQLAlchemy connection when possible."""
    global sqlite_vec
    if connection_record is not None and connection_record.info.get("aac_sqlite_vec_loaded"):
        return True
    if not SQLITE_VEC_AVAILABLE:
        return False
    try:
        if sqlite_vec is None:
            import sqlite_vec as sqlite_vec_module

            sqlite_vec = sqlite_vec_module
        dbapi_connection.enable_load_extension(True)
        try:
            sqlite_vec.load(dbapi_connection)
        finally:
            dbapi_connection.enable_load_extension(False)
        if connection_record is not None:
            connection_record.info["aac_sqlite_vec_loaded"] = True
        return True
    except (AttributeError, ImportError, OSError, sqlite3.Error) as exc:
        logger.error("Failed to load sqlite-vec extension: {}", exc)
        return False


class LocalVectorStore:
    """Store MiniLM embeddings in a sqlite-vec ``vec0`` virtual table."""

    def __init__(
        self,
        model_name: str = MODEL_NAME,
        index_path: str | os.PathLike[str] | None = None,
        metadata_path: str | os.PathLike[str] | None = None,
        device: str | None = None,
        lazy_load: bool = True,
        *,
        engine: Engine | None = None,
        embedder: Any | None = None,
        embedder_factory: Callable[..., Any] | None = None,
        cache_dir: str | os.PathLike[str] | None = None,
        embedding_dim: int = EMBEDDING_DIMENSION,
        legacy_index_path: str | os.PathLike[str] | None = None,
        legacy_metadata_path: str | os.PathLike[str] | None = None,
    ):
        self.model_name = model_name
        self.device = device
        self.engine = engine
        self.embedding_dim = embedding_dim
        if cache_dir is not None:
            self.cache_dir = Path(cache_dir).absolute()
            self._local_files_only = False
        else:
            resolved, self._local_files_only = config.resolve_model_cache_dir(
                "models--qdrant--all-MiniLM-L6-v2-onnx"
            )
            self.cache_dir = Path(resolved).absolute()
        self.model: Any | None = embedder
        self.embedder = embedder
        self._embedder_factory = embedder_factory
        self.metadata: list[dict[str, Any]] = []
        self.index = None
        self._model_loaded = embedder is not None
        self._index_loaded = False
        self._schema_ready = False
        self._load_attempted = embedder is not None
        self._listener_engine: Engine | None = None
        self._closed = False
        self._distance_threshold = DEFAULT_DISTANCE_THRESHOLD
        self._legacy_index_path = Path(
            legacy_index_path or index_path or config.get_data_path("vector_store.index")
        )
        self._legacy_metadata_path = Path(
            legacy_metadata_path
            or metadata_path
            or config.get_data_path("vector_store_metadata.json")
        )
        self.index_path = str(self._legacy_index_path)
        self.metadata_path = str(self._legacy_metadata_path)
        self._remove_legacy_files()

        if not lazy_load:
            self.force_load()

    def _remove_legacy_files(self) -> None:
        """Delete legacy on-disk vector artifacts during store construction."""
        for path in (self._legacy_index_path, self._legacy_metadata_path):
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("Could not remove legacy vector file {}: {}", path, exc)

    def _get_engine(self) -> Engine:
        if self._closed:
            raise RuntimeError("LocalVectorStore is closed")
        if self.engine is None:
            from src.aac_app.db import create_engine_instance

            self.engine = create_engine_instance()
        self._install_connection_listener(self.engine)
        return self.engine

    def _install_connection_listener(self, engine: Engine) -> None:
        """Install one engine-owned callback for future SQLite connections."""
        if engine.dialect.name != "sqlite":
            return
        with _engine_listener_lock:
            if getattr(engine, "_aac_sqlite_vec_listener", None) is None:
                def load_extension(
                    dbapi_connection: sqlite3.Connection,
                    connection_record: Any,
                    _connection_proxy: Any,
                ) -> None:
                    _load_sqlite_vec_extension(dbapi_connection, connection_record)

                event.listen(engine, "checkout", load_extension)
                engine._aac_sqlite_vec_listener = load_extension

        self._listener_engine = engine

    def _ensure_schema(self) -> bool:
        """Create the vec0 table, metadata, and completion marker idempotently."""
        if not SQLITE_VEC_AVAILABLE:
            return False
        try:
            engine = self._get_engine()
            with engine.begin() as connection:
                if not self._schema_ready:
                    connection.exec_driver_sql(
                        f"CREATE VIRTUAL TABLE IF NOT EXISTS {VECTOR_TABLE} "
                        f"USING vec0(embedding float[{self.embedding_dim}])"
                    )
                    connection.exec_driver_sql(
                        f"""
                        CREATE TABLE IF NOT EXISTS {METADATA_TABLE} (
                            symbol_id INTEGER PRIMARY KEY,
                            type TEXT NOT NULL DEFAULT 'symbol',
                            label TEXT,
                            text TEXT NOT NULL
                        )
                        """
                    )
                    connection.exec_driver_sql(
                        f"""
                        CREATE TABLE IF NOT EXISTS {STATE_TABLE} (
                            key TEXT PRIMARY KEY,
                            value TEXT NOT NULL
                        )
                        """
                    )
            self._schema_ready = True
            self._index_loaded = True
            return True
        except Exception as exc:
            logger.error("Failed to initialize sqlite-vec schema: {}", exc)
            return False

    def _ensure_model_loaded(self) -> bool:
        """Create the fastembed model lazily, without importing it at startup."""
        global FASTEMBED_AVAILABLE, TextEmbedding
        if self._model_loaded:
            return self.embedder is not None
        if self._load_attempted or not FASTEMBED_AVAILABLE:
            return False
        self._load_attempted = True
        try:
            if not self._local_files_only:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
            with safe_streams():
                if self._embedder_factory is not None:
                    self.embedder = self._embedder_factory(
                        model_name=self.model_name,
                        cache_dir=str(self.cache_dir),
                    )
                else:
                    if TextEmbedding is None:
                        _load_text_embedding_class()
                    self.embedder = TextEmbedding(
                        model_name=self.model_name,
                        cache_dir=str(self.cache_dir),
                        lazy_load=True,
                        local_files_only=self._local_files_only,
                    )
            self.model = self.embedder
            self._model_loaded = True
            logger.info("Fastembed model ready: {} (cache={})", self.model_name, self.cache_dir)
            return True
        except Exception as exc:
            self.embedder = None
            self.model = None
            self._model_loaded = True
            logger.error("Failed to initialize fastembed model: {}", exc)
            return False

    def _embed(self, texts: list[str]) -> list[list[float]] | None:
        if not self._ensure_model_loaded() or self.embedder is None:
            return None
        try:
            try:
                vectors = list(self.embedder.embed(texts, batch_size=256))
            except TypeError:
                vectors = list(self.embedder.embed(texts))
            normalized = [[float(value) for value in vector] for vector in vectors]
            if any(len(vector) != self.embedding_dim for vector in normalized):
                raise ValueError(f"Expected {self.embedding_dim}-dimensional embeddings")
            return normalized
        except Exception as exc:
            logger.error("Embedding operation failed: {}", exc)
            return None

    def _serialize_vector(self, vector: list[float]) -> bytes:
        if sqlite_vec is None:
            import sqlite_vec as sqlite_vec_module

            globals()["sqlite_vec"] = sqlite_vec_module
        return sqlite_vec.serialize_float32(vector)

    def has_persisted_metadata(self) -> bool:
        """Return whether a complete corpus indexing marker exists."""
        if not self._ensure_schema():
            return False
        try:
            with self._get_engine().connect() as connection:
                row = connection.execute(
                    text(f"SELECT value FROM {STATE_TABLE} WHERE key = 'complete' LIMIT 1")
                ).fetchone()
                if not row or row[0] != "1":
                    return False
                vector_count = connection.execute(
                    text(f"SELECT COUNT(*) FROM {VECTOR_TABLE}")
                ).scalar_one()
                metadata_count = connection.execute(
                    text(f"SELECT COUNT(*) FROM {METADATA_TABLE}")
                ).scalar_one()
                if vector_count != metadata_count:
                    return False
                symbols_table = connection.execute(
                    text(
                        "SELECT 1 FROM sqlite_master "
                        "WHERE type = 'table' AND name = 'symbols'"
                    )
                ).first()
                if symbols_table:
                    symbol_ids = {
                        int(row[0]) for row in connection.execute(text("SELECT id FROM symbols"))
                    }
                    vector_ids = {
                        int(row[0])
                        for row in connection.execute(text(f"SELECT rowid FROM {VECTOR_TABLE}"))
                    }
                    metadata_ids = {
                        int(row[0])
                        for row in connection.execute(
                            text(f"SELECT symbol_id FROM {METADATA_TABLE}")
                        )
                    }
                    return symbol_ids == vector_ids == metadata_ids
                return True
        except Exception as exc:
            logger.warning("Could not read vector-store metadata: {}", exc)
            return False

    def get_stale_symbol_ids(self, expected_texts: Mapping[int, str]) -> set[int]:
        """Return symbols whose vector or embedding text is missing or stale."""
        if not expected_texts:
            return set()
        if not self._ensure_schema():
            return set(expected_texts)
        try:
            with self._get_engine().connect() as connection:
                vector_ids = {
                    int(row[0])
                    for row in connection.execute(text(f"SELECT rowid FROM {VECTOR_TABLE}"))
                }
                metadata = {
                    int(row[0]): row[1]
                    for row in connection.execute(
                        text(
                            f"SELECT symbol_id, text FROM {METADATA_TABLE} "
                            "WHERE type = 'symbol'"
                        )
                    )
                }
            return {
                symbol_id
                for symbol_id, expected_text in expected_texts.items()
                if symbol_id not in vector_ids or metadata.get(symbol_id) != expected_text
            }
        except Exception as exc:
            logger.warning("Could not inspect stale symbol embeddings: {}", exc)
            return set(expected_texts)

    def remove_orphaned_symbols(self, symbol_ids: set[int]) -> None:
        """Remove vector rows that no longer have a symbol record."""
        if not self._ensure_schema():
            return
        try:
            with self._get_engine().begin() as connection:
                if symbol_ids:
                    placeholders = ", ".join(
                        f":symbol_{index}" for index in range(len(symbol_ids))
                    )
                    parameters = {
                        f"symbol_{index}": symbol_id
                        for index, symbol_id in enumerate(sorted(symbol_ids))
                    }
                    connection.execute(
                        text(
                            f"DELETE FROM {VECTOR_TABLE} "
                            f"WHERE rowid NOT IN ({placeholders})"
                        ),
                        parameters,
                    )
                    connection.execute(
                        text(
                            f"DELETE FROM {METADATA_TABLE} "
                            f"WHERE symbol_id NOT IN ({placeholders})"
                        ),
                        parameters,
                    )
                else:
                    connection.execute(text(f"DELETE FROM {VECTOR_TABLE}"))
                    connection.execute(text(f"DELETE FROM {METADATA_TABLE}"))
        except Exception as exc:
            logger.warning("Could not remove orphaned symbol embeddings: {}", exc)

    def mark_indexed(self) -> None:
        """Mark the current corpus as indexed after a successful batch."""
        if not self._ensure_schema():
            return
        try:
            with self._get_engine().begin() as connection:
                connection.execute(
                    text(
                        f"INSERT INTO {STATE_TABLE}(key, value) VALUES ('complete', '1') "
                        "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
                    )
                )
        except Exception as exc:
            logger.error("Could not persist vector-store completion marker: {}", exc)

    def load_index_if_available(self) -> None:
        """Initialize the SQLite vector schema without loading fastembed."""
        self._ensure_schema()

    def add_texts(self, texts: list[str], metadatas: list[dict[str, Any]]) -> bool:
        """Upsert text embeddings keyed by the symbol id in each metadata object."""
        if len(texts) != len(metadatas):
            raise ValueError("Number of texts and metadatas must match")
        if not texts:
            return True
        if not self._ensure_schema():
            return False
        vectors = self._embed(texts)
        if vectors is None:
            return False
        try:
            with self._get_engine().begin() as connection:
                for vector, document, metadata in zip(vectors, texts, metadatas, strict=True):
                    symbol_id = metadata.get("id")
                    if symbol_id is None:
                        raise ValueError("Vector metadata must contain an id")
                    connection.execute(
                        text(f"DELETE FROM {VECTOR_TABLE} WHERE rowid = :symbol_id"),
                        {"symbol_id": int(symbol_id)},
                    )
                    connection.execute(
                        text(
                            f"INSERT INTO {VECTOR_TABLE}(rowid, embedding) "
                            "VALUES (:symbol_id, :embedding)"
                        ),
                        {
                            "symbol_id": int(symbol_id),
                            "embedding": self._serialize_vector(vector),
                        },
                    )
                    connection.execute(
                        text(
                            f"""
                            INSERT INTO {METADATA_TABLE}(symbol_id, type, label, text)
                            VALUES (:symbol_id, :type, :label, :text)
                            ON CONFLICT(symbol_id) DO UPDATE SET
                                type = excluded.type,
                                label = excluded.label,
                                text = excluded.text
                            """
                        ),
                        {
                            "symbol_id": int(symbol_id),
                            "type": metadata.get("type", "symbol"),
                            "label": metadata.get("label"),
                            "text": metadata.get("text", document),
                        },
                    )
            self._refresh_metadata_cache()
            logger.info("Upserted {} symbol embeddings", len(texts))
            return True
        except Exception as exc:
            logger.error("Failed to store embeddings: {}", exc)
            return False

    def _refresh_metadata_cache(self) -> None:
        if not self._ensure_schema():
            return
        try:
            with self._get_engine().connect() as connection:
                rows = connection.execute(
                    text(
                        f"SELECT symbol_id, type, label, text "
                        f"FROM {METADATA_TABLE} ORDER BY symbol_id"
                    )
                ).mappings()
                self.metadata = [
                    {
                        "id": row["symbol_id"],
                        "type": row["type"],
                        "label": row["label"],
                        "text": row["text"],
                    }
                    for row in rows
                ]
        except Exception:
            self.metadata = []

    def search(self, query: str, k: int = 5) -> list[dict[str, Any]]:
        """Return nearest symbol metadata, excluding low-confidence matches."""
        if not query or not self._ensure_schema():
            return []
        query_vector = self._embed([query])
        if not query_vector:
            return []
        try:
            with self._get_engine().connect() as connection:
                rows = connection.execute(
                    text(
                        f"""
                        SELECT rowid, distance
                        FROM {VECTOR_TABLE}
                        WHERE embedding MATCH :embedding
                          AND k = :limit
                        ORDER BY distance
                        """
                    ),
                    {
                        "embedding": self._serialize_vector(query_vector[0]),
                        "limit": max(1, int(k)),
                    },
                ).fetchall()
                valid_rows = [
                    (int(symbol_id), float(distance))
                    for symbol_id, distance in rows
                    if float(distance) <= self._distance_threshold
                ]
                if not valid_rows:
                    return []

                # Fetch metadata in one bounded query instead of issuing one
                # SQL query per nearest vector. Rebuild the result order from
                # the sqlite-vec rows because an IN query has no ordering
                # guarantee.
                parameters = {
                    f"symbol_{index}": symbol_id
                    for index, (symbol_id, _distance) in enumerate(valid_rows)
                }
                placeholders = ", ".join(f":symbol_{index}" for index in range(len(parameters)))
                metadata_rows = connection.execute(
                    text(
                        f"SELECT symbol_id, type, label, text "
                        f"FROM {METADATA_TABLE} WHERE symbol_id IN ({placeholders})"
                    ),
                    parameters,
                ).mappings()
                metadata_by_id = {
                    int(metadata["symbol_id"]): metadata for metadata in metadata_rows
                }

                return [
                    {
                        "id": metadata_by_id[symbol_id]["symbol_id"],
                        "type": metadata_by_id[symbol_id]["type"],
                        "label": metadata_by_id[symbol_id]["label"],
                        "text": metadata_by_id[symbol_id]["text"],
                        "score": distance,
                    }
                    for symbol_id, distance in valid_rows
                    if symbol_id in metadata_by_id
                ]
        except Exception as exc:
            logger.error("Semantic vector search failed: {}", exc)
            return []

    def delete_by_metadata(self, key: str, value: Any) -> bool:
        """Delete vectors and metadata matching a supported metadata field."""
        if key not in {"id", "symbol_id", "type", "label", "text"}:
            return False
        if not self._ensure_schema():
            return False
        column = "symbol_id" if key in {"id", "symbol_id"} else key
        try:
            with self._get_engine().begin() as connection:
                rows = connection.execute(
                    text(
                        f"SELECT symbol_id FROM {METADATA_TABLE} "
                        f"WHERE {column} = :value"
                    ),
                    {"value": value},
                ).fetchall()
                for (symbol_id,) in rows:
                    connection.execute(
                        text(f"DELETE FROM {VECTOR_TABLE} WHERE rowid = :symbol_id"),
                        {"symbol_id": symbol_id},
                    )
                    connection.execute(
                        text(
                            f"DELETE FROM {METADATA_TABLE} "
                            "WHERE symbol_id = :symbol_id"
                        ),
                        {"symbol_id": symbol_id},
                    )
            self._refresh_metadata_cache()
            return True
        except Exception as exc:
            logger.error("Failed to delete vector metadata {}={}: {}", key, value, exc)
            return False

    def close(self) -> None:
        """Release store-owned state without disposing the shared database engine."""
        if self._closed:
            return
        self._closed = True
        self._listener_engine = None
        self.metadata.clear()
        self.model = None
        self.embedder = None

    def is_available(self) -> bool:
        """Return dependency availability without loading the embedding model."""
        return not self._closed and SQLITE_VEC_AVAILABLE and (
            self.embedder is not None or FASTEMBED_AVAILABLE
        )

    def is_ready(self) -> bool:
        """Return whether a model and SQLite vector schema are ready."""
        return (
            not self._closed
            and self._model_loaded
            and self.embedder is not None
            and self._schema_ready
        )

    def force_load(self) -> None:
        """Force model/schema initialization for explicit warmup callers."""
        self._ensure_schema()
        self._ensure_model_loaded()
