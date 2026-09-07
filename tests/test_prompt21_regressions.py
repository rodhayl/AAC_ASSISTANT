"""PROMPT_21 regressions: W1/A1/S1/U1/U2/L1/T1/B1/C1/R1/G1/M1.

(C1's websocket vocabulary tests live in tests/test_collab_ws.py — the D9
``add``-broadcast tests were rewritten there to the move-only contract.)

NOTE: PROMPT_22 (E1/E4/E5/E9) superseded three PROMPT_21 contracts, and the
tests below were updated in place to the new ones:
- W1 (blank input): PROMPT_21 pinned whitespace-only search/keywords/name as
  a ``[]`` no-match; E5 unified the blank-input contract to NO FILTER (an
  absent/empty/whitespace-only param behaves identically, full list) — the
  whitespace tests now assert that unified contract.
- U1 (recall gating): PROMPT_21 gated the recall scan on empty SQL results;
  E1 showed SQL matching an ASCII row must still recall fold-only siblings,
  so the scan now runs (bounded) on every search — the skip-on-hit test was
  rewritten to assert the recall UNION on a SQL hit.
- T1 (topic-word cache): oversized topics are now refused BEFORE the LLM
  fetcher (E9) instead of being fetched and only refused at the store step.

Remaining PROMPT_21 pins:
- A1: analytics usage-log telemetry fields are capped at their column widths.
- S1: multipart symbol label/category forms are capped at their columns.
- U2: the keywords standalone filter and the boards name search use the same
  shared recall helper as the symbol label search.
- L1: record_failed_attempt trims the lockout table exactly once, after the
  mutation.
- B1: board ai_model is bounded at the String(100) column on create+update.
- R1: reset-password 404 for inactive accounts happens AFTER the permission
  block, so teachers probing inactive-unassigned students get the roster 403
  (no "id exists but inactive" oracle).
- G1: guardian gender is bounded at the String(30) column on create+update.
- M1: update_user_settings rejects unknown keys with ValueError; shared
  column bounds live as constants in schemas.py.
"""

import io
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from src.aac_app.models import (
    CommunicationBoard,
    StudentTeacher,
    Symbol,
    SymbolUsageLog,
    User,
)
from src.aac_app.services.lockout_service import AccountLockoutService
from src.aac_app.services.runtime_translation import contains_like_pattern
from src.api import schemas
from src.api.main import app
from src.api.routers.auth_helpers import update_user_settings
from tests.auth_helpers import create_test_headers

client = TestClient(app)

pytestmark = pytest.mark.usefixtures("setup_test_db")

_PASSWORD = "TestPassword123"


class _EmptyVectorStore:
    """Deterministic stand-in for the process-global vector store (mirrors
    the D7 pattern in test_prompt20_regressions.py)."""

    def search(self, query, k=20):
        return []


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", (8, 8), (30, 120, 220, 255)).save(buf, format="PNG")
    return buf.getvalue()


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


def uuid4hex() -> str:
    import uuid

    return uuid.uuid4().hex[:8]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _symbol_search(token, params):
    return client.get(
        "/api/boards/symbols", params=params, headers=_auth(token)
    )


# --- W1: whitespace-only queries are no-match, never match-all ---------------


def test_contains_like_pattern_whitespace_maps_to_match_all_pinned():
    # Unit pin of the helper's contract: after the internal strip the empty
    # string maps to "%%". Search ROUTES apply the E5 blank-input contract
    # (an absent/empty/whitespace-only query means NO FILTER — they strip and
    # skip the search entirely), so whitespace never reaches this helper as a
    # match-all from a route; direct callers that do not apply that gate get
    # the documented degenerate pattern.
    assert contains_like_pattern("   ") == "%%"
    assert contains_like_pattern("") == "%%"
    assert contains_like_pattern("  casa  ") == "%casa%"


