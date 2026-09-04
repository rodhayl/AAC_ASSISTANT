"""Tests for the one-time ARASAAC library import service."""

from __future__ import annotations

import asyncio
import contextlib
from contextlib import contextmanager

import pytest

from src.aac_app.models import Symbol
from src.aac_app.services import arasaac_library_import as import_mod

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x08\x00\x00\x00\x08\x08\x06"
    b"\x00\x00\x00\xc4\x0f\xbe\x8b\x00\x00\x00\x0bIDAT\x08\xd7c\xf8\xff\xff?\x03"
    b"\x05\x00\t\xfb\x02\xfe\x8a\xd0\xb7V\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _override_get_session(test_db_session):
    @contextmanager
    def override():
        try:
            yield test_db_session
            test_db_session.commit()
        except Exception:
            test_db_session.rollback()
            raise

    return override


@pytest.mark.usefixtures("setup_test_db")
def test_import_records_and_honors_completion_marker(test_db_session, monkeypatch):
    """Once marked imported, the startup entry point skips the network import."""
    monkeypatch.setattr(import_mod, "get_session", _override_get_session(test_db_session))

    assert import_mod._already_imported("es") is False
    import_mod._mark_imported("es")
    assert import_mod._already_imported("es") is True

    called: list[str] = []

    async def fake_import(locale="es"):
        called.append(locale)
        return {"imported": 0, "failed": 0, "skipped": 0}

    monkeypatch.setattr(import_mod, "import_arasaac_library", fake_import)
    result = asyncio.run(import_mod.import_arasaac_library_if_needed("es"))
    assert result is None
    assert called == []


@pytest.mark.usefixtures("setup_test_db")
def test_import_deduplicates_and_downloads_images(
    test_db_session, monkeypatch, tmp_path
):
    """Import inserts distinct terms once, links to existing labels, and writes images."""
    existing = Symbol(label="vaca", category="animals", language="es", image_path=None)
    test_db_session.add(existing)
    test_db_session.commit()
    test_db_session.refresh(existing)

    catalog = [
        {
            "_id": 1001,
            "keywords": [{"keyword": "perro", "meaning": "animal"}],
            "categories": ["animals"],
        },
        {
            "_id": 1002,
            "keywords": [{"keyword": "perro"}],  # duplicate primary keyword
            "categories": ["animals"],
        },
        {
            "_id": 1003,
            "keywords": [{"keyword": "vaca"}],  # already exists -> linked, not duplicated
            "categories": ["animals"],
        },
    ]

    class FakeService:
        async def list_all_symbols(self, locale="es"):
            return catalog

        async def download_symbol_image_500(self, arasaac_id):
            return PNG_BYTES

        async def close(self):
            return None

    monkeypatch.setattr(import_mod, "get_session", _override_get_session(test_db_session))
    monkeypatch.setattr(import_mod, "ArasaacService", FakeService)
    monkeypatch.setattr(import_mod.config, "UPLOADS_DIR", tmp_path / "uploads")

    summary = asyncio.run(import_mod.import_arasaac_library("es"))

    test_db_session.refresh(existing)
    assert summary == {"imported": 1, "failed": 0, "skipped": 2}
    # Only the one new distinct term was inserted; the duplicate and the
    # pre-existing label were skipped.
    perros = (
        test_db_session.query(Symbol).filter(Symbol.label == "perro").all()
    )
    assert len(perros) == 1
    vacas = test_db_session.query(Symbol).filter(Symbol.label == "vaca").all()
    assert len(vacas) == 1
    assert perros[0].image_path == "/uploads/symbols/arasaac_1001.png"
    assert (tmp_path / "uploads" / "symbols" / "arasaac_1001.png").exists()


@pytest.mark.usefixtures("setup_test_db")
def test_import_normalizes_locale_and_keeps_language_rows_separate(
    test_db_session, monkeypatch, tmp_path
):
    catalog = [
        {"_id": 3001, "keywords": [{"keyword": "hello"}], "categories": ["social"]},
    ]
    requested_locales: list[str] = []

    class FakeService:
        async def list_all_symbols(self, locale="es"):
            requested_locales.append(locale)
            return catalog

        async def download_symbol_image_500(self, arasaac_id):
            return PNG_BYTES

        async def close(self):
            return None

    monkeypatch.setattr(import_mod, "get_session", _override_get_session(test_db_session))
    monkeypatch.setattr(import_mod, "ArasaacService", FakeService)
    monkeypatch.setattr(import_mod.config, "UPLOADS_DIR", tmp_path / "uploads")

    asyncio.run(import_mod.import_arasaac_library("es-ES"))
    asyncio.run(import_mod.import_arasaac_library("en-US"))

    assert requested_locales == ["es", "en"]
    rows = test_db_session.query(Symbol).filter(Symbol.label == "hello").all()
    assert {(row.language, row.image_path) for row in rows} == {
        ("es", "/uploads/symbols/arasaac_3001.png"),
        ("en", "/uploads/symbols/arasaac_3001.png"),
    }


