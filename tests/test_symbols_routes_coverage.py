"""Real-case API coverage for the symbols router (src/api/routers/symbols.py).

Covers the list filters/sorts (including the core-category usage-frequency
ordering), the semantic-search branch, symbol update/image replacement,
batch-update edge cases, and the 404 paths.
"""
import base64
import io

import pytest
from fastapi.testclient import TestClient

from src.aac_app.models import BoardSymbol, CommunicationBoard, Symbol, SymbolUsageLog
from src.api.main import app
from tests.auth_helpers import create_test_headers

client = TestClient(app)
# The install-style 500 paths re-raise raw exceptions; use a client that
# surfaces them as responses instead of re-raising in the test process.
client_no_raise = TestClient(app, raise_server_exceptions=False)

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


@pytest.fixture
def staff_headers(admin_user):
    return create_test_headers(admin_user.id, admin_user.username, "admin")


@pytest.fixture
def symbols_setup(test_db_session, admin_user):
    """Three symbols across categories/languages for filter and sort cases."""
    syms = [
        Symbol(label="Zebra", keywords="animal,stripes", category="animals", language="en"),
        Symbol(label="Apple", keywords="fruit,red", category="food", language="en"),
        Symbol(label="Agua", keywords="drink,water", category="core", language="es"),
    ]
    test_db_session.add_all(syms)
    test_db_session.commit()
    for sym in syms:
        test_db_session.refresh(sym)
    return syms


@pytest.mark.usefixtures("setup_test_db")
def test_symbol_list_filters_and_sorts(symbols_setup, staff_headers):
    # Category filter
    res = client.get("/api/boards/symbols?category=food", headers=staff_headers)
    assert [s["label"] for s in res.json()] == ["Apple"]

    # Language filter
    res = client.get("/api/boards/symbols?language=es", headers=staff_headers)
    assert [s["label"] for s in res.json()] == ["Agua"]

    # Keyword filter
    res = client.get("/api/boards/symbols?keywords=animal", headers=staff_headers)
    assert [s["label"] for s in res.json()] == ["Zebra"]

    # Sorts
    res = client.get("/api/boards/symbols?sort=newest", headers=staff_headers)
    assert res.json()[0]["id"] == max(s.id for s in symbols_setup)

    res = client.get("/api/boards/symbols?sort=oldest", headers=staff_headers)
    assert res.json()[0]["id"] == min(s.id for s in symbols_setup)

    res = client.get("/api/boards/symbols?sort=alpha", headers=staff_headers)
    labels = [s["label"] for s in res.json() if s["label"] in {"Zebra", "Apple", "Agua"}]
    assert labels == sorted(labels)


@pytest.mark.usefixtures("setup_test_db")
def test_symbol_core_category_sort_by_usage_frequency(
    symbols_setup, test_db_session, admin_user, staff_headers
):
    """The core category sorts by the current user's usage frequency."""
    zebra, apple, agua = symbols_setup
    # Zebra used twice, apple once, agua never.
    test_db_session.add_all(
        [
            SymbolUsageLog(
                symbol_id=zebra.id,
                symbol_label=zebra.label,
                symbol_category=zebra.category,
                user_id=admin_user.id,
                position_in_utterance=0,
                utterance_length=1,
            ),
            SymbolUsageLog(
                symbol_id=zebra.id,
                symbol_label=zebra.label,
                symbol_category=zebra.category,
                user_id=admin_user.id,
                position_in_utterance=0,
                utterance_length=1,
            ),
            SymbolUsageLog(
                symbol_id=apple.id,
                symbol_label=apple.label,
                symbol_category=apple.category,
                user_id=admin_user.id,
                position_in_utterance=0,
                utterance_length=1,
            ),
        ]
    )
    test_db_session.commit()

    res = client.get(
        "/api/boards/symbols?category=core&sort=default", headers=staff_headers
    )
    assert res.status_code == 200
    # Only the core-category symbol is returned (freq ordering has one row).
    assert [s["label"] for s in res.json()] == ["Agua"]


