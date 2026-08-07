import asyncio
import io
from pathlib import Path

import pytest
from fastapi import HTTPException, UploadFile

from src.api.file_uploads import (
    ALLOWED_AUDIO_CONTENT_TYPES,
    read_audio_upload,
    read_image_upload,
    read_upload_bytes,
    remove_owned_upload,
    save_audio_upload,
)


def test_read_upload_bytes_rejects_oversized_input_without_unbounded_read():
    upload = UploadFile(
        filename="voice.wav",
        file=io.BytesIO(b"x" * 11),
        headers={"content-type": "audio/wav"},
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(read_upload_bytes(
            upload,
            max_bytes=10,
            allowed_content_types=ALLOWED_AUDIO_CONTENT_TYPES,
            invalid_type_detail="invalid type",
            too_large_detail="too large",
            empty_detail="empty",
        ))

    assert exc.value.status_code == 413


def test_read_audio_upload_rejects_declared_wav_with_invalid_signature():
    upload = UploadFile(
        filename="note.wav",
        file=io.BytesIO(b"not a wav"),
        headers={"content-type": "audio/wav"},
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            read_audio_upload(
                upload,
                invalid_type_detail="invalid type",
                too_large_detail="too large",
                empty_detail="empty",
            )
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "invalid type"


def test_save_audio_upload_accepts_webm_signature_and_cleans_after_caller_removes(tmp_path):
    upload = UploadFile(
        filename="recording.webm",
        file=io.BytesIO(b"\x1a\x45\xdf\xa3" + b"x" * 10),
        headers={"content-type": "audio/webm"},
    )

    path = asyncio.run(
        save_audio_upload(
            upload,
            invalid_type_detail="invalid type",
            too_large_detail="too large",
            empty_detail="empty",
        )
    )

    assert Path(path).suffix == ".webm"
    assert Path(path).exists()
    Path(path).unlink()
    assert not Path(path).exists()


def test_read_upload_bytes_rejects_wrong_audio_type_with_type_error():
    upload = UploadFile(
        filename="note.txt",
        file=io.BytesIO(b"hello"),
        headers={"content-type": "text/plain"},
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            read_upload_bytes(
                upload,
                max_bytes=100,
                allowed_content_types=ALLOWED_AUDIO_CONTENT_TYPES,
                invalid_type_detail="invalid type",
                too_large_detail="too large",
                empty_detail="empty",
            )
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "invalid type"


def test_image_upload_uses_decoded_format_and_rejects_fake_content():
    upload = UploadFile(
        filename="picture.png",
        file=io.BytesIO(b"not an image"),
        headers={"content-type": "image/png"},
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(read_image_upload(
            upload,
            invalid_type_detail="invalid image",
            too_large_detail="too large",
            empty_detail="empty",
        ))

    assert exc.value.status_code == 400
    assert exc.value.detail == "invalid image"


def test_remove_owned_upload_does_not_delete_outside_upload_root(tmp_path: Path):
    uploads = tmp_path / "uploads" / "symbols"
    uploads.mkdir(parents=True)
    owned = uploads / "owned.png"
    owned.write_bytes(b"x")
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"x")

    remove_owned_upload("/uploads/symbols/owned.png", uploads)
    remove_owned_upload("/uploads/../outside.png", uploads)

    assert not owned.exists()
    assert outside.exists()
