"""Cheap optional-module availability checks without importing them."""

from __future__ import annotations

import importlib.util


def module_available(module_name: str) -> bool:
    """Return whether an optional module exists without importing it."""
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False
