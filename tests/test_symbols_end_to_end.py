import io
import os

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from tests.test_utils_auth import create_test_headers

client = TestClient(app)


@pytest.mark.usefixtures("setup_test_db")
def test_symbol_crud_with_usage_and_board_flow(tmp_path):
    # 1) Create user and auth header
    reg = client.post(
        "/api/auth/register",
        json={
            "username": "symboltester",
            "password": "TestPassword123",
            "display_name": "Symbol Tester",
            "user_type": "teacher",
        },
    )
    assert reg.status_code == 200
    user_id = reg.json()["id"]
    headers = create_test_headers(user_id, "symboltester", "teacher")

    # 2) Upload a small valid PNG symbol
    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x08\x00\x00\x00\x08\x08\x06"
        b"\x00\x00\x00\xc4\x0f\xbe\x8b\x00\x00\x00\x0bIDAT\x08\xd7c\xf8\xff\xff?\x03"
        b"\x05\x00\t\xfb\x02\xfe\x8a\xd0\xb7V\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    files = {"file": ("tiny.png", io.BytesIO(png_bytes), "image/png")}
    data = {
        "label": "Tiny",
        "description": "Tiny png",
        "category": "test",
        "keywords": "tiny",
        "language": "en",
    }
    up = client.post(
        "/api/boards/symbols/upload", data=data, files=files, headers=headers
    )
    assert up.status_code == 200
    sym = up.json()
    assert sym["label"] == "Tiny"
    assert sym["image_path"]
    # Uploaded file exists
    uploaded_path = sym["image_path"].lstrip("/")
    assert os.path.exists(uploaded_path)

    # 3) List symbols (all)
    res_all = client.get("/api/boards/symbols", headers=headers)
    assert res_all.status_code == 200
    assert any(s["id"] == sym["id"] for s in res_all.json())

    # 4) Create board
    board = client.post(
        f"/api/boards/?user_id={user_id}",
        json={"name": "E2E Symbols", "description": "test", "category": "general"},
        headers=headers,
    )
    assert board.status_code == 200
    board_id = board.json()["id"]

    # 5) Add symbol to board
    add = client.post(
        f"/api/boards/{board_id}/symbols",
        json={
            "symbol_id": sym["id"],
            "position_x": 0,
            "position_y": 0,
            "size": 1,
            "is_visible": True,
        },
        headers=headers,
    )
    assert add.status_code == 200

    # 6) Filter in-use
    res_in_use = client.get("/api/boards/symbols?usage=in_use", headers=headers)
    assert res_in_use.status_code == 200
    in_use_ids = [s["id"] for s in res_in_use.json()]
    assert sym["id"] in in_use_ids

    # 7) Delete without force should fail (in use)
    del_fail = client.delete(f"/api/boards/symbols/{sym['id']}", headers=headers)
    assert del_fail.status_code == 400

    # 8) Delete with force should succeed
    del_ok = client.delete(
        f"/api/boards/symbols/{sym['id']}?force=true", headers=headers
    )
    assert del_ok.status_code == 200

    # 9) Verify unused filter now shows empty for removed symbol
    res_unused = client.get("/api/boards/symbols?usage=unused", headers=headers)
    assert res_unused.status_code == 200
    assert sym["id"] not in [s["id"] for s in res_unused.json()]