def test_symbol_search_blank_means_no_filter_unified_contract(
    admin_token, test_db_session
):
    test_db_session.add(
        Symbol(label="casa", category="noun", language="es", is_builtin=True)
    )
    test_db_session.commit()
    # E5 no-filter contract: absent, empty and whitespace-only search behave
    # IDENTICALLY — the full list, never [] and never a match-all.
    resp = _symbol_search(admin_token, {"limit": 1000})
    assert resp.status_code == 200
    full = {item["label"] for item in resp.json()}
    assert "casa" in full
    for blank in ("", "   "):
        resp = _symbol_search(admin_token, {"search": blank, "limit": 1000})
        assert resp.status_code == 200
        assert {item["label"] for item in resp.json()} == full
    # Padded real term still matches (D11 kept).
    resp = _symbol_search(admin_token, {"search": "  casa  "})
    assert {item["label"] for item in resp.json()} == {"casa"}


def test_symbol_keywords_blank_means_no_filter_unified_contract(
    admin_token, test_db_session
):
    test_db_session.add(
        Symbol(label="perro", keywords="dog,mascota", language="es", is_builtin=True)
    )
    test_db_session.commit()
    resp = _symbol_search(admin_token, {"limit": 1000})
    assert resp.status_code == 200
    full = {item["label"] for item in resp.json()}
    for blank in ("", "   "):
        resp = _symbol_search(admin_token, {"keywords": blank, "limit": 1000})
        assert resp.status_code == 200
        assert {item["label"] for item in resp.json()} == full


def test_boards_name_blank_means_no_filter_unified_contract(
    test_db_session, admin_token
):
    owner = User(
        username=f"w1owner_{uuid4hex()}",
        display_name="W1 Owner",
        user_type="teacher",
        password_hash="test-hash",
        is_active=True,
    )
    test_db_session.add(owner)
    test_db_session.flush()
    test_db_session.add(CommunicationBoard(user_id=owner.id, name="Mi Tablero"))
    test_db_session.commit()
    resp = client.get("/api/boards", headers=_auth(admin_token))
    assert resp.status_code == 200
    full = [b["name"] for b in resp.json()]
    assert "Mi Tablero" in full
    # E5: empty and whitespace-only name behave exactly like an absent one.
    for blank in ("", "   "):
        resp = client.get(
            "/api/boards", params={"name": blank}, headers=_auth(admin_token)
        )
        assert resp.status_code == 200
        assert [b["name"] for b in resp.json()] == full
    # Padded real name still matches.
    resp = client.get(
        "/api/boards", params={"name": "  mi tablero  "}, headers=_auth(admin_token)
    )
    assert [b["name"] for b in resp.json()] == ["Mi Tablero"]


# --- A1: analytics telemetry fields bounded to their columns ---------------


def _usage_headers(regular_user) -> dict:
    return create_test_headers(
        regular_user.id, regular_user.username, regular_user.user_type
    )


def test_analytics_usage_overlong_fields_rejected_422(
    test_db_session, regular_user
):
    symbol = Symbol(label="hello", category="social", language="en", is_builtin=True)
    test_db_session.add(symbol)
    test_db_session.commit()
    headers = _usage_headers(regular_user)

    def _payload(**overrides):
        base = {
            "symbols": [{"id": symbol.id, "label": "hello", "category": "social"}],
        }
        base.update(overrides)
        return base

    # 60-char label vs SymbolUsageLog.symbol_label String(50).
    r = client.post(
        "/api/analytics/usage",
        json=_payload(
            symbols=[{"id": symbol.id, "label": "x" * 60, "category": "social"}]
        ),
        headers=headers,
    )
    assert r.status_code == 422, r.text
    # 5 KB category vs String(50).
    r = client.post(
        "/api/analytics/usage",
        json=_payload(
            symbols=[{"id": symbol.id, "label": "hello", "category": "c" * 5000}]
        ),
        headers=headers,
    )
    assert r.status_code == 422, r.text
    # 30-char semantic_intent vs String(20).
    r = client.post(
        "/api/analytics/usage",
        json=_payload(semantic_intent="i" * 30),
        headers=headers,
    )
    assert r.status_code == 422, r.text
    # 200-char context_topic vs String(100).
    r = client.post(
        "/api/analytics/usage",
        json=_payload(context_topic="t" * 200),
        headers=headers,
    )
    assert r.status_code == 422, r.text
    # Normal usage still persists (201).
    r = client.post("/api/analytics/log", json=_payload(), headers=headers)
    assert r.status_code == 201, r.text
    row = (
        test_db_session.query(SymbolUsageLog)
        .filter(SymbolUsageLog.symbol_label == "hello")
        .first()
    )
    assert row is not None


