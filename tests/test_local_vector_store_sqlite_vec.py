from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.aac_app.models import Base, Symbol
from src.aac_app.services import vector_utils
from src.aac_app.services.local_vector_store import LocalVectorStore
from src.api import deps
from src.api.routers.symbols import _apply_symbol_search


class FakeEmbedder:
    def __init__(self, vectors: dict[str, list[float]]):
        self.vectors = vectors

    def embed(self, documents):
        return [self.vectors[document] for document in documents]


class RecordingEmbedder:
    def __init__(self):
        self.calls: list[list[str]] = []

    def embed(self, documents):
        self.calls.append(list(documents))
        return [[1.0, 0.0, 0.0] for _ in documents]


def make_store(tmp_path: Path, vectors: dict[str, list[float]]) -> LocalVectorStore:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    store = LocalVectorStore(
        engine=engine,
        embedder=FakeEmbedder(vectors),
        embedding_dim=3,
        legacy_index_path=tmp_path / "vector_store.index",
        legacy_metadata_path=tmp_path / "vector_store_metadata.json",
    )
    # The store retains the engine for its lifetime; tests dispose it through
    # the helper below after each operation.
    return store


def dispose_store(store: LocalVectorStore) -> None:
    store.engine.dispose()


def test_sqlite_vec_add_search_update_and_delete(tmp_path):
    vectors = {
        "cow farm animal": [1.0, 0.0, 0.0],
        "horse farm animal": [0.9, 0.1, 0.0],
        "apple food": [0.0, 1.0, 0.0],
        "farm animal": [1.0, 0.0, 0.0],
    }
    store = make_store(tmp_path, vectors)
    try:
        store.add_texts(
            ["cow farm animal", "horse farm animal", "apple food"],
            [
                {"id": 1, "type": "symbol", "label": "cow"},
                {"id": 2, "type": "symbol", "label": "horse"},
                {"id": 3, "type": "symbol", "label": "apple"},
            ],
        )

        results = store.search("farm animal", k=3)
        assert [result["id"] for result in results] == [1, 2]

        store.add_texts(
            ["farm animal"],
            [{"id": 1, "type": "symbol", "label": "apple"}],
        )
        assert store.search("farm animal", k=3)[0]["label"] == "apple"

        store.delete_by_metadata("id", 1)
        assert [result["id"] for result in store.search("farm animal", k=3)] == [2]
    finally:
        dispose_store(store)


def test_migration_removes_legacy_files_and_persists_completion(tmp_path):
    legacy_index = tmp_path / "vector_store.index"
    legacy_metadata = tmp_path / "vector_store_metadata.json"
    legacy_index.write_bytes(b"old")
    legacy_metadata.write_text("[]", encoding="utf-8")

    store = make_store(tmp_path, {"one": [1.0, 0.0, 0.0]})
    try:
        assert not legacy_index.exists()
        assert not legacy_metadata.exists()

        store.add_texts(["one"], [{"id": 10, "type": "symbol", "label": "one"}])
        store.mark_indexed()

        restarted = LocalVectorStore(
            engine=store.engine,
            embedder=FakeEmbedder({"one": [1.0, 0.0, 0.0]}),
            embedding_dim=3,
        )
        assert restarted.has_persisted_metadata()
        with store.engine.connect() as connection:
            tables = connection.execute(
                text(
                    "SELECT name, type FROM sqlite_master "
                    "WHERE name IN ('symbol_embeddings', 'symbol_embedding_metadata')"
                )
            ).fetchall()
        assert {table[0] for table in tables} == {
            "symbol_embeddings",
            "symbol_embedding_metadata",
        }
    finally:
        dispose_store(store)