@pytest.mark.usefixtures("setup_test_db")
def test_symbol_list_search_uses_semantic_results(
    symbols_setup, staff_headers, monkeypatch
):
    """Searches longer than 3 chars use the vector store for ordering."""
    class FakeVectorStore:
        def search(self, query, k=20):
            return [
                {"type": "symbol", "id": symbols_setup[2].id, "score": 0.9},
                {"type": "symbol", "id": symbols_setup[0].id, "score": 0.8},
            ]

    monkeypatch.setattr("src.api.deps.get_vector_store", lambda: FakeVectorStore())
    res = client.get(
        "/api/boards/symbols?search=drink%20water%20please", headers=staff_headers
    )
    assert res.status_code == 200
    labels = [s["label"] for s in res.json() if s["label"] in {"Zebra", "Agua"}]
    # Semantic ordering puts Agua first.
    assert labels == ["Agua", "Zebra"]


@pytest.mark.usefixtures("setup_test_db")
def test_update_symbol_sets_usage_flag(
    symbols_setup, test_db_session, admin_user, staff_headers
):
    """Updating a symbol that is used on a board reports is_in_use."""
    symbol = symbols_setup[0]
    board = CommunicationBoard(user_id=admin_user.id, name="Usage Board")
    test_db_session.add(board)
    test_db_session.flush()
    test_db_session.add(
        BoardSymbol(board_id=board.id, symbol_id=symbol.id, position_x=0, position_y=0)
    )
    test_db_session.commit()

    res = client.put(
        f"/api/boards/symbols/{symbol.id}",
        json={"label": "Zebra actualizado"},
        headers=staff_headers,
    )
    assert res.status_code == 200
    assert res.json()["label"] == "Zebra actualizado"
    assert res.json()["is_in_use"] is True


@pytest.mark.usefixtures("setup_test_db")
def test_update_symbol_image_replaces_old_upload(
    symbols_setup, staff_headers
):
    """Uploading a new image replaces the old image_path and deletes the old file."""
    symbol = symbols_setup[1]
    old_path = symbol.image_path
    assert old_path is None  # no old upload for a fresh symbol

    res = client.post(
        f"/api/boards/symbols/{symbol.id}/image",
        headers=staff_headers,
        files={"file": ("new.png", io.BytesIO(PNG_BYTES), "image/png")},
    )
    assert res.status_code == 200
    new_path = res.json()["image_path"]
    assert new_path and new_path.startswith("/uploads/symbols/")

    # Second upload replaces the first and removes the previous file.
    res2 = client.post(
        f"/api/boards/symbols/{symbol.id}/image",
        headers=staff_headers,
        files={"file": ("new2.png", io.BytesIO(PNG_BYTES), "image/png")},
    )
    assert res2.status_code == 200
    assert res2.json()["image_path"] != new_path
    import os

    assert not os.path.exists(new_path.lstrip("/"))

    # Clean up the final upload through the delete route.
    deleted = client.delete(f"/api/boards/symbols/{symbol.id}", headers=staff_headers)
    assert deleted.status_code == 200
    assert not os.path.exists(res2.json()["image_path"].lstrip("/"))


@pytest.mark.usefixtures("setup_test_db")
def test_symbol_management_404_paths(
    symbols_setup, test_db_session, admin_user, staff_headers
):
    """Missing symbols and missing board symbols return translated 404s."""
    # Update/delete a nonexistent global symbol.
    assert (
        client.put(
            "/api/boards/symbols/999999", json={"label": "Ghost"}, headers=staff_headers
        ).status_code
        == 404
    )
    assert (
        client.delete("/api/boards/symbols/999999", headers=staff_headers).status_code
        == 404
    )

    # Update/delete a nonexistent board symbol on a real board.
    board = CommunicationBoard(user_id=admin_user.id, name="404 Board")
    test_db_session.add(board)
    test_db_session.commit()
    test_db_session.refresh(board)

    assert (
        client.put(
            f"/api/boards/{board.id}/symbols/999999",
            json={"position_x": 1},
            headers=staff_headers,
        ).status_code
        == 404
    )
    assert (
        client.delete(
            f"/api/boards/{board.id}/symbols/999999", headers=staff_headers
        ).status_code
        == 404
    )


