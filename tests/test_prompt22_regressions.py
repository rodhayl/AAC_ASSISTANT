"""PROMPT_22 regressions: E1-E12.

(E6's websocket tests live in tests/test_collab_ws.py — this file carries the
E6 predicate/unit tests and the route-level junk-drop tests are there too.)

- E1: the unicode-recall union runs on SQL HITS too (ASCII row matching must
  not hide a fold-only sibling) — symbols search, keywords standalone, boards.
- E2: the boards recall/name filter is scoped to the RBAC-visible set (a
  visible fold-only board is never hidden behind an invisible ASCII board).
- E3: unicode_recall_ids is bounded (scan cap + id cap) and can be scoped
  with extra_filters.
- E4: the existence probe is gone — an ASCII SQL hit pays ONE filter query.
- E5: blank input (absent/empty/whitespace-only) means NO FILTER on every
  search route; UI omit and API agree.
- E7: category/language got the same strip-guard as search/keywords/name.
- E8: learning saved-topic board name has no [:100] slice (schema caps first).
- E9: _tokenize_topic folds with casefold; oversized topics never invoke the
  LLM fetcher (catalog tiers still answer).
- E10: update_board uses an explicit schema-derived allow-list + ValueError.
- E11: ai_provider capped at String(50) on create/update (422-first).
- E12: the recall scans are scoped by the caller's equality pre-filters.
"""

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from src.aac_app.models import CommunicationBoard, SavedTopic, Symbol, User
from src.aac_app.services.prediction_service import PredictionService, _tokenize_topic
from src.aac_app.services.runtime_translation import unicode_recall_ids
from src.api import schemas
from src.api.main import app
from tests.auth_helpers import create_test_headers

client = TestClient(app)

pytestmark = pytest.mark.usefixtures("setup_test_db")

_PASSWORD = "TestPassword123"


class _EmptyVectorStore:
    """Deterministic stand-in for the process-global vector store (mirrors
    the D7/E1 pattern in the PROMPT_20/21 regression files)."""

    def search(self, query, k=20):
        return []


def uuid4hex() -> str:
    return uuid.uuid4().hex[:8]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _register(client, tag, user_type="teacher", password=_PASSWORD) -> tuple[dict, str]:
    """Register + login a fresh user; returns (user dict, bearer token)."""
    username = f"{tag}_{uuid4hex()}"
    reg = client.post(
        "/api/auth/register",
        json={
            "username": username,
            "password": password,
            "display_name": f"{tag} User",
            "user_type": user_type,
        },
    )
    assert reg.status_code == 200, reg.text
    user = reg.json()
    login = client.post(
        "/api/auth/token", data={"username": username, "password": password}
    )
    assert login.status_code == 200, login.text
    return user, login.json()["access_token"]


def _seed_symbols(test_db_session, rows):
    test_db_session.add_all(
        [Symbol(**row) for row in rows]
    )
    test_db_session.commit()


def _symbol_labels(token, params):
    response = client.get(
        "/api/boards/symbols", params=params, headers=_auth(token)
    )
    assert response.status_code == 200, response.text
    return {item["label"] for item in response.json()}


# --- E1: recall union runs on SQL hits (ASCII + fold rows both found) -------


def test_e1_symbol_search_returns_ascii_and_fold_rows_on_sql_hit(
    admin_token, test_db_session, monkeypatch
):
    monkeypatch.setattr("src.api.deps.get_vector_store", lambda: _EmptyVectorStore())
    _seed_symbols(
        test_db_session,
        [
            {"label": "strasse place", "category": "noun", "language": "de", "is_builtin": True},
            {"label": "straße", "category": "noun", "language": "de", "is_builtin": True},
        ],
    )
    # SQL LIKE matches 'strasse place' (the ASCII row) yet the fold-only
    # 'straße' must ALSO be returned — recall is a union, not an
    # empty-results-only fallback. Red before E1: only the ASCII row.
    labels = _symbol_labels(admin_token, {"search": "STRASSE"})
    assert labels == {"strasse place", "straße"}
    # Lower-case ß query finds both as well (SQL LIKE matches neither here —
    # the pattern is casefolded to %strasse% and lower('straße') keeps ß).
    assert _symbol_labels(admin_token, {"search": "straße"}) == {
        "strasse place",
        "straße",
    }
    # A pure-miss recall still works (D7 direction, zero SQL hits).
    assert _symbol_labels(admin_token, {"search": "zzqq"}) == set()


