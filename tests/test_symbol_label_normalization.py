"""PROMPT_17 D6: symbol-label case normalization is canonical everywhere.

`straße`/`STRASSE` and `ÉCOLE`/`école` must dedupe identically through every
symbol entry path. SQL ``lower()`` is ASCII-only on SQLite (and neither
backend folds ``ß``/``İ``), so the ARASAAC import and board-AI dedupe can no
longer mix ``func.lower`` with a Python-side fold: both must compare with the
canonical strip + casefold key (``normalize_symbol_label``).
"""

import asyncio

import pytest

from src.aac_app.models import Symbol
from src.aac_app.services.runtime_translation import normalize_symbol_label


def test_normalize_symbol_label_is_single_canonical_fold():
    """strip + casefold handles the diverging lower()/casefold() cases."""
    assert normalize_symbol_label("  straße  ") == normalize_symbol_label("STRASSE")
    assert normalize_symbol_label("ÉCOLE") == normalize_symbol_label("école")
    assert normalize_symbol_label("Straße") == "strasse"
    assert normalize_symbol_label("  ") == ""
    assert normalize_symbol_label(None) == ""


@pytest.mark.usefixtures("setup_test_db")
def test_board_ai_get_or_create_dedupes_non_ascii_labels(
    test_db_session,
):
    from src.api.routers.board_ai import get_or_create_symbol

    for stored, variant in (("ÉCOLE", "école"), ("straße", "STRASSE")):
        existing = Symbol(label=stored, category="general", language="es")
        test_db_session.add(existing)
        test_db_session.commit()
        test_db_session.refresh(existing)

        symbol, created = get_or_create_symbol(
            test_db_session, variant, "variant-key"
        )
        assert symbol.id == existing.id
        assert created is False
        # No duplicate row was created for the case variant.
        assert (
            test_db_session.query(Symbol).filter(Symbol.label == variant).count()
            == 0
        )


@pytest.mark.usefixtures("setup_test_db")
def test_arasaac_import_dedupes_non_ascii_labels(
    test_db_session, monkeypatch, tmp_path
):
    """Importing 'straße' links to the stored 'STRASSE' row (no download)."""
    from src import config
    from src.aac_app.models import User
    from src.api.routers import arasaac

    user = User(
        username="arasaac_norm_user",
        display_name="ARASAAC Norm User",
        user_type="student",
        password_hash="unused",
        is_active=True,
    )
    test_db_session.add(user)
    test_db_session.commit()
    test_db_session.refresh(user)

    existing = Symbol(label="STRASSE", category="general", language="es")
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
    monkeypatch.setattr(arasaac, "index_symbol", lambda _symbol: None)
    monkeypatch.setattr(config, "UPLOADS_DIR", tmp_path)

    payload = arasaac.ImportArasaacRequest(
        arasaac_id=555, label="straße", category="general"
    )
    result = asyncio.run(
        arasaac.import_arasaac_symbol(
            payload,
            db=test_db_session,
            current_user=user,
        )
    )

    assert result.id == existing.id
    assert downloaded is False
    assert (
        test_db_session.query(Symbol).filter(Symbol.label == "straße").count() == 0
    )


@pytest.mark.usefixtures("setup_test_db")
def test_bulk_import_dedupes_non_ascii_labels(
    test_db_session, monkeypatch, tmp_path
):
    """The bulk library import skips casefold-duplicate terms and existing rows."""
    from contextlib import contextmanager

    from src.aac_app.services import arasaac_library_import as import_mod

    PNG_BYTES = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x08\x00\x00\x00\x08\x08\x06"
        b"\x00\x00\x00\xc4\x0f\xbe\x8b\x00\x00\x00\x0bIDAT\x08\xd7c\xf8\xff\xff?\x03"
        b"\x05\x00\t\xfb\x02\xfe\x8a\xd0\xb7V\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    @contextmanager
    def override():
        try:
            yield test_db_session
            test_db_session.commit()
        except Exception:
            test_db_session.rollback()
            raise

    monkeypatch.setattr(import_mod, "get_session", override)

    # A pre-existing uppercase row with the sharp-s spelling: importing the
    # other-case variant must link, never duplicate.
    existing = Symbol(label="straße", category="general", language="es")
    test_db_session.add(existing)
    test_db_session.commit()

    catalog = [
        {
            "_id": 4001,
            "keywords": [{"keyword": "STRASSE", "meaning": "street"}],
            "categories": ["place"],
        },
        {
            "_id": 4002,
            "keywords": [{"keyword": "ÉCOLE", "meaning": "school"}],
            "categories": ["place"],
        },
        {
            "_id": 4003,
            "keywords": [{"keyword": "école"}],  # casefold duplicate of 4002
            "categories": ["place"],
        },
    ]

    class FakeService:
        async def list_all_symbols(self, locale="es"):
            return catalog

        async def download_symbol_image_500(self, arasaac_id):
            return PNG_BYTES

        async def close(self):
            return None

    monkeypatch.setattr(import_mod, "ArasaacService", FakeService)
    monkeypatch.setattr(import_mod.config, "UPLOADS_DIR", tmp_path / "uploads")

    summary = asyncio.run(import_mod.import_arasaac_library("es"))

    # STRASSE (already present as straße) and the école duplicate are both
    # skipped; only ÉCOLE is new.
    assert summary == {"imported": 1, "failed": 0, "skipped": 2}
    rows = test_db_session.query(Symbol).filter(Symbol.language == "es").all()
    labels = {row.label for row in rows}
    assert labels == {"straße", "ÉCOLE"}