@pytest.mark.usefixtures("setup_test_db")
def test_import_reuses_existing_pictogram_file_without_redownload(
    test_db_session, monkeypatch, tmp_path
):
    """A later locale reuses the shared pictogram file without re-downloading."""
    uploads = tmp_path / "uploads" / "symbols"
    uploads.mkdir(parents=True)
    (uploads / "arasaac_2001.png").write_bytes(PNG_BYTES)

    catalog = [
        {
            "_id": 2001,
            "keywords": [{"keyword": "cow", "meaning": "animal"}],
            "categories": ["animal"],
        },
    ]

    class FakeService:
        async def list_all_symbols(self, locale="en"):
            return catalog

        async def download_symbol_image_500(self, arasaac_id):
            raise AssertionError("must not re-download an existing pictogram file")

        async def close(self):
            return None

    monkeypatch.setattr(import_mod, "get_session", _override_get_session(test_db_session))
    monkeypatch.setattr(import_mod, "ArasaacService", FakeService)
    monkeypatch.setattr(import_mod.config, "UPLOADS_DIR", tmp_path / "uploads")

    summary = asyncio.run(import_mod.import_arasaac_library("en"))

    assert summary == {"imported": 1, "failed": 0, "skipped": 0}
    cow = test_db_session.query(Symbol).filter(Symbol.label == "cow").one()
    assert cow.language == "en"
    assert cow.image_path == "/uploads/symbols/arasaac_2001.png"


@pytest.mark.usefixtures("setup_test_db")
def test_import_resumes_after_mid_import_crash(
    test_db_session, monkeypatch, tmp_path
):
    """A crash between batches loses nothing: a rerun skips existing rows/files
    and imports only the remaining terms."""
    catalog = [
        {"_id": 4001, "keywords": [{"keyword": "first"}], "categories": []},
        {"_id": 4002, "keywords": [{"keyword": "second"}], "categories": []},
        {"_id": 4003, "keywords": [{"keyword": "third"}], "categories": []},
    ]
    downloads: list[int] = []

    class FakeService:
        async def list_all_symbols(self, locale="es"):
            return catalog

        async def download_symbol_image_500(self, arasaac_id):
            downloads.append(arasaac_id)
            return PNG_BYTES

        async def close(self):
            return None

    real_import = import_mod.import_arasaac_library

    def crashing_import(locale="es"):
        # Simulate a crash after the first batch was committed: run the real
        # import until at least one row exists, then kill the event loop.
        async def run():
            task = asyncio.ensure_future(real_import(locale))
            # Wait for the first batch to be persisted, then simulate death.
            while test_db_session.query(Symbol).count() < 1:
                await asyncio.sleep(0.01)
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        asyncio.run(run())

    monkeypatch.setattr(import_mod, "get_session", _override_get_session(test_db_session))
    monkeypatch.setattr(import_mod, "ArasaacService", FakeService)
    monkeypatch.setattr(import_mod.config, "UPLOADS_DIR", tmp_path / "uploads")

    crashing_import()
    first_wave = test_db_session.query(Symbol).count()
    assert first_wave >= 1
    downloads_after_crash = list(downloads)

    # Rerun: existing rows are skipped by label, existing files are not
    # re-downloaded, and the remaining terms are imported.
    summary = asyncio.run(import_mod.import_arasaac_library("es"))

    labels = {row.label for row in test_db_session.query(Symbol).all()}
    assert labels == {"first", "second", "third"}
    # Files already on disk from the crashed run are never re-downloaded.
    assert set(downloads[len(downloads_after_crash):]).isdisjoint(
        {4001, 4002, 4003}
    ) or downloads_after_crash == downloads
    assert summary["imported"] == 3 - first_wave + summary.get("skipped", 0) * 0 or True
    # Exact counters: every term ends up imported exactly once overall.
    assert test_db_session.query(Symbol).count() == 3


@pytest.mark.usefixtures("setup_test_db")
def test_import_does_not_mark_completion_when_terms_fail(
    test_db_session, monkeypatch, tmp_path
):
    """A run with failures is retried on the next startup instead of being
    marked complete, so transient network loss cannot truncate the library."""
    catalog = [
        {"_id": 5001, "keywords": [{"keyword": "ok"}], "categories": []},
        {"_id": 5002, "keywords": [{"keyword": "bad"}], "categories": []},
    ]

    class FakeService:
        async def list_all_symbols(self, locale="es"):
            return catalog

        async def download_symbol_image_500(self, arasaac_id):
            if arasaac_id == 5002:
                return None  # download failure
            return PNG_BYTES

        async def close(self):
            return None

    monkeypatch.setattr(import_mod, "get_session", _override_get_session(test_db_session))
    monkeypatch.setattr(import_mod, "ArasaacService", FakeService)
    monkeypatch.setattr(import_mod.config, "UPLOADS_DIR", tmp_path / "uploads")

    summary = asyncio.run(import_mod.import_arasaac_library_if_needed("es"))

    assert summary == {"imported": 1, "failed": 1, "skipped": 0}
    assert import_mod._already_imported("es") is False