def test_startup_repairs_missing_vector_even_when_table_counts_match(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        session.add_all(
            [
                Symbol(id=1, label="cow", description="farm animal"),
                Symbol(id=2, label="horse", description="farm animal"),
            ]
        )
        session.commit()

        initial = LocalVectorStore(
            engine=engine,
            embedder=FakeEmbedder(
                {
                    "cow. farm animal. general": [1.0, 0.0, 0.0],
                    "horse. farm animal. general": [0.0, 1.0, 0.0],
                }
            ),
            embedding_dim=3,
        )
        initial.add_texts(
            ["cow. farm animal. general", "horse. farm animal. general"],
            [
                {
                    "id": 1,
                    "type": "symbol",
                    "label": "cow",
                    "text": "cow. farm animal. general",
                },
                {
                    "id": 2,
                    "type": "symbol",
                    "label": "horse",
                    "text": "horse. farm animal. general",
                },
            ],
        )
        initial.mark_indexed()

        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM symbol_embeddings WHERE rowid = :symbol_id"),
                {"symbol_id": 1},
            )
            connection.execute(
                text(
                    "INSERT INTO symbol_embeddings(rowid, embedding) "
                    "VALUES (:symbol_id, :embedding)"
                ),
                {
                    "symbol_id": 999,
                    "embedding": initial._serialize_vector([0.0, 0.0, 1.0]),
                },
            )

        recorder = RecordingEmbedder()
        restarted = LocalVectorStore(engine=engine, embedder=recorder, embedding_dim=3)

        @contextmanager
        def session_context():
            yield session

        monkeypatch.setattr(vector_utils, "get_vector_store", lambda: restarted)
        monkeypatch.setattr(vector_utils, "get_session", session_context)

        vector_utils.index_all_symbols()

        assert recorder.calls == [["cow. farm animal. general"]]
        with engine.connect() as connection:
            vector_ids = {
                row[0]
                for row in connection.execute(
                    text("SELECT rowid FROM symbol_embeddings")
                ).fetchall()
            }
        assert vector_ids == {1, 2}
        assert restarted.has_persisted_metadata()
    finally:
        session.close()
        engine.dispose()