@pytest.mark.usefixtures("setup_test_db")
def test_batch_update_skips_entries_without_id(
    symbols_setup, test_db_session, admin_user, staff_headers
):
    """Batch updates ignore entries missing an id and count the applied ones."""
    symbol = symbols_setup[0]
    board = CommunicationBoard(user_id=admin_user.id, name="Batch Board")
    test_db_session.add(board)
    test_db_session.flush()
    test_db_session.add(
        BoardSymbol(board_id=board.id, symbol_id=symbol.id, position_x=0, position_y=0)
    )
    test_db_session.commit()
    board_symbol = (
        test_db_session.query(BoardSymbol).filter_by(board_id=board.id).first()
    )

    res = client.put(
        f"/api/boards/{board.id}/symbols/batch",
        json=[
            {"id": board_symbol.id, "position_x": 2, "position_y": 1, "size": 2},
            {"position_x": 9},  # no id -> skipped
        ],
        headers=staff_headers,
    )
    assert res.status_code == 200
    assert res.json()["updated"] == 1

    test_db_session.refresh(board_symbol)
    assert board_symbol.position_x == 2
    assert board_symbol.position_y == 1
    assert board_symbol.size == 2


@pytest.mark.usefixtures("setup_test_db")
def test_symbol_reorder_batch(symbols_setup, staff_headers):
    """Reorder assigns order_index values in one batch request."""
    ids = [s.id for s in symbols_setup]
    res = client.put(
        "/api/boards/symbols/reorder",
        json=[{"id": ids[0], "order_index": 5}, {"id": ids[1], "order_index": 1}],
        headers=staff_headers,
    )
    assert res.status_code == 200
    assert res.json() == {"ok": True, "updated": 2}

    res = client.put(
        "/api/boards/symbols/reorder", json=[], headers=staff_headers
    )
    assert res.status_code == 200
    assert res.json() == {"ok": True, "updated": 0}


class FaultySession:
    """Session wrapper that raises on the configured method names."""

    def __init__(self, session, **faults):
        self._session = session
        self._faults = faults

    def __getattr__(self, name):
        if name in self._faults:
            exc = self._faults[name]

            def raiser(*args, **kwargs):
                raise exc

            return raiser
        return getattr(self._session, name)

    def close(self):
        self._session.close()


def _faulty_session(test_db_engine, **faults):
    from sqlalchemy.orm import sessionmaker

    session = sessionmaker(
        autocommit=False, autoflush=False, bind=test_db_engine
    )()
    return FaultySession(session, **faults)


def _override_db(session):
    from src.api.deps import get_db

    def override():
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override


@pytest.mark.usefixtures("setup_test_db")
def test_symbol_reorder_failure_rolls_back_and_returns_500(
    symbols_setup, staff_headers, test_db_engine, monkeypatch
):
    """A commit failure during reorder rolls back and maps to 500."""
    symbol = symbols_setup[0]
    faulty = _faulty_session(test_db_engine, commit=RuntimeError("disk full"))

    class ReorderSession(FaultySession):
        def __init__(self):
            super().__init__(faulty._session, commit=RuntimeError("disk full"))

        def query(self, model):
            if model is Symbol:
                return _FakeQuery([symbol])
            return self._session.query(model)

    class _FakeQuery:
        def __init__(self, rows):
            self._rows = rows

        def filter(self, *args):
            return self

        def all(self):
            return self._rows

    _override_db(ReorderSession())
    try:
        res = client.put(
            "/api/boards/symbols/reorder",
            json=[{"id": symbol.id, "order_index": 5}],
            headers=staff_headers,
        )
    finally:
        app.dependency_overrides.clear()
    assert res.status_code == 500


