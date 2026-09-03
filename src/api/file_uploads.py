"""Shared safeguards for multipart file uploads."""

from __future__ import annotations

import contextlib
import io
import os
import tempfile
from pathlib import Path

from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError
from PIL.Image import DecompressionBombError

DEFAULT_MAX_IMAGE_BYTES = 5 * 1024 * 1024
DEFAULT_MAX_AUDIO_BYTES = 10 * 1024 * 1024
ALLOWED_AUDIO_CONTENT_TYPES = frozenset(
    {
        "audio/wav",
        "audio/x-wav",
        "audio/wave",
        "audio/webm",
        "audio/ogg",
        "audio/mpeg",
        "audio/mp4",
        "audio/x-m4a",
        "video/webm",
        "application/ogg",
    }
)


def _has_audio_signature(content: bytes, content_type: str) -> bool:
    """Accept common browser/container signatures for the declared audio type."""
    if content_type in {"audio/wav", "audio/x-wav", "audio/wave"}:
        return len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WAVE"
    if content_type in {"audio/webm", "video/webm"}:
        return content.startswith(b"\x1a\x45\xdf\xa3")
    if content_type in {"audio/ogg", "application/ogg"}:
        return content.startswith(b"OggS")
    if content_type == "audio/mpeg":
        return content.startswith(b"ID3") or (
            len(content) >= 2 and content[0] == 0xFF and (content[1] & 0xE0) == 0xE0
        )
    if content_type in {"audio/mp4", "audio/x-m4a"}:
        return len(content) >= 12 and content[4:8] == b"ftyp"
    return False


async def _read_bounded_chunks(
    upload: UploadFile, *, max_bytes: int, too_large_detail: str
):
    """Yield upload chunks while enforcing the byte budget.

    Shared by the in-memory and temp-file readers so the chunk size,
    budget accounting, and 413 policy cannot drift apart.
    """
    total = 0
    while True:
        chunk = await upload.read(min(1024 * 1024, max_bytes - total + 1))
        if not chunk:
            return
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(status_code=413, detail=too_large_detail)
        yield chunk


async def read_upload_bytes(
    upload: UploadFile,
    *,
    max_bytes: int,
    too_large_detail: str,
    empty_detail: str,
    invalid_type_detail: str | None = None,
    allowed_content_types: frozenset[str] | None = None,
) -> bytes:
    """Read an upload in bounded chunks and reject empty/oversized input.

    ``Content-Length`` is not trusted: multipart clients may omit or falsify it.
    Reading incrementally keeps memory bounded and lets callers use one policy
    for all UploadFile endpoints.
    """
    content_type = (upload.content_type or "").split(";", 1)[0].strip().lower()
    if allowed_content_types is not None and content_type not in allowed_content_types:
        raise HTTPException(
            status_code=400,
            detail=invalid_type_detail or too_large_detail,
        )

    chunks = [
        chunk
        async for chunk in _read_bounded_chunks(
            upload, max_bytes=max_bytes, too_large_detail=too_large_detail
        )
    ]

    if not chunks:
        raise HTTPException(status_code=400, detail=empty_detail)
    return b"".join(chunks)


async def save_audio_upload(
    upload: UploadFile,
    *,
    max_bytes: int = DEFAULT_MAX_AUDIO_BYTES,
    invalid_type_detail: str,
    too_large_detail: str,
    empty_detail: str,
    suffix: str = ".wav",
) -> str:
    """Stream a bounded audio upload to a temporary file and return its path."""
    content_type = (upload.content_type or "").split(";", 1)[0].strip().lower()
    suffix = {
        "audio/webm": ".webm",
        "video/webm": ".webm",
        "audio/ogg": ".ogg",
        "application/ogg": ".ogg",
        "audio/mpeg": ".mp3",
        "audio/mp4": ".m4a",
        "audio/x-m4a": ".m4a",
    }.get(content_type, suffix)
    if content_type not in ALLOWED_AUDIO_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail=invalid_type_detail)
    total = 0
    prefix = bytearray()
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_path = temp_file.name
            async for chunk in _read_bounded_chunks(
                upload, max_bytes=max_bytes, too_large_detail=too_large_detail
            ):
                total += len(chunk)
                if len(prefix) < 32:
                    prefix.extend(chunk[: 32 - len(prefix)])
                temp_file.write(chunk)
        if total == 0:
            raise HTTPException(status_code=400, detail=empty_detail)
        if not _has_audio_signature(bytes(prefix), content_type):
            raise HTTPException(status_code=400, detail=invalid_type_detail)
        return temp_path
    except Exception:
        if temp_path:
            with contextlib.suppress(OSError):
                os.remove(temp_path)
        raise


async def read_image_upload(
    upload: UploadFile,
    *,
    max_bytes: int = DEFAULT_MAX_IMAGE_BYTES,
    invalid_type_detail: str,
    too_large_detail: str,
    empty_detail: str,
    max_pixels: int = 25_000_000,
) -> tuple[bytes, str]:
    """Read and decode an image, returning bytes and a safe normalized suffix."""
    content = await read_upload_bytes(
        upload,
        max_bytes=max_bytes,
        too_large_detail=too_large_detail,
        empty_detail=empty_detail,
    )
    try:
        with Image.open(io.BytesIO(content)) as image:
            image.verify()
            if image.width * image.height > max_pixels:
                raise HTTPException(status_code=413, detail=too_large_detail)
            image_format = (image.format or "").lower()
    except (DecompressionBombError, UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        status_code = 413 if isinstance(exc, DecompressionBombError) else 400
        raise HTTPException(status_code=status_code, detail=too_large_detail if status_code == 413 else invalid_type_detail) from exc

    extension_by_format = {
        "jpeg": ".jpg",
        "png": ".png",
        "gif": ".gif",
        "webp": ".webp",
        "bmp": ".bmp",
    }
    suffix = extension_by_format.get(image_format)
    if suffix is None:
        raise HTTPException(status_code=400, detail=invalid_type_detail)
    return content, suffix


def remove_owned_upload(public_path: str | None, uploads_dir: Path) -> None:
    """Delete a file only when its public path resolves inside the target upload subdirectory (e.g. config.UPLOADS_DIR / 'symbols')."""
    if not public_path or not public_path.startswith("/uploads/"):
        return
    relative = public_path.removeprefix("/uploads/")
    parts = Path(relative).parts
    if len(parts) < 2 or parts[0] != uploads_dir.name:
        return
    candidate = (uploads_dir.joinpath(*parts[1:])).resolve()
    root = uploads_dir.resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return
    try:
        candidate.unlink(missing_ok=True)
    except OSError:
        # Cleanup is best effort; a locked file must not break a DB operation.
        return
