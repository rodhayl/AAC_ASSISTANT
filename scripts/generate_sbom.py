"""Generate a software bill of materials and checksums for a release.

Reads the pinned Python (``uv.lock``) and Node (``package-lock.json``)
dependency graphs and writes:

- ``dist/SBOM.json`` — a minimal CycloneDX 1.4 JSON document listing the
  application component and its dependencies with pinned versions.
- ``dist/SHA256SUMS.txt`` — SHA-256 checksums for every release artifact found in
  ``dist/``.

Run after ``build_package.bat``:

    uv run python scripts/generate_sbom.py [--dist DIR]

The SBOM is generated from lockfiles, so it reflects exactly what CI and
release builds install, not what happens to be in a local environment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _uv_dependencies() -> list[dict[str, str]]:
    """Extract ``name -> version`` from ``uv.lock`` package entries."""
    lock_path = PROJECT_ROOT / "uv.lock"
    data = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    packages: list[dict[str, str]] = []
    for package in data.get("package", []):
        name = package.get("name")
        version = package.get("version")
        if name and version:
            packages.append({"name": name, "version": version})
    packages.sort(key=lambda entry: entry["name"].casefold())
    return packages


def _npm_dependencies() -> list[dict[str, str]]:
    """Extract ``name -> version`` from the top-level npm lockfile packages."""
    lock_path = PROJECT_ROOT / "src" / "frontend" / "package-lock.json"
    data = json.loads(lock_path.read_text(encoding="utf-8"))
    packages: list[dict[str, str]] = []
    for name, metadata in data.get("packages", {}).items():
        if not name:
            continue
        version = metadata.get("version")
        if not version:
            continue
        label = name.removeprefix("node_modules/")
        packages.append({"name": label, "version": version})
    packages.sort(key=lambda entry: entry["name"].casefold())
    return packages


def _component(name: str, version: str) -> dict[str, str]:
    return {"type": "library", "name": name, "version": version}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _bom(dependencies: list[dict[str, str]]) -> dict:
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.4",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "name": "aac-assistant",
                "version": "2.0.0",
            }
        },
        "components": [_component(*item.values()) for item in dependencies],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dist",
        default=str(PROJECT_ROOT / "dist"),
        help="directory containing release artifacts (default: dist/)",
    )
    args = parser.parse_args()

    dist_dir = Path(args.dist).absolute()
    dist_dir.mkdir(parents=True, exist_ok=True)

    dependencies = _uv_dependencies() + _npm_dependencies()
    bom_path = dist_dir / "SBOM.json"
    bom_path.write_text(json.dumps(_bom(dependencies), indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {bom_path} ({len(dependencies)} dependencies)")

    artifacts = sorted(
        path
        for path in dist_dir.iterdir()
        if path.is_file()
        and path.suffix.casefold() in {".exe", ".zip", ".tar", ".gz", ".whl"}
    )
    checksum_lines = [f"{_sha256(path)}  {path.name}" for path in artifacts]
    checksum_path = dist_dir / "SHA256SUMS.txt"
    checksum_path.write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    print(f"Wrote {checksum_path} ({len(artifacts)} artifacts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