@pytest.mark.usefixtures("setup_test_db")
def test_symbol_upload_commit_failure_cleans_up_upload(
    staff_headers, test_db_engine, monkeypatch
):
    """A commit failure after image persistence removes the orphaned file."""
    removed = []
    monkeypatch.setattr(
        "src.api.routers.symbols.remove_owned_upload",
        lambda path, uploads_dir: removed.append(path),
    )

    _override_db(_faulty_session(test_db_engine, commit=RuntimeError("commit failed")))
    try:
        res = client_no_raise.post(
            "/api/boards/symbols/upload",
            headers=staff_headers,
            data={"label": "Rotura"},
            files={"file": ("break.png", io.BytesIO(PNG_BYTES), "image/png")},
        )
    finally:
        app.dependency_overrides.clear()
    assert res.status_code == 500
    assert len(removed) == 1
    assert removed[0].startswith("/uploads/symbols/")


@pytest.mark.usefixtures("setup_test_db")
def test_symbol_upload_survives_refresh_and_index_errors(
    staff_headers, test_db_engine, monkeypatch
):
    """Refresh/index warnings after persistence do not fail the upload."""
    monkeypatch.setattr(
        "src.api.routers.symbols.index_symbol",
        lambda symbol: (_ for _ in ()).throw(RuntimeError("index down")),
    )
    _override_db(_faulty_session(test_db_engine, refresh=RuntimeError("refresh lost")))
    try:
        res = client.post(
            "/api/boards/symbols/upload",
            headers=staff_headers,
            data={"label": "Resiliente"},
            files={"file": ("ok.png", io.BytesIO(PNG_BYTES), "image/png")},
        )
    finally:
        app.dependency_overrides.clear()
    assert res.status_code == 200
    assert res.json()["label"] == "Resiliente"


@pytest.mark.usefixtures("setup_test_db")
def test_symbol_image_write_oserror_cleans_up_and_rejects(
    staff_headers, monkeypatch
):
    """An OSError while writing the image file removes the partial upload."""
    import pathlib

    removed = []
    monkeypatch.setattr(
        "src.api.routers.symbols.remove_owned_upload",
        lambda path, uploads_dir: removed.append(path),
    )

    class ExplodingFile:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def write(self, content):
            raise OSError("disk full")

    monkeypatch.setattr(
        pathlib.Path, "open", lambda self, mode, **kwargs: ExplodingFile()
    )
    res = client_no_raise.post(
        "/api/boards/symbols/upload",
        headers=staff_headers,
        data={"label": "Fallo"},
        files={"file": ("fail.png", io.BytesIO(PNG_BYTES), "image/png")},
    )
    assert res.status_code == 500
    assert len(removed) == 1


@pytest.mark.usefixtures("setup_test_db")
def test_symbol_image_update_commit_failure_cleans_up(
    symbols_setup, staff_headers, test_db_engine, monkeypatch
):
    """A commit failure while replacing an image removes the new upload."""
    removed = []
    monkeypatch.setattr(
        "src.api.routers.symbols.remove_owned_upload",
        lambda path, uploads_dir: removed.append(path),
    )

    _override_db(_faulty_session(test_db_engine, commit=RuntimeError("commit failed")))
    try:
        symbol = symbols_setup[0]
        res = client_no_raise.post(
            f"/api/boards/symbols/{symbol.id}/image",
            headers=staff_headers,
            files={"file": ("new.png", io.BytesIO(PNG_BYTES), "image/png")},
        )
    finally:
        app.dependency_overrides.clear()
    assert res.status_code == 500
    assert len(removed) == 1


@pytest.mark.usefixtures("setup_test_db")
def test_symbol_image_update_survives_refresh_error(
    symbols_setup, staff_headers, test_db_engine, monkeypatch
):
    """A refresh warning after an image update still returns the symbol."""
    _override_db(_faulty_session(test_db_engine, refresh=RuntimeError("refresh lost")))
    try:
        symbol = symbols_setup[0]
        res = client.post(
            f"/api/boards/symbols/{symbol.id}/image",
            headers=staff_headers,
            files={"file": ("ok.png", io.BytesIO(PNG_BYTES), "image/png")},
        )
    finally:
        app.dependency_overrides.clear()
    assert res.status_code == 200
    assert res.json()["image_path"].startswith("/uploads/symbols/")


