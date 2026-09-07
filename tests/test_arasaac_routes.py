import asyncio

import pytest
from fastapi import HTTPException

from src import config
from src.aac_app.models import Symbol, User, UserSettings
from src.api.routers import arasaac


def test_arasaac_search_percent_encodes_query_in_url():
    """Queries with spaces or special characters must not corrupt the URL path."""
    from src.aac_app.services.arasaac import ArasaacService

    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return [
                {"_id": 1, "keywords": [{"keyword": "pan"}], "desc": "bread"}
            ]

    class FakeClient:
        async def get(self, url):
            captured["url"] = url
            return FakeResponse()

        async def aclose(self):
            pass

    service = ArasaacService()
    service.client = FakeClient()
    try:
        results = asyncio.run(service.search_symbols("pan de leche", "es"))
    finally:
        asyncio.run(service.close())

    assert (
        captured["url"]
        == "https://api.arasaac.org/api/pictograms/es/bestsearch/pan%20de%20leche"
    )
    assert results and results[0]["label"] == "pan"

    # Path-breaking characters are encoded too, never parsed as separators.
    captured.clear()
    asyncio.run(service.search_symbols("rosa#1?x/y", "es"))
    assert captured["url"].endswith("/bestsearch/rosa%231%3Fx%2Fy")


def test_arasaac_search_sanitizes_hostile_locale():
    """A hostile locale must be replaced with a safe code before URL use."""
    from src.aac_app.services.arasaac import ArasaacService

    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return []

    class FakeClient:
        async def get(self, url):
            captured["url"] = url
            return FakeResponse()

        async def aclose(self):
            pass

    service = ArasaacService()
    service.client = FakeClient()
    try:
        # Traversal in the locale must not reach the request URL.
        asyncio.run(service.search_symbols("pan", "../../../etc/passwd"))
    finally:
        asyncio.run(service.close())

    assert captured["url"].startswith(
        "https://api.arasaac.org/api/pictograms/es/bestsearch/"
    )
    assert ".." not in captured["url"]


def test_arasaac_locale_and_id_whitelists():
    """Locale and id helpers only accept safe path segments."""
    from src.aac_app.services.arasaac import _validated_id_path, _validated_locale

    assert _validated_locale("es") == "es"
    assert _validated_locale("fr") == "fr"
    assert _validated_locale("es-ES") == "es"
    assert _validated_locale("../../../etc") == "es"
    assert _validated_locale("") == "es"
    assert _validated_id_path(123) == "123"
    assert _validated_id_path("456") == "456"
    with pytest.raises(ValueError):
        _validated_id_path("../../etc/passwd")
    with pytest.raises(ValueError):
        _validated_id_path("12/34")


@pytest.mark.usefixtures("setup_test_db")
def test_arasaac_import_preserves_missing_image_status_and_closes_client(
    test_db_session, monkeypatch
):
    user = User(
        username="arasaac_import_user",
        display_name="ARASAAC Import User",
        user_type="student",
        password_hash="unused",
        is_active=True,
    )
    test_db_session.add(user)
    test_db_session.commit()
    test_db_session.refresh(user)

    closed = False

    class FakeArasaacService:
        async def download_symbol_image(self, arasaac_id: int) -> bytes | None:
            assert arasaac_id == 123
            return None

        async def close(self):
            nonlocal closed
            closed = True

    monkeypatch.setattr(arasaac, "ArasaacService", FakeArasaacService)
    monkeypatch.setattr(arasaac, "get_text", lambda **_kwargs: "download failed")

    payload = arasaac.ImportArasaacRequest(arasaac_id=123, label="missing")
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            arasaac.import_arasaac_symbol(
                payload,
                db=test_db_session,
                current_user=user,
            )
        )

    assert error.value.status_code == 404
    assert error.value.detail == "download failed"
    assert closed is True