def test_e1_keywords_standalone_returns_ascii_and_fold_rows_on_sql_hit(
    admin_token, test_db_session
):
    _seed_symbols(
        test_db_session,
        [
            {"label": "alpha", "keywords": "strasse road", "category": "noun", "language": "de", "is_builtin": True},
            {"label": "beta", "keywords": "straße", "category": "noun", "language": "de", "is_builtin": True},
        ],
    )
    # SQL LIKE hits 'alpha' (keywords 'strasse road') yet the keyword-only
    # fold row 'beta' must ALSO be returned. Red before E1: only 'alpha'.
    assert _symbol_labels(admin_token, {"keywords": "STRASSE"}) == {"alpha", "beta"}
    assert _symbol_labels(admin_token, {"keywords": "straße"}) == {"alpha", "beta"}


def test_e1_boards_name_returns_ascii_and_fold_rows_on_sql_hit(
    test_db_session, admin_token
):
    owner = User(
        username=f"e1owner_{uuid4hex()}",
        display_name="E1 Owner",
        user_type="teacher",
        password_hash="test-hash",
        is_active=True,
    )
    test_db_session.add(owner)
    test_db_session.flush()
    test_db_session.add_all(
        [
            CommunicationBoard(user_id=owner.id, name="strasse place"),
            CommunicationBoard(user_id=owner.id, name="straße"),
        ]
    )
    test_db_session.commit()
    resp = client.get(
        "/api/boards", params={"name": "STRASSE"}, headers=_auth(admin_token)
    )
    assert resp.status_code == 200, resp.text
    # Admin sees every board; the ASCII SQL ilike hit must not hide the
    # fold-only sibling. Red before E1: only 'strasse place'.
    assert {b["name"] for b in resp.json()} == {"strasse place", "straße"}


# --- E2: boards name recall is RBAC-scoped -----------------------------------


def test_e2_visible_fold_board_not_hidden_by_invisible_ascii_board(
    test_db_session,
):
    o1 = User(
        username=f"e2o1_{uuid4hex()}",
        display_name="E2 O1",
        user_type="teacher",
        password_hash="test-hash",
        is_active=True,
    )
    o2 = User(
        username=f"e2o2_{uuid4hex()}",
        display_name="E2 O2",
        user_type="teacher",
        password_hash="test-hash",
        is_active=True,
    )
    test_db_session.add_all([o1, o2])
    test_db_session.flush()
    # o1's private board matches the ASCII ilike for STRASSE; o2's own
    # private board is the fold-only 'straße' o2 is allowed to see.
    test_db_session.add_all(
        [
            CommunicationBoard(user_id=o1.id, name="STRASSE private", is_public=False),
            CommunicationBoard(user_id=o2.id, name="straße", is_public=False),
        ]
    )
    test_db_session.commit()
    o2_headers = create_test_headers(o2.id, o2.username, "teacher")
    o1_headers = create_test_headers(o1.id, o1.username, "teacher")

    # o2's search must return their own fold board, never o1's invisible one.
    # Red before E2: the RBAC-blind probe saw o1's ASCII hit and suppressed
    # recall, then RBAC removed the only SQL row -> [].
    resp = client.get(
        "/api/boards", params={"name": "STRASSE"}, headers=o2_headers
    )
    assert resp.status_code == 200, resp.text
    assert [b["name"] for b in resp.json()] == ["straße"]
    # o2 never sees o1's private board in the unfiltered list either.
    resp = client.get("/api/boards", headers=o2_headers)
    assert {b["name"] for b in resp.json()} == {"straße"}
    # o1 still sees their own ASCII board.
    resp = client.get(
        "/api/boards", params={"name": "STRASSE"}, headers=o1_headers
    )
    assert {b["name"] for b in resp.json()} == {"STRASSE private"}