@pytest.mark.usefixtures("setup_test_db")
def test_add_symbol_progress_failure_is_best_effort(
    symbols_setup, test_db_session, admin_user, staff_headers, monkeypatch
):
    """Vocabulary-progress failures do not fail the board-symbol creation."""
    symbol = symbols_setup[0]
    board = CommunicationBoard(user_id=admin_user.id, name="Progress Board")
    test_db_session.add(board)
    test_db_session.commit()
    test_db_session.refresh(board)

    monkeypatch.setattr(
        "src.aac_app.services.achievement_system.AchievementSystem.update_progress",
        lambda self, user_id, metric, value, db: (_ for _ in ()).throw(
            RuntimeError("progress down")
        ),
    )
    res = client.post(
        f"/api/boards/{board.id}/symbols",
        headers=staff_headers,
        json={"symbol_id": symbol.id, "position_x": 0, "position_y": 0},
    )
    assert res.status_code == 200
    assert res.json()["symbol_id"] == symbol.id


@pytest.mark.usefixtures("setup_test_db")
def test_board_symbol_partial_update_visibility_text_and_link(
    symbols_setup, test_db_session, admin_user, staff_headers
):
    """Board-symbol updates apply visibility, custom text and linked boards."""
    symbol = symbols_setup[0]
    target = CommunicationBoard(user_id=admin_user.id, name="Target Board")
    test_db_session.add(target)
    test_db_session.flush()
    board = CommunicationBoard(user_id=admin_user.id, name="Source Board")
    test_db_session.add(board)
    test_db_session.flush()
    test_db_session.add(
        BoardSymbol(board_id=board.id, symbol_id=symbol.id, position_x=0, position_y=0)
    )
    test_db_session.commit()
    board_symbol = (
        test_db_session.query(BoardSymbol).filter_by(board_id=board.id).first()
    )

    res = client.put(
        f"/api/boards/{board.id}/symbols/{board_symbol.id}",
        headers=staff_headers,
        json={
            "is_visible": False,
            "custom_text": "Mi símbolo",
            "linked_board_id": target.id,
        },
    )
    assert res.status_code == 200
    assert res.json()["is_visible"] is False
    assert res.json()["custom_text"] == "Mi símbolo"
    assert res.json()["linked_board_id"] == target.id


@pytest.mark.usefixtures("setup_test_db")
def test_board_symbol_batch_update_visibility_text_and_link(
    symbols_setup, test_db_session, admin_user, staff_headers
):
    """The batch endpoint applies visibility, custom text and linked boards."""
    symbol = symbols_setup[0]
    target = CommunicationBoard(user_id=admin_user.id, name="Batch Target")
    test_db_session.add(target)
    test_db_session.flush()
    board = CommunicationBoard(user_id=admin_user.id, name="Batch Source")
    test_db_session.add(board)
    test_db_session.flush()
    test_db_session.add(
        BoardSymbol(board_id=board.id, symbol_id=symbol.id, position_x=0, position_y=0)
    )
    test_db_session.commit()
    board_symbol = (
        test_db_session.query(BoardSymbol).filter_by(board_id=board.id).first()
    )

    res = client.put(
        f"/api/boards/{board.id}/symbols/batch",
        headers=staff_headers,
        json=[
            {
                "id": board_symbol.id,
                "is_visible": False,
                "custom_text": "Etiqueta",
                "linked_board_id": target.id,
            },
        ],
    )
    assert res.status_code == 200
    assert res.json()["updated"] == 1

    test_db_session.refresh(board_symbol)
    assert board_symbol.is_visible is False
    assert board_symbol.custom_text == "Etiqueta"
    assert board_symbol.linked_board_id == target.id
