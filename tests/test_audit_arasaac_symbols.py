from __future__ import annotations

from scripts.audit_arasaac_symbols import audit
from src.aac_app.models import Symbol


def _entry(arasaac_id: int, label: str) -> dict:
    return {"_id": arasaac_id, "keywords": [{"keyword": label}]}


def test_audit_accepts_complete_bilingual_catalog(monkeypatch, test_db_session, tmp_path):
    uploads = tmp_path / "uploads"
    symbol_dir = uploads / "symbols"
    symbol_dir.mkdir(parents=True)
    monkeypatch.setattr("scripts.audit_arasaac_symbols.config.UPLOADS_DIR", uploads)

    (symbol_dir / "shared.png").write_bytes(b"png")
    test_db_session.add_all([
        Symbol(label="hola", language="es", image_path="/uploads/symbols/shared.png"),
        Symbol(label="hello", language="en", image_path="/uploads/symbols/shared.png"),
    ])
    test_db_session.commit()

    report = audit({
        "es": [_entry(1, "hola")],
        "en": [_entry(1, "hello")],
    })

    assert report["ok"] is True
    assert report["equivalence"] == {
        "es_ids": 1,
        "en_ids": 1,
        "shared_ids": 1,
        "es_only_ids": 0,
        "en_only_ids": 0,
    }
    assert report["languages"]["es"]["missing_images"] == 0
    assert report["languages"]["en"]["missing_catalog_labels"] == 0


def test_audit_reports_missing_label_image_and_id_mismatch(monkeypatch, test_db_session, tmp_path):
    uploads = tmp_path / "uploads"
    monkeypatch.setattr("scripts.audit_arasaac_symbols.config.UPLOADS_DIR", uploads)
    test_db_session.add(Symbol(label="hola", language="es", image_path="/uploads/symbols/no.png"))
    test_db_session.commit()

    report = audit({
        "es": [_entry(1, "hola"), _entry(2, "adios")],
        "en": [_entry(1, "hello"), _entry(3, "bye")],
    })

    assert report["ok"] is False
    assert report["equivalence"]["shared_ids"] == 1
    assert report["equivalence"]["es_only_ids"] == 1
    assert report["equivalence"]["en_only_ids"] == 1
    assert report["languages"]["es"]["missing_catalog_labels"] == 1
    assert report["languages"]["es"]["missing_images"] == 1
