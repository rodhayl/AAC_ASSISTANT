from __future__ import annotations

import asyncio
from contextlib import contextmanager

import pytest

from src.aac_app.models import Symbol
from src.aac_app.services import symbol_image_backfill as backfill_mod

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x08\x00\x00\x00\x08\x08\x06"
    b"\x00\x00\x00\xc4\x0f\xbe\x8b\x00\x00\x00\x0bIDAT\x08\xd7c\xf8\xff\xff?\x03"
    b"\x05\x00\t\xfb\x02\xfe\x8a\xd0\xb7V\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.mark.usefixtures("setup_test_db")
def test_backfill_downloads_missing_symbol_image(test_db_session, monkeypatch, tmp_path):
    symbol = Symbol(
        label="cow",
        category="farm_animals",
        language="en",
        image_path=None,
        is_builtin=True,
    )
    test_db_session.add(symbol)
    test_db_session.commit()
    test_db_session.refresh(symbol)

    @contextmanager
    def override_get_session():
        try:
            yield test_db_session
            test_db_session.commit()
        except Exception:
            test_db_session.rollback()
            raise

    class FakeArasaacService:
        async def search_symbols(self, query: str, locale: str = "es") -> list[dict]:
            assert query == "cow"
            assert locale in {"en", "es"}
            return [
                {
                    "id": 2300,
                    "label": "cow",
                    "keywords": "cow, farm animal",
                    "image_url": "https://example.test/cow.png",
                }
            ]

        async def download_symbol_image(self, arasaac_id: int) -> bytes | None:
            assert arasaac_id == 2300
            return PNG_BYTES

        async def close(self):
            return None

    uploads_dir = tmp_path / "uploads"
    monkeypatch.setattr(backfill_mod, "get_session", override_get_session)
    monkeypatch.setattr(backfill_mod, "ArasaacService", FakeArasaacService)
    monkeypatch.setattr(backfill_mod.config, "UPLOADS_DIR", uploads_dir)

    summary = asyncio.run(backfill_mod.backfill_missing_symbol_images(limit=10))

    test_db_session.refresh(symbol)
    assert summary["processed"] == 1
    assert summary["updated"] == 1
    assert summary["downloaded"] == 1
    assert summary["reused"] == 0
    assert summary["failed"] == 0
    assert symbol.image_path.startswith("/uploads/symbols/arasaac_auto_1_2300_")
    assert len(list((uploads_dir / "symbols").glob("arasaac_auto_1_2300_*.png"))) == 1


@pytest.mark.usefixtures("setup_test_db")
def test_backfill_reuses_existing_matching_image(test_db_session, monkeypatch, tmp_path):
    existing = Symbol(
        label="water",
        category="drinks",
        language="en",
        image_path="/uploads/symbols/shared-water.png",
        is_builtin=True,
    )
    missing = Symbol(
        label="water",
        category="drinks",
        language="en",
        image_path=None,
        is_builtin=True,
    )
    test_db_session.add_all([existing, missing])
    test_db_session.commit()
    test_db_session.refresh(existing)
    test_db_session.refresh(missing)

    @contextmanager
    def override_get_session():
        try:
            yield test_db_session
            test_db_session.commit()
        except Exception:
            test_db_session.rollback()
            raise

    class FakeArasaacService:
        async def search_symbols(self, query: str, locale: str = "es") -> list[dict]:
            raise AssertionError("network search should not run when a reusable image exists")

        async def download_symbol_image(self, arasaac_id: int) -> bytes | None:
            raise AssertionError("download should not run when a reusable image exists")

        async def close(self):
            return None

    uploads_dir = tmp_path / "uploads"
    symbol_dir = uploads_dir / "symbols"
    symbol_dir.mkdir(parents=True, exist_ok=True)
    (symbol_dir / "shared-water.png").write_bytes(PNG_BYTES)

    monkeypatch.setattr(backfill_mod, "get_session", override_get_session)
    monkeypatch.setattr(backfill_mod, "ArasaacService", FakeArasaacService)
    monkeypatch.setattr(backfill_mod.config, "UPLOADS_DIR", uploads_dir)

    summary = asyncio.run(backfill_mod.backfill_missing_symbol_images(limit=10))

    test_db_session.refresh(missing)
    assert summary["processed"] == 1
    assert summary["updated"] == 1
    assert summary["downloaded"] == 0
    assert summary["reused"] == 1
    assert summary["failed"] == 0
    assert missing.image_path == existing.image_path