def test_e2_admin_sees_both_rbac_scoped_boards(test_db_session, admin_user):
    o1 = User(
        username=f"e2adm_o1_{uuid4hex()}",
        display_name="E2 Adm O1",
        user_type="teacher",
        password_hash="test-hash",
        is_active=True,
    )
    o2 = User(
        username=f"e2adm_o2_{uuid4hex()}",
        display_name="E2 Adm O2",
        user_type="teacher",
        password_hash="test-hash",
        is_active=True,
    )
    test_db_session.add_all([o1, o2])
    test_db_session.flush()
    test_db_session.add_all(
        [
            CommunicationBoard(user_id=o1.id, name="STRASSE private", is_public=False),
            CommunicationBoard(user_id=o2.id, name="straße", is_public=False),
        ]
    )
    test_db_session.commit()
    admin_headers = create_test_headers(admin_user.id, admin_user.username, "admin")
    resp = client.get(
        "/api/boards", params={"name": "STRASSE"}, headers=admin_headers
    )
    assert resp.status_code == 200, resp.text
    assert {b["name"] for b in resp.json()} == {"STRASSE private", "straße"}


# --- E3: unicode_recall_ids caps + extra_filters -----------------------------


def test_unicode_recall_ids_id_cap_limits_matches(test_db_session):
    _seed_symbols(
        test_db_session,
        [
            {"label": f"straße{i}", "category": "noun", "language": "de", "is_builtin": True}
            for i in range(6)
        ],
    )
    # Six fold-only rows match 'STRASSE'; the id cap must bound the list.
    ids = unicode_recall_ids(
        test_db_session,
        Symbol,
        [Symbol.label],
        "STRASSE",
        max_scan_rows=100,
        max_ids=3,
    )
    assert len(ids) == 3


def test_unicode_recall_ids_scan_cap_stops_before_late_row(test_db_session):
    # Five non-matching rows first, then the fold-only row LAST.
    _seed_symbols(
        test_db_session,
        [
            {"label": f"alpha{i}", "category": "noun", "language": "en", "is_builtin": True}
            for i in range(5)
        ],
    )
    late = Symbol(
        label="straße", category="noun", language="de", is_builtin=True
    )
    test_db_session.add(late)
    test_db_session.commit()
    late_id = late.id
    # A scan cap of 5 visits only the first five rows: the fold row inserted
    # after them is beyond the cap and must NOT be recalled.
    ids = unicode_recall_ids(
        test_db_session,
        Symbol,
        [Symbol.label],
        "STRASSE",
        max_scan_rows=5,
        max_ids=50,
    )
    assert late_id not in ids
    # With headroom the same row IS found (recall still works to the cap).
    ids = unicode_recall_ids(
        test_db_session,
        Symbol,
        [Symbol.label],
        "STRASSE",
        max_scan_rows=100,
        max_ids=50,
    )
    assert late_id in ids


def test_unicode_recall_ids_extra_filters_scope_the_scan(test_db_session):
    noun = Symbol(
        label="straße noun", category="noun", language="de", is_builtin=True
    )
    other = Symbol(
        label="straße other", category="other", language="de", is_builtin=True
    )
    test_db_session.add_all([noun, other])
    test_db_session.commit()
    # extra_filters AND onto the scan query: only the noun row is considered,
    # so the other-category fold row is never returned (E12b).
    ids = unicode_recall_ids(
        test_db_session,
        Symbol,
        [Symbol.label],
        "STRASSE",
        extra_filters=[Symbol.category == "noun"],
    )
    assert ids == [noun.id]
    # Without the filter both rows match.
    ids = unicode_recall_ids(
        test_db_session, Symbol, [Symbol.label], "STRASSE"
    )
    assert set(ids) == {noun.id, other.id}