# --- S1: multipart symbol label/category Form caps ---------------------------


def _upload(client, headers, **overrides):
    data = {
        "label": "Upload OK",
        "description": "upload test",
        "category": "test",
        "keywords": "upload",
        "language": "en",
    }
    data.update(overrides)
    files = {"file": ("tiny.png", io.BytesIO(_png_bytes()), "image/png")}
    return client.post(
        "/api/boards/symbols/upload", data=data, files=files, headers=headers
    )


def test_multipart_upload_overlong_label_and_category_rejected(admin_user):
    headers = create_test_headers(admin_user.id, admin_user.username, "admin")
    r = _upload(client, headers, label="x" * 500)
    assert r.status_code == 422, r.text
    r = _upload(client, headers, category="c" * 200)
    assert r.status_code == 422, r.text
    # Normal upload still works.
    r = _upload(client, headers)
    assert r.status_code == 200, r.text


def test_multipart_generate_svg_overlong_label_rejected(admin_user):
    headers = create_test_headers(admin_user.id, admin_user.username, "admin")
    # generate-svg takes only Form fields (no file); validation must reject
    # the overlong label before the LLM provider is ever consulted.
    data = {
        "label": "x" * 500,
        "description": "svg test",
        "category": "test",
        "keywords": "svg",
        "language": "en",
    }
    r = client.post(
        "/api/boards/symbols/generate-svg", data=data, headers=headers
    )
    assert r.status_code == 422, r.text


# --- U1: recall scan gated on empty SQL results ------------------------------


def test_symbol_search_sql_hit_still_unions_bounded_recall(
    admin_token, test_db_session, monkeypatch
):
    monkeypatch.setattr("src.api.deps.get_vector_store", lambda: _EmptyVectorStore())
    test_db_session.add_all(
        [
            Symbol(
                label="strasse place", category="noun", language="de", is_builtin=True
            ),
            Symbol(
                label="straße", category="noun", language="de", is_builtin=True
            ),
        ]
    )
    test_db_session.commit()

    from src.api.routers import symbols as symbols_module

    calls = []
    original = symbols_module.unicode_recall_ids

    def counting(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)

    monkeypatch.setattr(symbols_module, "unicode_recall_ids", counting)
    resp = _symbol_search(admin_token, {"search": "STRASSE"})
    assert resp.status_code == 200
    # E1: SQL LIKE matches only 'strasse place' (ASCII lower() cannot fold
    # the stored ß), yet the fold-only 'straße' must ALSO be returned — the
    # recall union runs even when the SQL filter hits (PROMPT_21's
    # empty-results-only gate regressed exactly this). The scan ran once.
    assert {i["label"] for i in resp.json()} == {"strasse place", "straße"}
    assert len(calls) == 1


# --- U2: keywords standalone + boards name recall ----------------------------


def test_keywords_standalone_search_recalls_unicode_fold(
    admin_token, test_db_session
):
    test_db_session.add(
        Symbol(
            label="calle",
            keywords="straße",
            description=None,
            category="noun",
            language="de",
            is_builtin=True,
        )
    )
    test_db_session.commit()
    resp = _symbol_search(admin_token, {"keywords": "STRASSE"})
    assert resp.status_code == 200
    assert {i["label"] for i in resp.json()} == {"calle"}
    resp = _symbol_search(admin_token, {"keywords": "straße"})
    assert {i["label"] for i in resp.json()} == {"calle"}


def test_boards_name_search_recalls_unicode_fold(test_db_session, admin_token):
    owner = User(
        username=f"u2owner_{uuid4hex()}",
        display_name="U2 Owner",
        user_type="teacher",
        password_hash="test-hash",
        is_active=True,
    )
    test_db_session.add(owner)
    test_db_session.flush()
    test_db_session.add(CommunicationBoard(user_id=owner.id, name="straße"))
    test_db_session.commit()
    resp = client.get(
        "/api/boards", params={"name": "STRASSE"}, headers=_auth(admin_token)
    )
    assert resp.status_code == 200
    assert [b["name"] for b in resp.json()] == ["straße"]
    resp = client.get(
        "/api/boards", params={"name": "straße"}, headers=_auth(admin_token)
    )
    assert [b["name"] for b in resp.json()] == ["straße"]