def test_arasaac_import_links_to_existing_symbol_by_casefolded_label(
    test_db_session, monkeypatch
):
    """Importing an already-known term must not create a duplicate row."""
    user = User(
        username="arasaac_dedupe_user",
        display_name="ARASAAC Dedupe User",
        user_type="student",
        password_hash="unused",
        is_active=True,
    )
    test_db_session.add(user)
    test_db_session.commit()
    test_db_session.refresh(user)

    existing = Symbol(label="house", category="ARASAAC", language="es")
    test_db_session.add(existing)
    test_db_session.commit()
    test_db_session.refresh(existing)

    downloaded = False

    class FakeArasaacService:
        async def download_symbol_image(self, arasaac_id: int) -> bytes:
            nonlocal downloaded
            downloaded = True
            return b"image-bytes"

        async def close(self):
            return None

    monkeypatch.setattr(arasaac, "ArasaacService", FakeArasaacService)

    payload = arasaac.ImportArasaacRequest(
        arasaac_id=999, label="House", category="ARASAAC"
    )
    result = asyncio.run(
        arasaac.import_arasaac_symbol(
            payload,
            db=test_db_session,
            current_user=user,
        )
    )

    assert result.id == existing.id
    assert test_db_session.query(Symbol).filter(Symbol.label == "house").count() == 1
    assert downloaded is False


def test_arasaac_import_keeps_file_when_optional_indexing_fails(
    test_db_session, monkeypatch, tmp_path
):
    user = User(
        username="arasaac_file_cleanup_user",
        display_name="ARASAAC File Cleanup User",
        user_type="student",
        password_hash="unused",
        is_active=True,
    )
    test_db_session.add(user)
    test_db_session.commit()
    test_db_session.refresh(user)

    class FakeArasaacService:
        async def download_symbol_image(self, arasaac_id: int) -> bytes:
            assert arasaac_id == 456
            return b"image-bytes"

        async def close(self):
            return None

    monkeypatch.setattr(arasaac, "ArasaacService", FakeArasaacService)
    monkeypatch.setattr(arasaac, "index_symbol", lambda _symbol: (_ for _ in ()).throw(RuntimeError("index failed")))
    monkeypatch.setattr(config, "UPLOADS_DIR", tmp_path)
    monkeypatch.setattr(arasaac, "get_text", lambda **_kwargs: "import failed")

    payload = arasaac.ImportArasaacRequest(arasaac_id=456, label="cleanup")
    result = asyncio.run(
        arasaac.import_arasaac_symbol(
            payload,
            db=test_db_session,
            current_user=user,
        )
    )

    assert result.label == "cleanup"
    assert list((tmp_path / "symbols").glob("*.png")) != []
    assert test_db_session.query(Symbol).filter(Symbol.label == "cleanup").count() == 1


def test_arasaac_import_normalizes_ui_language_to_base_code(
    test_db_session, monkeypatch, tmp_path
):
    """A regional UI locale (e.g. es-ES) must be stored as its base code so
    the symbol search's exact language filter (es/en) can find it."""
    user = User(
        username="arasaac_lang_user",
        display_name="ARASAAC Lang User",
        user_type="student",
        password_hash="unused",
        is_active=True,
    )
    test_db_session.add(user)
    test_db_session.commit()
    test_db_session.refresh(user)
    test_db_session.add(UserSettings(user_id=user.id, ui_language="es-ES"))
    test_db_session.commit()

    class FakeArasaacService:
        async def download_symbol_image(self, arasaac_id: int) -> bytes:
            return b"image-bytes"

        async def close(self):
            return None

    monkeypatch.setattr(arasaac, "ArasaacService", FakeArasaacService)
    monkeypatch.setattr(arasaac, "index_symbol", lambda _symbol: None)
    monkeypatch.setattr(config, "UPLOADS_DIR", tmp_path)

    payload = arasaac.ImportArasaacRequest(
        arasaac_id=789, label="lenguaje", category="ARASAAC"
    )
    result = asyncio.run(
        arasaac.import_arasaac_symbol(
            payload,
            db=test_db_session,
            current_user=user,
        )
    )

    assert result.language == "es"


