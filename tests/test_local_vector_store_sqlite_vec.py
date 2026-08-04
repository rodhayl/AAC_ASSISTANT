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
    return LocalVectorStore(
        engine=engine,
        embedder=FakeEmbedder(vectors),
        embedding_dim=3,
        legacy_index_path=tmp_path / "vector_store.index",
        legacy_metadata_path=tmp_path / "vector_store_metadata.json",
    )


def test_sqlite_vec_add_search_update_and_delete(tmp_path):
    vectors = {
        "cow farm animal": [1.0, 0.0, 0.0],
        "horse farm animal": [0.9, 0.1, 0.0],
        "apple food": [0.0, 1.0, 0.0],
        "farm animal": [1.0, 0.0, 0.0],
    }
    store = make_store(tmp_path, vectors)

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


def test_migration_removes_legacy_files_and_persists_completion(tmp_path):
    legacy_index = tmp_path / "vector_store.index"
    legacy_metadata = tmp_path / "vector_store_metadata.json"
    legacy_index.write_bytes(b"old")
    legacy_metadata.write_text("[]", encoding="utf-8")

    store = make_store(tmp_path, {"one": [1.0, 0.0, 0.0]})
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


def test_startup_repairs_missing_vector_even_when_table_counts_match(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
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

    # Keep the vector count equal to metadata/symbol counts, but replace the
    # affected row with an unrelated id. This mirrors a partial CRUD upsert.
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
    session.close()


def test_healthy_store_skips_model_load_and_reindex(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
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
    session.close()


def test_offline_embedding_failure_returns_empty_results(tmp_path):
    store = LocalVectorStore(
        engine=create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        ),
        embedder_factory=lambda **_: (_ for _ in ()).throw(
            OSError("network unavailable")
        ),
        embedding_dim=3,
    )

    assert store.search("offline query") == []


def test_symbol_query_orders_semantic_results_and_keeps_keyword_fallback(
    monkeypatch,
):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
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
    results = _apply_symbol_search(session.query(Symbol), "farm animal", session).all()
    assert [symbol.id for symbol in results] == [2, 1]

    class OfflineStore:
        def search(self, _query, k=20):
            raise OSError("network unavailable")

    monkeypatch.setattr(deps, "get_vector_store", lambda: OfflineStore())
    results = _apply_symbol_search(session.query(Symbol), "farm animal", session).all()
    assert [symbol.id for symbol in results] == [1, 2]
    session.close()