# --- L1: lockout table trimmed exactly once per failed attempt --------------


def test_record_failed_attempt_trims_exactly_once(
    test_db_session, monkeypatch
):
    original = AccountLockoutService._trim_to_cap
    calls = []

    def counting(db):
        calls.append(1)
        return original(db)

    monkeypatch.setattr(AccountLockoutService, "_trim_to_cap", staticmethod(counting))

    username = f"l1_fresh_{uuid4hex()}"
    # Fresh username: insert branch, one trim AFTER the mutation.
    AccountLockoutService.record_failed_attempt(
        test_db_session, username, "10.0.0.1"
    )
    assert len(calls) == 1
    # Second failure for the same user (increment branch): also exactly one.
    AccountLockoutService.record_failed_attempt(
        test_db_session, username, "10.0.0.1"
    )
    assert len(calls) == 2


# --- T1: prediction inputs bounded -------------------------------------------


def test_next_symbol_request_overlong_inputs_422(regular_user):
    headers = _usage_headers(regular_user)
    r = client.post(
        "/api/analytics/next-symbol", json={"topic": "t" * 5000}, headers=headers
    )
    assert r.status_code == 422, r.text
    r = client.post(
        "/api/analytics/next-symbol",
        json={"current_symbols": "c" * 100_000},
        headers=headers,
    )
    assert r.status_code == 422, r.text


def test_tokenize_topic_caps_unique_tokens():
    from src.aac_app.services.prediction_service import (
        _TOPIC_TOKEN_MAX,
        _tokenize_topic,
    )

    tokens = _tokenize_topic("w " * 10_000)
    assert len(tokens) <= _TOPIC_TOKEN_MAX


def test_cached_topic_words_never_fetches_or_stores_oversized_key():
    from src.aac_app.services import prediction_service as ps

    calls = []

    def fetcher(language, topic):
        calls.append(topic)
        return ["uno", "dos"]

    long_topic = "a" * 500
    result = ps._cached_topic_words("es", long_topic, fetcher)
    # E9: an oversized topic never invokes the LLM fetcher (that call would
    # be discarded at the no-store guard); the empty result means only the
    # tokenized catalog tiers answer for such topics.
    assert result == ()
    assert calls == []
    # Not cached: the giant key must not live in the process cache either.
    assert (("es", long_topic)) not in ps._topics_word_cache
    # A normal-sized topic still fetches and caches.
    ps._cached_topic_words("es", "frutas", fetcher)
    assert calls == ["frutas"]
    assert ("es", "frutas") in ps._topics_word_cache


# --- B1: board ai_model bounded ----------------------------------------------


def _make_board_owner(client):
    user, token = _register(client, f"b1owner_{uuid4hex()}")
    return user, token


def test_board_ai_model_overlong_rejected_on_create_and_update(
    test_db_session
):
    user, token = _make_board_owner(client)
    big_model = "m" * 5000
    r = client.post(
        "/api/boards",
        params={"user_id": user["id"]},
        json={
            "name": "AI Board",
            "grid_rows": 3,
            "grid_cols": 4,
            "ai_enabled": True,
            "ai_provider": "ollama",
            "ai_model": big_model,
        },
        headers=_auth(token),
    )
    assert r.status_code == 422, r.text

    created = client.post(
        "/api/boards",
        params={"user_id": user["id"]},
        json={"name": "AI Board 2", "grid_rows": 3, "grid_cols": 4},
        headers=_auth(token),
    )
    assert created.status_code == 200, created.text
    board_id = created.json()["id"]
    r = client.put(
        f"/api/boards/{board_id}",
        json={
            "ai_enabled": True,
            "ai_provider": "ollama",
            "ai_model": big_model,
        },
        headers=_auth(token),
    )
    assert r.status_code == 422, r.text