@pytest.mark.usefixtures("setup_test_db")
def test_arasaac_search_without_locale_uses_ui_language(
    test_db_session, monkeypatch
):
    """Omitted locale defers to the persisted ui_language (normalized).

    The pre-fix code declared ``locale: str = Query("es", ...)`` so the
    ``if not locale`` branch that promised this behavior was unreachable and
    the UI-language preference never applied.
    """
    user = User(
        username="arasaac_lang_search_user",
        display_name="ARASAAC Lang Search User",
        user_type="teacher",
        password_hash="unused",
        is_active=True,
    )
    test_db_session.add(user)
    test_db_session.commit()
    test_db_session.refresh(user)
    test_db_session.add(UserSettings(user_id=user.id, ui_language="en-US"))
    test_db_session.commit()
    test_db_session.refresh(user)

    captured = {}

    class FakeArasaacService:
        def __init__(self):
            pass

        async def search_symbols(self, query: str, locale: str):
            captured["query"] = query
            captured["locale"] = locale
            return []

        async def close(self):
            return None

    monkeypatch.setattr(arasaac, "ArasaacService", FakeArasaacService)

    asyncio.run(arasaac.search_arasaac(q="pan", locale=None, current_user=user))

    # en-US normalizes to its base code, matching the import path.
    assert captured == {"query": "pan", "locale": "en"}


@pytest.mark.usefixtures("setup_test_db")
def test_arasaac_search_explicit_locale_wins_over_ui_language(
    test_db_session, monkeypatch
):
    """An explicitly supplied locale is used verbatim; ui_language is skipped."""
    user = User(
        username="arasaac_explicit_search_user",
        display_name="ARASAAC Explicit Search User",
        user_type="teacher",
        password_hash="unused",
        is_active=True,
    )
    test_db_session.add(user)
    test_db_session.commit()
    test_db_session.refresh(user)
    test_db_session.add(UserSettings(user_id=user.id, ui_language="es-ES"))
    test_db_session.commit()
    test_db_session.refresh(user)

    captured = {}

    class FakeArasaacService:
        async def search_symbols(self, query: str, locale: str):
            captured["locale"] = locale
            return []

        async def close(self):
            return None

    monkeypatch.setattr(arasaac, "ArasaacService", FakeArasaacService)

    asyncio.run(
        arasaac.search_arasaac(q="pain", locale="fr", current_user=user)
    )
    assert captured == {"locale": "fr"}


@pytest.mark.usefixtures("setup_test_db")
def test_arasaac_search_without_locale_or_settings_defaults_to_es(
    test_db_session, monkeypatch
):
    """No locale and no settings row: the API default "es" applies."""
    user = User(
        username="arasaac_default_search_user",
        display_name="ARASAAC Default Search User",
        user_type="teacher",
        password_hash="unused",
        is_active=True,
    )
    test_db_session.add(user)
    test_db_session.commit()
    test_db_session.refresh(user)

    captured = {}

    class FakeArasaacService:
        async def search_symbols(self, query: str, locale: str):
            captured["locale"] = locale
            return []

        async def close(self):
            return None

    monkeypatch.setattr(arasaac, "ArasaacService", FakeArasaacService)

    asyncio.run(arasaac.search_arasaac(q="pan", locale=None, current_user=user))
    assert captured == {"locale": "es"}


