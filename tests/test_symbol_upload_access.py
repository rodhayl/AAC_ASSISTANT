import io
import os

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from src.api.main import app
from tests.test_utils_auth import create_test_headers

client = TestClient(app)


@pytest.mark.usefixtures("setup_test_db")
def test_symbol_image_upload_and_accessible(admin_user):
    user_id = admin_user.id
    headers = create_test_headers(user_id, admin_user.username, "admin")

    # Upload tiny PNG
    png_buffer = io.BytesIO()
    Image.new("RGBA", (8, 8), (30, 120, 220, 255)).save(png_buffer, format="PNG")
    png_bytes = png_buffer.getvalue()
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