def test_board_ai_normal_config_persists_and_disable_nulls(
    test_db_session
):
    user, token = _make_board_owner(client)
    # Enabling AI on create triggers a generation pass against the provider
    # (board_ai.create_board); stub it so the test exercises persistence, not
    # a real Ollama call — mirrors test_board_ai_routes.py.
    with (
        patch("src.api.routers.board_ai.BoardGenerationService") as mock_service,
        patch("src.api.routers.board_ai.OllamaProvider"),
    ):
        mock_service.return_value.generate_board_items = AsyncMock(
            return_value=[
                {"label": "Local item", "symbol_key": "local_item", "color": "#FFFFFF"}
            ]
        )
        created = client.post(
            "/api/boards",
            params={"user_id": user["id"]},
            json={
                "name": "AI Board OK",
                "grid_rows": 3,
                "grid_cols": 4,
                "ai_enabled": True,
                "ai_provider": "ollama",
                "ai_model": "llama3",
            },
            headers=_auth(token),
        )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["ai_enabled"] is True
    assert body["ai_provider"] == "ollama"
    assert body["ai_model"] == "llama3"
    board_id = body["id"]

    disabled = client.put(
        f"/api/boards/{board_id}",
        json={"ai_enabled": False},
        headers=_auth(token),
    )
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["ai_enabled"] is False
    assert disabled.json()["ai_model"] is None
    assert disabled.json()["ai_provider"] is None


# --- R1: inactive reset 404 after permission block ---------------------------


def test_teacher_reset_probe_of_inactive_unassigned_student_is_403(
    test_db_session
):
    teacher = User(
        username=f"r1teacher_{uuid4hex()}",
        display_name="R1 Teacher",
        user_type="teacher",
        password_hash="test-hash",
        is_active=True,
    )
    inactive = User(
        username=f"r1inactive_{uuid4hex()}",
        display_name="R1 Inactive",
        user_type="student",
        password_hash="test-hash",
        is_active=False,
    )
    test_db_session.add_all([teacher, inactive])
    test_db_session.commit()
    teacher_headers = create_test_headers(
        teacher.id, teacher.username, "teacher"
    )
    # Probing an inactive UNASSIGNED student must read as a roster 403, not a
    # 404 that leaks "id exists but is inactive".
    r = client.post(
        "/api/users/reset-password",
        headers=teacher_headers,
        json={"user_id": inactive.id, "new_password": "NewPassword123"},
    )
    assert r.status_code == 403, r.text


def test_teacher_reset_of_inactive_assigned_student_still_404(
    test_db_session
):
    teacher = User(
        username=f"r1teacher2_{uuid4hex()}",
        display_name="R1 Teacher2",
        user_type="teacher",
        password_hash="test-hash",
        is_active=True,
    )
    inactive = User(
        username=f"r1inactive2_{uuid4hex()}",
        display_name="R1 Inactive2",
        user_type="student",
        password_hash="test-hash",
        is_active=False,
    )
    test_db_session.add_all([teacher, inactive])
    test_db_session.flush()
    test_db_session.add(
        StudentTeacher(student_id=inactive.id, teacher_id=teacher.id)
    )
    test_db_session.commit()
    teacher_headers = create_test_headers(teacher.id, teacher.username, "teacher")
    r = client.post(
        "/api/users/reset-password",
        headers=teacher_headers,
        json={"user_id": inactive.id, "new_password": "NewPassword123"},
    )
    assert r.status_code == 404, r.text


def test_admin_reset_of_inactive_student_still_404(test_db_session, admin_user):
    inactive = User(
        username=f"r1inactive3_{uuid4hex()}",
        display_name="R1 Inactive3",
        user_type="student",
        password_hash="test-hash",
        is_active=False,
    )
    test_db_session.add(inactive)
    test_db_session.commit()
    admin_headers = create_test_headers(admin_user.id, admin_user.username, "admin")
    r = client.post(
        "/api/users/reset-password",
        headers=admin_headers,
        json={"user_id": inactive.id, "new_password": "NewPassword123"},
    )
    assert r.status_code == 404, r.text


