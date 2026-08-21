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

The same pass also verifies the reverse direction: every ``get_text`` /
``get_shared_text`` key used by the backend routers must resolve in the
locale JSON for the namespace it is looked up in (honoring local wrappers
that pin a namespace, e.g. ``learning.py``), so a missing key can never be
returned to clients as a raw dotted string.

Usage:
    uv run python scripts/check_i18n_keys.py
"""

from __future__ import annotations

import ast
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


def _load_locale(lang: str, namespace: str) -> dict:
    path = ROOT / "src" / "frontend" / "src" / "locales" / lang / f"{namespace}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _resolve(data: dict, key: str) -> str | None:
    value: object = data
    for part in key.split("."):
        if isinstance(value, dict) and part in value:
            value = value[part]
        else:
            return None
    return value if isinstance(value, str) else None


def _check_backend_keys_resolve() -> list[str]:
    """Return backend get_text keys that do not resolve in any locale file."""
    errors: list[str] = []
    for router in sorted((ROOT / "src" / "api" / "routers").glob("*.py")):
        try:
            tree = ast.parse(router.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue

        # A router may define a local get_text wrapper that pins a namespace
        # (e.g. learning.py resolves in "pages/learning").
        wrapper_namespace: str | None = None
        for node in ast.walk(tree):
            if not (isinstance(node, ast.FunctionDef) and node.name == "get_text"):
                continue
            for child in ast.walk(node):
                if (
                    isinstance(child, ast.Call)
                    and isinstance(child.func, ast.Name)
                    and child.func.id == "get_shared_text"
                ):
                    for kw in child.keywords:
                        if kw.arg == "namespace" and isinstance(kw.value, ast.Constant):
                            wrapper_namespace = kw.value.value

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else (
                func.attr if isinstance(func, ast.Attribute) else None
            )
            if name not in ("get_text", "get_shared_text"):
                continue

            namespace = "common"
            key: str | None = None
            for kw in node.keywords:
                if kw.arg == "key" and isinstance(kw.value, ast.Constant):
                    key = kw.value.value
                if kw.arg == "namespace" and isinstance(kw.value, ast.Constant):
                    namespace = kw.value.value
            if key is None:
                # Positional form: get_text(user, "errors.someKey") / the
                # shared variant keeps (user, key) as its first two args too.
                positional = [
                    a.value
                    for a in node.args
                    if isinstance(a, ast.Constant) and isinstance(a.value, str)
                ]
                key = positional[1] if len(positional) >= 2 else None
            if name == "get_text" and wrapper_namespace is not None:
                namespace = wrapper_namespace
            if not key or not namespace:
                continue

            if any(
                _resolve(_load_locale(lang, namespace), key) is not None
                for lang in ("es", "en")
            ):
                continue
            errors.append(
                f"{router.name} :: ns={namespace} key={key}"
            )
    return errors


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

    missing_backend = _check_backend_keys_resolve()

    if dead:
        print(f"Found {len(dead)} unreferenced translation keys:")
        for entry in dead:
            print(f"  {entry}")
    if missing_backend:
        print(f"Found {len(missing_backend)} backend get_text keys that do not resolve:")
        for entry in missing_backend:
            print(f"  {entry}")
    if dead or missing_backend:
        return 1

    print("i18n keys OK: every Spanish translation key is referenced in source "
          "and every backend get_text key resolves in the locale files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