def test_arasaac_search_rejects_oversized_query(test_db_session, client):
    """A giant ARASAAC search query is rejected by validation (422) before
    any upstream network request is built."""
    from tests.auth_helpers import create_test_headers

    user = User(
        username="arasaac_query_user",
        display_name="ARASAAC Query User",
        user_type="teacher",
        password_hash="unused",
        is_active=True,
    )
    test_db_session.add(user)
    test_db_session.commit()
    test_db_session.refresh(user)
    headers = create_test_headers(user.id, user.username, "teacher")

    response = client.get(
        "/api/arasaac/search", params={"q": "x" * 201}, headers=headers
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "string_too_long"


def test_arasaac_search_rejects_whitespace_only_query_without_upstream_call(
    test_db_session, client, monkeypatch
):
    """A whitespace-only ``q`` is a 400 and never burns an upstream request.

    ``min_length=1`` alone lets ``"   "`` through validation, so the route
    must strip and reject before constructing the ARASAAC service.
    """
    from tests.auth_helpers import create_test_headers

    user = User(
        username="arasaac_space_query_user",
        display_name="ARASAAC Space Query User",
        user_type="teacher",
        password_hash="unused",
        is_active=True,
    )
    test_db_session.add(user)
    test_db_session.commit()
    test_db_session.refresh(user)
    headers = create_test_headers(user.id, user.username, "teacher")

    class ExplodingService:
        def __init__(self):
            pass

        async def search_symbols(self, query, locale):
            raise AssertionError("upstream must not be called for blank queries")

        async def close(self):
            return None

    monkeypatch.setattr(arasaac, "ArasaacService", ExplodingService)

    response = client.get(
        "/api/arasaac/search", params={"q": "    "}, headers=headers
    )
    assert response.status_code == 400, response.text


def test_arasaac_import_rejects_label_blocked_by_global_policy(
    test_db_session, monkeypatch, tmp_path
):
    """A client-supplied label the global policy blocks is never imported.

    The ARASAAC import must apply the same layer-1 admission gate as
    board_ai.get_or_create_symbol (400 errors.safety.symbolBlocked) and must
    run it BEFORE the image download: a blocked label spends no network and
    leaves no row or file behind.
    """
    from src.aac_app.services import content_safety as safety_module

    user = User(
        username="arasaac_blocked_user",
        display_name="ARASAAC Blocked User",
        user_type="student",
        password_hash="unused",
        is_active=True,
    )
    test_db_session.add(user)
    test_db_session.commit()
    test_db_session.refresh(user)

    checked_labels = []

    class BlockingVerdict:
        blocked = True

    class FakePolicy:
        pass

    monkeypatch.setattr(
        safety_module, "load_global_policy", lambda: FakePolicy()
    )
    monkeypatch.setattr(
        safety_module,
        "check_text",
        lambda _policy, text: checked_labels.append(text) or BlockingVerdict(),
    )
    monkeypatch.setattr(arasaac, "get_text", lambda **_kwargs: "blocked label")
    monkeypatch.setattr(config, "UPLOADS_DIR", tmp_path)

    class FakeArasaacService:
        async def download_symbol_image(self, arasaac_id: int) -> bytes:
            raise AssertionError(
                "network must not be spent downloading a blocked label"
            )

        async def close(self):
            return None

    monkeypatch.setattr(arasaac, "ArasaacService", FakeArasaacService)

    payload = arasaac.ImportArasaacRequest(
        arasaac_id=1, label="badword", category="ARASAAC"
    )
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            arasaac.import_arasaac_symbol(
                payload,
                db=test_db_session,
                current_user=user,
            )
        )

    assert error.value.status_code == 400
    assert error.value.detail == "blocked label"
    assert checked_labels == ["badword"]
    assert test_db_session.query(Symbol).filter(Symbol.label == "badword").count() == 0
    assert list((tmp_path / "symbols").glob("*.png")) == []

def test_arasaac_import_allows_label_that_passes_global_policy(
    test_db_session, monkeypatch, tmp_path
):
    """A label that passes the policy gate still imports normally (201 path)."""
    from src.aac_app.services import content_safety as safety_module

    user = User(
        username="arasaac_clean_user",
        display_name="ARASAAC Clean User",
        user_type="student",
        password_hash="unused",
        is_active=True,
    )
    test_db_session.add(user)
    test_db_session.commit()
    test_db_session.refresh(user)

    class PassingVerdict:
        blocked = False

    monkeypatch.setattr(
        safety_module, "load_global_policy", lambda: object()
    )
    monkeypatch.setattr(
        safety_module,
        "check_text",
        lambda _policy, _text: PassingVerdict(),
    )
    monkeypatch.setattr(arasaac, "index_symbol", lambda _symbol: None)
    monkeypatch.setattr(config, "UPLOADS_DIR", tmp_path)

    class FakeArasaacService:
        async def download_symbol_image(self, arasaac_id: int) -> bytes:
            assert arasaac_id == 2
            return b"image-bytes"

        async def close(self):
            return None

    monkeypatch.setattr(arasaac, "ArasaacService", FakeArasaacService)

    payload = arasaac.ImportArasaacRequest(
        arasaac_id=2, label="pan", category="ARASAAC"
    )
    result = asyncio.run(
        arasaac.import_arasaac_symbol(
            payload,
            db=test_db_session,
            current_user=user,
        )
    )

    assert result.label == "pan"
    assert test_db_session.query(Symbol).filter(Symbol.label == "pan").count() == 1
    assert list((tmp_path / "symbols").glob("*.png")) != []
