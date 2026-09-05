"""Regression tests: scripts/smoke_live.py never carries credential literals.

The repository is secret-scanned over full history (``.gitleaks.toml``
allowlists only the documented demo credentials ``Admin123``/``Student123``/
``Teacher123`` and only inside a fixed set of files). ``smoke_live.py`` boots a
throwaway production server whose bootstrap requires a strong
``AAC_BOOTSTRAP_ADMIN_PASSWORD``; that value must be generated at runtime
(``secrets.token_urlsafe``), never checked in as a literal.

These tests pin that contract after a 22-character production-password literal
was removed from the degraded-server environment in the file.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SMOKE_LIVE = REPO_ROOT / "scripts" / "smoke_live.py"

# Documented development/test credentials (AGENTS.md secrets audit; also the
# only allowlisted credential set in .gitleaks.toml).
DOCUMENTED_DEMO_CREDENTIALS = {"Admin123", "Student123", "Teacher123"}


def _string_constant(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _password_keyed_literal_values(tree: ast.Module, key: str) -> list[str]:
    """Return string-literal values stored under a given (case-sensitive) dict key."""
    literals: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key_node, value_node in zip(node.keys, node.values, strict=True):
            if _string_constant(key_node) == key:
                value = _string_constant(value_node)
                if value is not None:
                    literals.append(value)
    return literals


def _password_keyed_literals(tree: ast.Module) -> list[str]:
    """Return string literals used as password values in dict literals."""
    literals: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key_node, value_node in zip(node.keys, node.values, strict=True):
            key = _string_constant(key_node)
            if key is not None and "PASSWORD" in key.upper():
                value = _string_constant(value_node)
                if value is not None:
                    literals.append(value)
    return literals


def _password_named_constant_literals(tree: ast.Module) -> list[str]:
    """Return string literals initializing module constants named like a password."""
    literals: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and "PASSWORD" in target.id.upper():
                value = _string_constant(node.value)
                if value is not None:
                    literals.append(value)
    return literals


def test_bootstrap_admin_password_is_generated_at_runtime() -> None:
    """``AAC_BOOTSTRAP_ADMIN_PASSWORD`` values must be runtime expressions.

    The degraded server env sets this key to a value generated per run with
    ``secrets.token_urlsafe``. Re-introducing a checked-in literal here would
    be a secret-scan finding, exactly like the removed
    ``Smoke#Prod!2026-Admin`` was.
    """
    tree = ast.parse(SMOKE_LIVE.read_text(encoding="utf-8"), filename=str(SMOKE_LIVE))
    literals = _password_keyed_literal_values(tree, "AAC_BOOTSTRAP_ADMIN_PASSWORD")
    assert literals == [], (
        f"AAC_BOOTSTRAP_ADMIN_PASSWORD must be generated at runtime, found "
        f"literal(s): {literals}"
    )


def test_password_literals_are_only_documented_demo_credentials() -> None:
    """Every literal password in the file is a documented demo credential.

    The throwaway smoke database is bootstrapped and logged into with the
    documented demo credentials (allowlisted for secret scans). Any other
    literal under a password key or assigned to a password-named constant
    must be rejected so the file never re-introduces a real secret.
    """
    tree = ast.parse(SMOKE_LIVE.read_text(encoding="utf-8"), filename=str(SMOKE_LIVE))
    literals = _password_keyed_literals(tree) + _password_named_constant_literals(tree)
    assert literals, "expected documented demo credential literals to be found"
    assert set(literals) <= DOCUMENTED_DEMO_CREDENTIALS, (
        f"credential literal(s) in {SMOKE_LIVE.name} beyond the documented demo "
        f"credentials {sorted(DOCUMENTED_DEMO_CREDENTIALS)}: {sorted(set(literals))}"
    )
