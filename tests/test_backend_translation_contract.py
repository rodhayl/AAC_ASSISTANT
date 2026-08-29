"""Focused backend translation namespace contract checks."""

from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
LOCALES = ROOT / "src" / "frontend" / "src" / "locales"


def _leaf_keys(value, prefix="") -> set[str]:
    if not isinstance(value, dict):
        return {prefix}
    keys: set[str] = set()
    for name, child in value.items():
        child_prefix = f"{prefix}.{name}" if prefix else name
        keys.update(_leaf_keys(child, child_prefix))
    return keys


def _locale_keys(language: str, namespace: str) -> set[str]:
    path = LOCALES / language / f"{namespace}.json"
    return _leaf_keys(json.loads(path.read_text(encoding="utf-8")))


def test_learning_session_default_namespace_and_keys_exist():
    source = (ROOT / "src/api/deps/access.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    namespace_nodes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and node.value == "pages/learning"
    ]
    assert namespace_nodes, "learning-session default must name pages/learning"

    keys = _locale_keys("en", "pages/learning") & _locale_keys("es", "pages/learning")
    assert {"errors.sessionNotFound", "errors.unauthorized", "errors.sessionNotActive"} <= keys


def test_learning_router_wrapper_uses_learning_namespace():
    source = (ROOT / "src/api/routers/learning.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    wrapper = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "get_text"
    )
    assert any(
        isinstance(node, ast.Constant) and node.value == "pages/learning"
        for node in ast.walk(wrapper)
    )
    keys = _locale_keys("en", "pages/learning") & _locale_keys("es", "pages/learning")
    assert {"errors.unauthorizedUser", "errors.unknownError", "errors.noSymbolsProvided"} <= keys
