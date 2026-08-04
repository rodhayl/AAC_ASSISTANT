"""Static file handling for the production single-port application."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException


class SPAStaticFiles(StaticFiles):
    """Serve static assets and fall back to ``index.html`` for SPA routes."""

    def _not_found_response(self, path: str):
        """Return the correct response when a static path does not exist."""
        normalized_path = path.replace("\\", "/").lstrip("/")
        if normalized_path == "api" or normalized_path.startswith("api/"):
            return JSONResponse(content={"detail": "Not Found"}, status_code=404)

        index_path = Path(self.directory) / "index.html"
        if index_path.is_file():
            return FileResponse(index_path)

        return JSONResponse(content={"detail": "Not Found"}, status_code=404)

    async def get_response(self, path: str, scope: dict[str, Any]):
        """Serve an asset or the SPA shell, preserving JSON API 404s."""
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
            return self._not_found_response(path)


def resolve_frontend_directory(
    project_root: Path,
    bundle_dir: Path,
    is_frozen: bool,
) -> Path | None:
    """Find the built frontend in development, portable, or frozen layouts."""
    candidates = (
        (bundle_dir / "frontend") if is_frozen else (project_root / "src" / "frontend" / "dist"),
        bundle_dir / "src" / "frontend" / "dist",
        project_root / "frontend",
        project_root / "src" / "frontend" / "dist",
    )
    for candidate in candidates:
        if (candidate / "index.html").is_file():
            return candidate
    return None
