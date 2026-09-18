"""Publish a GitHub release for an existing tag and upload local assets.

Zero-cost, Actions-free release path: GitHub Actions minutes are exhausted,
so the maintainer builds locally (build_package.bat with AAC_SIGN_RELEASE=1)
and this script publishes the artifacts with the same result the release
workflow would produce.

Usage (token needs repo scope; never printed):
    AAC_SIGNING_TOKEN=... python scripts/publish_release.py v2.0.1 \
        dist/AAC_Assistant_Setup_2.0.1.exe \
        dist/AAC_Assistant_Portable_2.0.1.zip \
        dist/SHA256SUMS.txt
"""

from __future__ import annotations

import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = "rodhayl/AAC_ASSISTANT"
API = f"https://api.github.com/repos/{REPO}"


def api(
    path: str,
    method: str = "GET",
    payload: dict | None = None,
    raw_body: bytes | None = None,
    content_type: str = "application/json",
):
    token = os.environ["AAC_SIGNING_TOKEN"]
    data = raw_body if raw_body is not None else (
        json.dumps(payload).encode() if payload is not None else None
    )
    request = urllib.request.Request(
        f"{API}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": content_type,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=3600) as response:
            body = response.read()
    except urllib.error.HTTPError as error:
        if error.code == 404:
            # Absent resources (no release for the tag yet) are expected.
            return {}
        detail = error.read().decode("utf-8", "replace")
        raise SystemExit(f"{method} {path} failed: HTTP {error.code} {detail}") from error
    if not body:
        return {}
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return {}


def ensure_release(tag: str, notes: str) -> dict:
    existing = api(f"/releases/tags/{tag}")
    if existing.get("id"):
        print(f"Release for {tag} already exists (id {existing['id']})")
        return existing
    release = api(
        "/releases",
        method="POST",
        payload={
            "tag_name": tag,
            "name": f"AAC Assistant {tag}",
            "body": notes,
            "draft": False,
            "prerelease": False,
        },
    )
    print(f"Release created for {tag} (id {release['id']})")
    return release


def upload_asset(release_id: int, file_path: Path, label: str = "") -> None:
    name = file_path.name
    for asset in api(f"/releases/{release_id}/assets") or []:
        if asset.get("name") == name:
            print(f"Asset already present, skipping: {name} ({asset.get('size')} bytes)")
            return
    upload_url = api(f"/releases/{release_id}")["upload_url"].split("{")[0]
    mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
    size = file_path.stat().st_size
    token = os.environ["AAC_SIGNING_TOKEN"]
    request = urllib.request.Request(
        f"{upload_url}?name={name}" + (f"&label={label}" if label else ""),
        data=file_path.read_bytes(),
        method="POST",
        headers={
            "Authorization": f"token {token}",
            "Content-Type": mime,
            "Content-Length": str(size),
        },
    )
    started = time.time()
    with urllib.request.urlopen(request, timeout=3600) as response:
        result = json.loads(response.read())
    rate = size / max(time.time() - started, 0.1) / 1_000_000
    print(f"Uploaded: {name} ({size:,} bytes, {rate:.1f} MB/s) state={result.get('state')}")


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    tag = sys.argv[1]
    files = [Path(p) for p in sys.argv[2:]]
    for path in files:
        if not path.is_file():
            print(f"Missing asset: {path}", file=sys.stderr)
            return 1

    release = ensure_release(tag, notes=NOTES)
    for path in files:
        upload_asset(release["id"], path)

    names = sorted(a["name"] for a in api(f"/releases/{release['id']}/assets") or [])
    print(f"Release assets now: {names}")
    print(f"Published: https://github.com/{REPO}/releases/tag/{tag}")
    return 0


NOTES = """## AAC Assistant 2.0.1

Maintenance release focused on Windows launch reliability, release
infrastructure, and accumulated security, accessibility, and test-suite
improvements. Full details in [docs/RELEASE_NOTES.md](https://github.com/rodhayl/AAC_ASSISTANT/blob/main/docs/RELEASE_NOTES.md).

### Highlights

- **Windows launchers fixed** — `start.bat` / `install_dependencies.bat` find
  winget-installed `uv`, pin Python 3.13, and survive Smart App Control
  blocking uv's venv launcher (os error 4551).
- **Authenticode-signed binaries** — the installer and app executable are
  signed; the signature is trusted on machines where the certificate was
  imported (see README "Code signing").
- **Offline capability verified** — Kokoro TTS, faster-whisper, fastembed and
  sqlite-vec all load from the bundled models; 253/253 browser E2E tests pass.

### Upgrading

Run `AAC_Assistant_Setup_2.0.1.exe`; the existing installation, database, and
uploads are preserved. Verify integrity with `SHA256SUMS.txt`.
"""


if __name__ == "__main__":
    raise SystemExit(main())
