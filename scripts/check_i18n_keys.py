"""Report translation keys that no frontend or backend code references.

The Spanish locale is the bundled default/fallback, so it is the canonical
set of keys. A key is considered live when either its full dotted path or its
leaf segment appears in the frontend (``t()``) or backend (``get_text`` /
``TranslationService.get``) source. Dynamic keys such as
``t(`categories.${id}`)`` are covered because the values that feed the
interpolation live in the source (e.g. ``LEARNING_SYMBOL_CATEGORY_IDS``).

This check is intentionally conservative: it only flags a key whose leaf never
appears anywhere in the scanned source, which cannot produce a false positive
on a statically or data-driven referenced key. Keys that are genuinely reached
only through external data (never mentioned in source) would be flagged and
must then be documented or added to a small allowlist.

Usage:
    uv run python scripts/check_i18n_keys.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCALES_ES = ROOT / "src" / "frontend" / "src" / "locales" / "es"
SOURCE_ROOTS = (
    ROOT / "src" / "frontend" / "src",
    ROOT / "src" / "api",
    ROOT / "src" / "aac_app",
)
SOURCE_SUFFIXES = {".ts", ".tsx", ".py"}


def _flatten(obj: object, prefix: str = "") -> set[str]:
    keys: set[str] = set()
    if isinstance(obj, dict):
        for key, value in obj.items():
            full = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                keys |= _flatten(value, full)
            else:
                keys.add(full)
    return keys


def _collect_source() -> str:
    chunks: list[str] = []
    for root in SOURCE_ROOTS:
        for path in root.rglob("*"):
            if path.suffix in SOURCE_SUFFIXES:
                try:
                    chunks.append(path.read_text(encoding="utf-8"))
                except OSError:
                    continue
    return "\n".join(chunks)


def main() -> int:
    source = _collect_source()
    dead: list[str] = []
    for locale_file in sorted(LOCALES_ES.rglob("*.json")):
        try:
            data = json.loads(locale_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"Invalid locale file {locale_file}: {exc}")
            return 1
        relative = locale_file.relative_to(LOCALES_ES)
        for key in sorted(_flatten(data)):
            leaf = key.rsplit(".", 1)[-1]
            if key in source or leaf in source:
                continue
            dead.append(f"{relative} :: {key}")

    if dead:
        print(f"Found {len(dead)} unreferenced translation keys:")
        for entry in dead:
            print(f"  {entry}")
        return 1

    print("i18n keys OK: every Spanish translation key is referenced in source.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
