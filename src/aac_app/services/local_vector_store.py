"""SQLite-backed semantic search for the local symbol library.

The embedding model is intentionally lazy.  The SQLite extension and virtual
table are initialized only when the store is first used, which keeps a
core-only/offline startup healthy even when the model cannot be downloaded.
"""

from __future__ import annotations

import importlib.util
import os
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

from loguru import logger
from sqlalchemy import event, text
from sqlalchemy.engine import Engine

from src import config

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIMENSION = 384
VECTOR_TABLE = "symbol_embeddings"
METADATA_TABLE = "symbol_embedding_metadata"
STATE_TABLE = "symbol_embedding_state"
DEFAULT_DISTANCE_THRESHOLD = 1.15


def _module_available(module_name: str) -> bool:
    """Check for an optional dependency without importing it."""
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


FASTEMBED_AVAILABLE = _module_available("fastembed")
SQLITE_VEC_AVAILABLE = _module_available("sqlite_vec")
TextEmbedding: Any | None = None
sqlite_vec: Any | None = None


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
        self.cache_dir = Path(cache_dir or config.get_data_path("models")).absolute()
        self.model: Any | None = embedder
        self.embedder = embedder
        self._embedder_factory = embedder_factory
        self.metadata: list[dict[str, Any]] = []
        self.index = None  # Compatibility attribute; vectors now live in SQLite.
        self._model_loaded = embedder is not None
        self._index_loaded = False
        self._schema_ready = False
        self._load_attempted = embedder is not None
        self._loaded_connections: set[int] = set()
        self._sqlite_vec_failed = False
        self._distance_threshold = DEFAULT_DISTANCE_THRESHOLD
        self._legacy_index_path = Path(
            legacy_index_path
            or index_path
            or config.get_data_path("vector_store.index")
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
        if self.engine is None:
            from src.aac_app.db import ensure_tables

            self.engine = ensure_tables()
        self._install_connection_listener(self.engine)
        return self.engine

    def _install_connection_listener(self, engine: Engine) -> None:
        """Load sqlite-vec for every future SQLAlchemy DBAPI connection."""
        if engine.dialect.name != "sqlite" or getattr(
            engine, "_aac_sqlite_vec_listener_installed", False
        ):
            return

        def load_extension(dbapi_connection: sqlite3.Connection, _connection_record) -> None:
            self._load_sqlite_vec(dbapi_connection)

        event.listen(engine, "connect", load_extension)
        engine._aac_sqlite_vec_listener_installed = True

    def _load_sqlite_vec(self, dbapi_connection: sqlite3.Connection) -> bool:
        """Load sqlite-vec once per DBAPI connection with extension loading closed."""
        global SQLITE_VEC_AVAILABLE, sqlite_vec
        connection_id = id(dbapi_connection)
        if connection_id in self._loaded_connections:
            return True
        if self._sqlite_vec_failed or not SQLITE_VEC_AVAILABLE:
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
            self._loaded_connections.add(connection_id)
            return True
        except (AttributeError, ImportError, OSError, sqlite3.Error) as exc:
            self._sqlite_vec_failed = True
            logger.error("Failed to load sqlite-vec extension: {}", exc)
            return False

    def _connection_driver(self, connection: Any) -> sqlite3.Connection:
        """Get the sqlite3 DBAPI connection from a SQLAlchemy connection."""
        raw_connection = connection.connection
        driver_connection = getattr(raw_connection, "driver_connection", raw_connection)
        if not isinstance(driver_connection, sqlite3.Connection):
            raise TypeError("sqlite-vec requires a sqlite3 SQLAlchemy connection")
        return driver_connection

    def _ensure_schema(self) -> bool:
        """Create the vec0 table, metadata, and completion marker idempotently."""
        if not SQLITE_VEC_AVAILABLE:
            return False
        try:
            engine = self._get_engine()
            with engine.begin() as connection:
                dbapi_connection = self._connection_driver(connection)
                if not self._load_sqlite_vec(dbapi_connection):
                    return False
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
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            if self._embedder_factory is not None:
                self.embedder = self._embedder_factory(
                    model_name=self.model_name,
                    cache_dir=str(self.cache_dir),
                )
            else:
                if TextEmbedding is None:
                    from fastembed import TextEmbedding as text_embedding

                    TextEmbedding = text_embedding
                self.embedder = TextEmbedding(
                    model_name=self.model_name,
                    cache_dir=str(self.cache_dir),
                    lazy_load=True,
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
                # Keep the store easy to unit-test with a tiny embedder.
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
                    text(
                        f"SELECT value FROM {STATE_TABLE} "
                        "WHERE key = 'complete' LIMIT 1"
                    )
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
                    symbol_count = connection.execute(
                        text("SELECT COUNT(*) FROM symbols")
                    ).scalar_one()
                    return metadata_count >= symbol_count
                return True
        except Exception as exc:
            logger.warning("Could not read vector-store metadata: {}", exc)
            return False

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
                    label = metadata.get("label")
                    item_type = metadata.get("type", "symbol")
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
                            "type": item_type,
                            "label": label,
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
                results: list[dict[str, Any]] = []
                for symbol_id, distance in rows:
                    if float(distance) > self._distance_threshold:
                        continue
                    metadata = connection.execute(
                        text(
                            f"SELECT symbol_id, type, label, text "
                            f"FROM {METADATA_TABLE} WHERE symbol_id = :symbol_id"
                        ),
                        {"symbol_id": int(symbol_id)},
                    ).mappings().first()
                    if metadata is None:
                        continue
                    results.append(
                        {
                            "id": metadata["symbol_id"],
                            "type": metadata["type"],
                            "label": metadata["label"],
                            "text": metadata["text"],
                            "score": float(distance),
                        }
                    )
                return results
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

    def is_available(self) -> bool:
        """Return dependency availability without loading the embedding model."""
        return SQLITE_VEC_AVAILABLE and (
            self.embedder is not None or FASTEMBED_AVAILABLE
        )

    def is_ready(self) -> bool:
        """Return whether a model and SQLite vector schema are ready."""
        return self._model_loaded and self.embedder is not None and self._schema_ready

    def force_load(self) -> None:
        """Force model/schema initialization for explicit warmup callers."""
        self._ensure_schema()
        self._ensure_model_loaded()