@pytest.mark.usefixtures("setup_test_db")
def test_backfill_removes_download_when_row_was_filled_concurrently(
    test_db_session, monkeypatch, tmp_path
):
    symbol = Symbol(
        label="ball",
        category="toys",
        language="en",
        image_path=None,
        is_builtin=True,
    )
    test_db_session.add(symbol)
    test_db_session.commit()
    test_db_session.refresh(symbol)

    @contextmanager
    def override_get_session():
        try:
            yield test_db_session
            test_db_session.commit()
        except Exception:
            test_db_session.rollback()
            raise

    class FakeArasaacService:
        async def search_symbols(self, query: str, locale: str = "es") -> list[dict]:
            return [{"id": 2301, "label": query}]

        async def download_symbol_image(self, arasaac_id: int) -> bytes | None:
            test_db_session.execute(
                Symbol.__table__.update()
                .where(Symbol.id == symbol.id)
                .values(image_path="/uploads/symbols/existing.png")
            )
            test_db_session.commit()
            return PNG_BYTES

        async def close(self):
            return None

    uploads_dir = tmp_path / "uploads"
    monkeypatch.setattr(backfill_mod, "get_session", override_get_session)
    monkeypatch.setattr(backfill_mod, "ArasaacService", FakeArasaacService)
    monkeypatch.setattr(backfill_mod.config, "UPLOADS_DIR", uploads_dir)

    summary = asyncio.run(backfill_mod.backfill_missing_symbol_images(limit=10))

    test_db_session.refresh(symbol)
    assert summary["processed"] == 1
    assert summary["updated"] == 0
    assert summary["downloaded"] == 0
    assert summary["failed"] == 0
    assert symbol.image_path == "/uploads/symbols/existing.png"
    assert not list((uploads_dir / "symbols").glob("*.png"))


@pytest.mark.usefixtures("setup_test_db")
def test_reusable_image_candidates_exclude_target_symbol(
    test_db_session, monkeypatch, tmp_path
):
    target = Symbol(
        label="ball",
        category="toys",
        language="en",
        image_path=None,
        is_builtin=True,
    )
    source = Symbol(
        label="ball",
        category="toys",
        language="en",
        image_path="/uploads/symbols/source-ball.png",
        is_builtin=True,
    )
    test_db_session.add_all([target, source])
    test_db_session.commit()
    test_db_session.refresh(target)
    test_db_session.refresh(source)

    uploads_dir = tmp_path / "uploads"
    symbol_dir = uploads_dir / "symbols"
    symbol_dir.mkdir(parents=True, exist_ok=True)
    (symbol_dir / "source-ball.png").write_bytes(PNG_BYTES)
    monkeypatch.setattr(backfill_mod.config, "UPLOADS_DIR", uploads_dir)

    candidates = backfill_mod._reusable_image_paths(test_db_session, [target])
    assert candidates[("ball", "toys")] == [
        (source.id, "/uploads/symbols/source-ball.png")
    ]


@pytest.mark.usefixtures("setup_test_db")
def test_backfill_uses_keyword_fallback_queries(test_db_session, monkeypatch, tmp_path):
    symbol = Symbol(
        label="finished",
        category="social",
        language="en",
        image_path=None,
        keywords="finished, done, end, all done",
    )
    test_db_session.add(symbol)
    test_db_session.commit()
    test_db_session.refresh(symbol)

    seen_queries: list[tuple[str, str]] = []

    @contextmanager
    def override_get_session():
        try:
            yield test_db_session
            test_db_session.commit()
        except Exception:
            test_db_session.rollback()
            raise

    class FakeArasaacService:
        async def search_symbols(self, query: str, locale: str = "es") -> list[dict]:
            seen_queries.append((query, locale))
            if query == "finished":
                return []
            if query == "done":
                return [
                    {
                        "id": 4901,
                        "label": "done",
                        "keywords": "done, finished",
                        "image_url": "https://example.test/done.png",
                    }
                ]
            return []

        async def download_symbol_image(self, arasaac_id: int) -> bytes | None:
            assert arasaac_id == 4901
            return PNG_BYTES

        async def close(self):
            return None

    uploads_dir = tmp_path / "uploads"
    monkeypatch.setattr(backfill_mod, "get_session", override_get_session)
    monkeypatch.setattr(backfill_mod, "ArasaacService", FakeArasaacService)
    monkeypatch.setattr(backfill_mod.config, "UPLOADS_DIR", uploads_dir)

    summary = asyncio.run(backfill_mod.backfill_missing_symbol_images(limit=10))

    test_db_session.refresh(symbol)
    assert ("finished", "en") in seen_queries
    assert ("done", "en") in seen_queries
    assert summary["updated"] == 1
    assert summary["downloaded"] == 1
    assert summary["failed"] == 0
    assert symbol.image_path.startswith("/uploads/symbols/arasaac_auto_1_4901_")