def test_unicode_recall_ids_d7_semantics_under_default_caps(test_db_session):
    _seed_symbols(
        test_db_session,
        [
            {"label": "straße", "category": "noun", "language": "de", "is_builtin": True},
            {"label": "casa", "category": "noun", "language": "es", "is_builtin": True},
        ],
    )
    # Default caps must never truncate the tiny catalogs the D7/E1 tests use.
    ids = unicode_recall_ids(
        test_db_session, Symbol, [Symbol.label], "STRASSE"
    )
    labels = {
        test_db_session.query(Symbol.label).filter(Symbol.id == row_id).scalar()
        for row_id in ids
    }
    assert "straße" in labels
    assert "casa" not in labels


# --- E4: single filter fetch on the ASCII hit path ---------------------------


def test_e4_symbol_search_sql_hit_pays_one_like_query(
    admin_token, test_db_session, monkeypatch, test_db_engine
):
    monkeypatch.setattr("src.api.deps.get_vector_store", lambda: _EmptyVectorStore())
    _seed_symbols(
        test_db_session,
        [{"label": "casa", "category": "noun", "language": "es", "is_builtin": True}],
    )
    statements: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(str(statement))

    event.listen(test_db_engine, "after_cursor_execute", record)
    try:
        labels = _symbol_labels(admin_token, {"search": "casa"})
    finally:
        event.remove(test_db_engine, "after_cursor_execute", record)
    assert labels == {"casa"}
    like_statements = [s for s in statements if "LIKE" in s.upper()]
    # Red before E4: the empty-result probe (a LIKE existence SELECT) plus the
    # fetch = 2 LIKE-carrying statements. Green: the probe is gone, only the
    # single fetch carries the LIKE filter (the recall scan has no LIKE).
    assert len(like_statements) == 1


# --- E5 + E7: blank input is NO FILTER on every search route -----------------


def test_e5_symbol_search_blank_variants_match_no_filter(
    admin_token, test_db_session, monkeypatch
):
    monkeypatch.setattr("src.api.deps.get_vector_store", lambda: _EmptyVectorStore())
    _seed_symbols(
        test_db_session,
        [
            {"label": "casa", "category": "noun", "language": "es", "is_builtin": True},
            {"label": "perro", "category": "noun", "language": "es", "is_builtin": True},
        ],
    )
    baseline = _symbol_labels(admin_token, {"limit": 1000})
    for blank in ("", "   "):
        assert _symbol_labels(admin_token, {"search": blank, "limit": 1000}) == baseline
    # Blank search + another filter equals that filter alone (never the full
    # library, never []): the strip happens before the guard, so blank never
    # becomes a silent match-all either.
    category_only = _symbol_labels(admin_token, {"category": "noun", "limit": 1000})
    assert category_only == baseline
    for blank in ("", "   "):
        got = _symbol_labels(
            admin_token, {"search": blank, "category": "noun", "limit": 1000}
        )
        assert got == baseline


def test_e5_keywords_blank_variants_match_no_filter(admin_token, test_db_session):
    _seed_symbols(
        test_db_session,
        [
            {"label": "alpha", "keywords": "dog", "category": "noun", "language": "es", "is_builtin": True},
            {"label": "beta", "keywords": "cat", "category": "noun", "language": "es", "is_builtin": True},
        ],
    )
    baseline = _symbol_labels(admin_token, {"limit": 1000})
    for blank in ("", "   "):
        assert _symbol_labels(admin_token, {"keywords": blank, "limit": 1000}) == baseline


