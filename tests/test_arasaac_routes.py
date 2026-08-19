import asyncio

import pytest
from fastapi import HTTPException

from src import config
from src.aac_app.models import Symbol, User, UserSettings
from src.api.routers import arasaac


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