def test_teacher_reset_of_active_assigned_student_still_works(
    test_db_session
):
    teacher = User(
        username=f"r1teacher3_{uuid4hex()}",
        display_name="R1 Teacher3",
        user_type="teacher",
        password_hash="test-hash",
        is_active=True,
    )
    student = User(
        username=f"r1active_{uuid4hex()}",
        display_name="R1 Active",
        user_type="student",
        password_hash="test-hash",
        is_active=True,
    )
    test_db_session.add_all([teacher, student])
    test_db_session.flush()
    test_db_session.add(StudentTeacher(student_id=student.id, teacher_id=teacher.id))
    test_db_session.commit()
    teacher_headers = create_test_headers(teacher.id, teacher.username, "teacher")
    r = client.post(
        "/api/users/reset-password",
        headers=teacher_headers,
        json={"user_id": student.id, "new_password": "NewPassword123"},
    )
    assert r.status_code == 200, r.text


# --- G1: guardian gender bounded ---------------------------------------------


def test_guardian_gender_overlong_rejected_422(test_db_session, admin_user):
    student = User(
        username=f"g1student_{uuid4hex()}",
        display_name="G1 Student",
        user_type="student",
        password_hash="test-hash",
        is_active=True,
    )
    test_db_session.add(student)
    test_db_session.commit()
    admin_headers = create_test_headers(admin_user.id, admin_user.username, "admin")

    r = client.post(
        f"/api/guardian-profiles/students/{student.id}",
        json={"template_name": "default", "gender": "g" * 200},
        headers=admin_headers,
    )
    assert r.status_code == 422, r.text

    created = client.post(
        f"/api/guardian-profiles/students/{student.id}",
        json={"template_name": "default", "gender": "niño"},
        headers=admin_headers,
    )
    assert created.status_code == 200, created.text
    assert created.json()["gender"] == "niño"

    r = client.put(
        f"/api/guardian-profiles/students/{student.id}",
        json={"gender": "g" * 200},
        headers=admin_headers,
    )
    assert r.status_code == 422, r.text
    # Clear-gender flow unchanged (update applies explicit falsy: an empty
    # string clears the stored value; None is omitted from the changes dict).
    cleared = client.put(
        f"/api/guardian-profiles/students/{student.id}",
        json={"gender": ""},
        headers=admin_headers,
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["gender"] == ""


# --- M1: settings mass-assign allow-list + shared bounds ---------------------


def test_update_user_settings_rejects_unknown_keys(
    test_db_session, regular_user
):
    with pytest.raises(ValueError):
        update_user_settings(
            test_db_session, regular_user.id, {"user_id": 999}
        )
    with pytest.raises(ValueError):
        update_user_settings(test_db_session, regular_user.id, {"typo_key": 1})
    # Known preference keys still apply (schema field set is the allow-list).
    settings = update_user_settings(
        test_db_session, regular_user.id, {"ui_language": "es", "dark_mode": True}
    )
    assert settings.ui_language == "es"
    assert settings.dark_mode is True


def test_saved_topic_overlong_rejected_by_schema_before_slice(
    test_db_session, admin_user
):
    # §8 deferred: learning.py's ``[:200]`` topic slice was unreachable — the
    # schema (SavedTopicCreate.topic max_length=200) rejects first. Prove it:
    # a 300-char topic is a 422 and no row is stored.
    headers = create_test_headers(admin_user.id, admin_user.username, "admin")
    r = client.post(
        "/api/learning/topics/saved",
        json={"topic": "t" * 300, "board": "board"},
        headers=headers,
    )
    assert r.status_code == 422, r.text


def test_shared_column_bound_constants_are_the_single_home():
    # M1b: the route-level bounds reference the shared constants, so a future
    # column change edits schemas.py alone. Spot-check equality with the
    # User columns they mirror.
    from src.aac_app.models import User

    assert User.__table__.c.username.type.length == schemas.USERNAME_MAX_LENGTH
    assert User.__table__.c.email.type.length == schemas.EMAIL_MAX_LENGTH
    assert (
        User.__table__.c.display_name.type.length == schemas.DISPLAY_NAME_MAX_LENGTH
    )
