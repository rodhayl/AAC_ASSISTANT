"""H4/H5 (PROMPT_5): symbol writes cannot bypass the field/file policies.

- H4: the generic ``PUT /boards/symbols/{id}`` used a bare ``setattr`` loop over
  ``SymbolUpdate``, which included ``image_path``/``audio_path`` — so any staff
  member could store an arbitrary path, skipping ``_save_symbol_image``'s
  MIME/size validation and orphaning the upload it replaced (which stays
  served under the immutable 1-year cache).
- H5: the multipart routes declared ``description``/``keywords`` as bare
  ``Form(None)`` while the JSON schema and the (Text, no-backstop) columns
  cap at 10_000 characters.
"""

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from src.aac_app.models import Symbol
from src.api.main import app
from tests.auth_helpers import create_test_headers

client = TestClient(app)

MAX_TEXT = 10_000


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def _staff_headers(admin_user) -> dict:
    return create_test_headers(admin_user.id, admin_user.username, "admin")


def _upload(admin_user, *, description=None, keywords=None, label="Bounds Upload"):
    data = {"label": label, "category": "test", "language": "en"}
    if description is not None:
        data["description"] = description
    if keywords is not None:
        data["keywords"] = keywords
    return client.post(
        "/api/boards/symbols/upload",
        data=data,
        files={"file": ("tiny.png", io.BytesIO(_png()), "image/png")},
        headers=_staff_headers(admin_user),
    )


@pytest.mark.usefixtures("setup_test_db")
def test_update_symbol_cannot_set_image_path(admin_user, test_db_session):
    symbol = Symbol(label="h4 original", category="test", language="en", image_path="/uploads/symbols/original.png")
    test_db_session.add(symbol)
    test_db_session.commit()
    test_db_session.refresh(symbol)

    response = client.put(
        f"/api/boards/symbols/{symbol.id}",
        json={"label": "h4 renamed", "image_path": "/etc/passwd"},
        headers=_staff_headers(admin_user),
    )
    assert response.status_code == 200, response.text

    test_db_session.expire_all()
    stored = test_db_session.get(Symbol, symbol.id)
    # The rename applied, the file pointer did not.
    assert stored.label == "h4 renamed"
    assert stored.image_path == "/uploads/symbols/original.png"


@pytest.mark.usefixtures("setup_test_db")
def test_update_symbol_still_accepts_the_documented_fields(admin_user, test_db_session):
    symbol = Symbol(label="h4 fields", category="test", language="en")
    test_db_session.add(symbol)
    test_db_session.commit()
    test_db_session.refresh(symbol)

    response = client.put(
        f"/api/boards/symbols/{symbol.id}",
        json={
            "label": "h4 fields edited",
            "description": "a description",
            "category": "other",
            "keywords": "one, two",
            "language": "en",
        },
        headers=_staff_headers(admin_user),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["label"] == "h4 fields edited"
    assert body["description"] == "a description"
    assert body["keywords"] == "one, two"


@pytest.mark.usefixtures("setup_test_db")
def test_upload_symbol_rejects_overlong_description_and_keywords(admin_user):
    too_long = "x" * (MAX_TEXT + 1)

    assert _upload(admin_user, description=too_long, label="h5 desc").status_code == 422
    assert _upload(admin_user, keywords=too_long, label="h5 kw").status_code == 422


@pytest.mark.usefixtures("setup_test_db")
def test_upload_symbol_accepts_the_boundary_lengths(admin_user):
    at_limit = "x" * MAX_TEXT
    response = _upload(
        admin_user, description=at_limit, keywords=at_limit, label="h5 boundary"
    )
    assert response.status_code == 200, response.text
    assert len(response.json()["description"]) == MAX_TEXT


@pytest.mark.usefixtures("setup_test_db")
def test_generate_svg_rejects_overlong_description_before_the_llm(admin_user):
    """Validation must fire before the LLM call, so the provider is never used."""
    response = client.post(
        "/api/boards/symbols/generate-svg",
        data={
            "label": "h5 svg",
            "category": "test",
            "language": "en",
            "description": "x" * (MAX_TEXT + 1),
        },
        headers=_staff_headers(admin_user),
    )
    assert response.status_code == 422, response.text