def test_e7_category_and_language_strip_guards(test_db_session, admin_token):
    _seed_symbols(
        test_db_session,
        [
            {"label": "casa", "category": "general", "language": "es", "is_builtin": True},
            {"label": "coche", "category": "transport", "language": "es", "is_builtin": True},
        ],
    )
    # Padded category matches the stored rows (mirrors padded search).
    assert _symbol_labels(admin_token, {"category": "  general  "}) == {"casa"}
    # Blank category behaves like an absent one (E5 no-filter), never a
    # literal ''-equality match.
    baseline = _symbol_labels(admin_token, {"limit": 1000})
    assert _symbol_labels(admin_token, {"category": "   ", "limit": 1000}) == baseline
    # Padded language still filters (normalize handles the strip).
    assert _symbol_labels(admin_token, {"language": "  es  "}) == {"casa", "coche"}
    # Whitespace-only language == absent language (no-filter contract), not a
    # silent match-all for one param and [] for another.
    assert _symbol_labels(admin_token, {"language": "   ", "limit": 1000}) == baseline
    # Genuinely unknown (non-code) value semantics unchanged: normalize
    # returns None and the filter is skipped (no filter, not a 500).
    assert _symbol_labels(admin_token, {"language": "123", "limit": 1000}) == baseline
    # A real-but-empty code still filters to [] (its rows simply do not
    # exist), untouched by the strip-guard.
    assert _symbol_labels(admin_token, {"language": "zz", "limit": 1000}) == set()


# --- E8: saved-topic board name slice removal --------------------------------