def test_healthy_store_skips_model_load_and_reindex(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        session.add(Symbol(id=1, label="cow", description="farm animal"))
        session.commit()

        initial = LocalVectorStore(
            engine=engine,
            embedder=FakeEmbedder({"cow. farm animal. general": [1.0, 0.0, 0.0]}),
            embedding_dim=3,
        )
        initial.add_texts(
            ["cow. farm animal. general"],
            [
                {
                    "id": 1,
                    "type": "symbol",
                    "label": "cow",
                    "text": "cow. farm animal. general",
                }
            ],
        )
        initial.mark_indexed()

        def fail_if_loaded(**_):
            raise AssertionError("healthy vector stores must not load the model")

        restarted = LocalVectorStore(
            engine=engine,
            embedder_factory=fail_if_loaded,
            embedding_dim=3,
        )

        @contextmanager
        def session_context():
            yield session

        monkeypatch.setattr(vector_utils, "get_vector_store", lambda: restarted)
        monkeypatch.setattr(vector_utils, "get_session", session_context)

        vector_utils.index_all_symbols()

        assert not restarted._model_loaded
        assert not restarted._load_attempted
    finally:
        session.close()
        engine.dispose()


def test_offline_embedding_failure_returns_empty_results(tmp_path):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    store = LocalVectorStore(
        engine=engine,
        embedder_factory=lambda **_: (_ for _ in ()).throw(
            OSError("network unavailable")
        ),
        embedding_dim=3,
    )
    try:
        assert store.search("offline query") == []
    finally:
        engine.dispose()


def test_listener_loads_extension_once_per_connection(tmp_path, monkeypatch):
    """The checkout listener runs once per pooled connection via record info."""
    from src.aac_app.services import local_vector_store as lvs_module

    calls: list[str] = []

    def fake_load_extension(dbapi_connection, connection_record):
        loaded = connection_record is not None and connection_record.info.get(
            "aac_sqlite_vec_loaded"
        )
        calls.append("load" if not loaded else "skip")
        if not loaded and connection_record is not None:
            connection_record.info["aac_sqlite_vec_loaded"] = True
        return True

    monkeypatch.setattr(lvs_module, "SQLITE_VEC_AVAILABLE", True)
    monkeypatch.setattr(lvs_module, "_load_sqlite_vec_extension", fake_load_extension)

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    store = LocalVectorStore(
        engine=engine,
        embedder=FakeEmbedder({"a": [1.0, 0.0, 0.0]}),
        embedding_dim=3,
    )
    try:
        # Force listener installation; StaticPool reuses one connection, so
        # each checkout loads once and then skips via the record marker.
        store._get_engine()
        for _ in range(3):
            with engine.connect() as connection:
                connection.exec_driver_sql("SELECT 1")
    finally:
        engine.dispose()

    assert calls[0] == "load"
    assert all(call == "skip" for call in calls[1:])
    assert len(calls) == 3


def test_two_stores_share_engine_without_duplicate_listeners(tmp_path, monkeypatch):
    """Multiple stores sharing one engine install exactly one checkout listener."""
    from src.aac_app.services import local_vector_store as lvs_module

    loads: list[int] = []

    def fake_load_extension(dbapi_connection, connection_record):
        if connection_record is None:
            return True
        if connection_record.info.get("aac_sqlite_vec_loaded"):
            return True
        connection_record.info["aac_sqlite_vec_loaded"] = True
        loads.append(1)
        return True

    monkeypatch.setattr(lvs_module, "SQLITE_VEC_AVAILABLE", True)
    monkeypatch.setattr(lvs_module, "_load_sqlite_vec_extension", fake_load_extension)

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    first = LocalVectorStore(
        engine=engine,
        embedder=FakeEmbedder({"a": [1.0, 0.0, 0.0]}),
        embedding_dim=3,
    )
    second = LocalVectorStore(
        engine=engine,
        embedder=FakeEmbedder({"a": [1.0, 0.0, 0.0]}),
        embedding_dim=3,
    )
    try:
        first._get_engine()
        second._get_engine()
        assert getattr(engine, "_aac_sqlite_vec_listener", None) is not None
        with engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")
        with engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")
    finally:
        first.close()
        second.close()
        engine.dispose()

    # One connection, one real extension load; reuse skips reloading.
    assert loads == [1]


def test_close_is_idempotent_and_marks_store_closed(tmp_path):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    store = LocalVectorStore(
        engine=engine,
        embedder=FakeEmbedder({"a": [1.0, 0.0, 0.0]}),
        embedding_dim=3,
    )
    try:
        store.close()
        store.close()  # Second close must be a no-op.
        assert store.is_available() is False
        assert store.is_ready() is False
    finally:
        engine.dispose()


def test_symbol_query_orders_semantic_results_and_keeps_keyword_fallback(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        session.add_all(
            [
                Symbol(id=1, label="cow", description="farm animal"),
                Symbol(id=2, label="horse", description="farm animal"),
                Symbol(id=3, label="apple", description="fruit"),
            ]
        )
        session.commit()

        class SemanticStore:
            def search(self, _query, k=20):
                return [
                    {"id": 2, "type": "symbol"},
                    {"id": 1, "type": "symbol"},
                ][:k]

        monkeypatch.setattr(deps, "get_vector_store", lambda: SemanticStore())
        query, status = _apply_symbol_search(session.query(Symbol), "farm animal", session)
        assert status == "enabled"
        assert [symbol.id for symbol in query.all()] == [2, 1]

        class OfflineStore:
            def search(self, _query, k=20):
                raise OSError("network unavailable")

        monkeypatch.setattr(deps, "get_vector_store", lambda: OfflineStore())
        query, status = _apply_symbol_search(session.query(Symbol), "farm animal", session)
        assert status == "degraded"
        assert [symbol.id for symbol in query.all()] == [1, 2]

        # Short queries skip semantic embedding and stay keyword-only.
        query, status = _apply_symbol_search(session.query(Symbol), "cow", session)
        assert status == "keyword"
        assert [symbol.id for symbol in query.all()] == [1]
    finally:
        session.close()
        engine.dispose()
