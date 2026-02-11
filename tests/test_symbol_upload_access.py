import io
import os

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from tests.test_utils_auth import create_test_headers

client = TestClient(app)


@pytest.mark.usefixtures("setup_test_db")
def test_symbol_image_upload_and_accessible():
    # Register user
    reg = client.post(
        "/api/auth/register",
        json={
            "username": "imguser",
            "password": "TestPassword123",
            "display_name": "Img User",
            "user_type": "teacher",
        },
    )
    assert reg.status_code == 200
    user_id = reg.json()["id"]
    headers = create_test_headers(user_id, "imguser", "teacher")

    # Upload tiny PNG
    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x08\x00\x00\x00\x08\x08\x06"
        b"\x00\x00\x00\xc4\x0f\xbe\x8b\x00\x00\x00\x0bIDAT\x08\xd7c\xf8\xff\xff?\x03"
        b"\x05\x00\t\xfb\x02\xfe\x8a\xd0\xb7V\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    files = {"file": ("tiny.png", io.BytesIO(png_bytes), "image/png")}
    data = {
        "label": "Tiny Upload",
        "description": "upload test",
        "category": "test",
        "keywords": "tiny",
        "language": "en",
    }
    up = client.post(
        "/api/boards/symbols/upload", data=data, files=files, headers=headers
    )
    assert up.status_code == 200
    sym = up.json()
    assert sym["image_path"].startswith("/uploads/")

    # File exists on disk
    disk_path = sym["image_path"].lstrip("/")
    assert os.path.exists(disk_path)

    # Static file is served
    resp = client.get(sym["image_path"])
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/")