def test_e8_saved_topic_board_boundary_is_enforced_by_schema(
    test_db_session, admin_user
):
    headers = create_test_headers(admin_user.id, admin_user.username, "admin")
    # 101-char board -> schema 422 (SavedTopicCreate.board max_length=100);
    # the handler's old [:100] slice was unreachable.
    r = client.post(
        "/api/learning/topics/saved",
        json={"topic": "valid topic", "board": "b" * 101},
        headers=headers,
    )
    assert r.status_code == 422, r.text
    # A full 100-char board passes and is stored un-truncated.
    board_100 = "b" * 100
    r = client.post(
        "/api/learning/topics/saved",
        json={"topic": "valid topic", "board": board_100},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    row = (
        test_db_session.query(SavedTopic)
        .filter(SavedTopic.created_by_user_id == admin_user.id)
        .first()
    )
    assert row is not None and row.board == board_100


# --- E9: prediction topic fold parity + no fetcher for oversized topics ------

def test_e9_tokenize_topic_casefold_parity():
    # Red before E9: .lower() produced ['strasse'] vs ['straße'].
    assert _tokenize_topic("STRASSE") == _tokenize_topic("straße")


def test_e9_oversized_topic_never_invokes_fetcher_but_catalog_still_answers(
    test_db_session, regular_user
):
    service = PredictionService()
    _seed_symbols(
        test_db_session,
        [{"label": "frutas", "category": "noun", "language": "es", "is_builtin": True}],
    )
    calls: list[str] = []

    def counting_fetcher(language, topic):
        calls.append(topic)
        return ["manzana", "pera"]

    giant_topic = "frutas " + "x" * 600
    suggestions = service.predict_next(
        user_id=regular_user.id,
        current_symbols=[],
        limit=5,
        language="es",
        db=test_db_session,
        topic=giant_topic,
        topic_word_fetcher=counting_fetcher,
    )
    # Red before E9: the fetcher was invoked with the giant topic (then the
    # result was discarded at the no-store guard).
    assert calls == []
    # The catalog topic tier still answers for the oversized topic.
    assert any(s["label"] == "frutas" for s in suggestions)


# --- E10: update_board explicit allow-list -----------------------------------


def test_e10_board_update_allow_list_covers_schema_and_columns():
    from src.api.routers.boards import _BOARD_UPDATE_SETTABLE_KEYS

    assert frozenset(schemas.BoardUpdate.model_fields) == _BOARD_UPDATE_SETTABLE_KEYS
    columns = set(CommunicationBoard.__table__.c.keys())
    for key in _BOARD_UPDATE_SETTABLE_KEYS:
        assert key in columns, f"BoardUpdate field {key!r} has no board column"


def test_e10_update_board_unknown_key_raises_value_error(
    test_db_session, admin_user
):
    from src.api.routers.boards import update_board

    owner = User(
        username=f"e10owner_{uuid4hex()}",
        display_name="E10 Owner",
        user_type="teacher",
        password_hash="test-hash",
        is_active=True,
    )
    test_db_session.add(owner)
    test_db_session.flush()
    board = CommunicationBoard(user_id=owner.id, name="E10 Board")
    test_db_session.add(board)
    test_db_session.commit()

    fake_update = MagicMock()
    fake_update.model_dump.return_value = {"bogus_field": 1}
    # Red before E10: the raw setattr loop silently set a dead attribute.
    with pytest.raises(ValueError, match="bogus_field"):
        update_board(
            board.id,
            fake_update,
            current_user=admin_user,
            db=test_db_session,
        )


# --- E11: ai_provider capped at String(50) on create/update ------------------


def test_e11_board_ai_provider_overlong_rejected_422():
    user, token = _register(client, "e11owner")
    big_provider = "p" * 5000
    # Red before E11: the schema accepted the 5KB provider and the route's
    # allow-list answered 400 — the schema cap must fire first (422).
    r = client.post(
        "/api/boards",
        params={"user_id": user["id"]},
        json={
            "name": "E11 Board",
            "grid_rows": 3,
            "grid_cols": 4,
            "ai_enabled": True,
            "ai_provider": big_provider,
            "ai_model": "llama3",
        },
        headers=_auth(token),
    )
    assert r.status_code == 422, r.text

    created = client.post(
        "/api/boards",
        params={"user_id": user["id"]},
        json={"name": "E11 Board 2", "grid_rows": 3, "grid_cols": 4},
        headers=_auth(token),
    )
    assert created.status_code == 200, created.text
    board_id = created.json()["id"]
    r = client.put(
        f"/api/boards/{board_id}",
        json={"ai_enabled": True, "ai_provider": big_provider, "ai_model": "llama3"},
        headers=_auth(token),
    )
    assert r.status_code == 422, r.text


# --- E12b: recall scans reuse the caller's equality pre-filters --------------

def test_e12_recall_scan_receives_category_and_language_scope(
    admin_token, test_db_session, monkeypatch
):
    monkeypatch.setattr("src.api.deps.get_vector_store", lambda: _EmptyVectorStore())
    _seed_symbols(
        test_db_session,
        [
            {"label": "strasse a", "category": "verb", "language": "de", "is_builtin": True},
            {"label": "casa", "category": "noun", "language": "es", "is_builtin": True},
        ],
    )
    from src.api.routers import symbols as symbols_module

    captured: list[dict] = []
    original = symbols_module.unicode_recall_ids

    def spy(*args, **kwargs):
        captured.append(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(symbols_module, "unicode_recall_ids", spy)

    # search + category: the recall scan must be scoped to the category slice.
    _symbol_labels(admin_token, {"search": "STRASSE", "category": "verb"})
    assert len(captured) == 1
    filters = captured[0].get("extra_filters")
    assert filters and len(filters) == 1
    assert filters[0].compare(Symbol.category == "verb")

    # keywords + language: same scoping mechanism for the standalone filter.
    captured.clear()
    _symbol_labels(admin_token, {"keywords": "STRASSE", "language": "de"})
    assert len(captured) == 1
    filters = captured[0].get("extra_filters")
    assert filters and len(filters) == 1
    assert filters[0].compare(Symbol.language == "de")

    # No equality filters -> the scan runs unscoped (extra_filters empty).
    captured.clear()
    _symbol_labels(admin_token, {"search": "STRASSE"})
    assert captured[0].get("extra_filters") == []
