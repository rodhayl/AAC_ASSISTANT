"""Focused tests for the internal-import audit script."""

import ast
import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_audit():
    spec = importlib.util.spec_from_file_location(
        "audit_codebase_under_test", REPO_ROOT / "scripts" / "audit_codebase.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def audit():
    return _load_audit()


def test_resolve_import_path_finds_module_and_package(audit):
    module_file = audit.resolve_import_path("src.aac_app.db")
    assert module_file is not None
    assert module_file.name == "db.py"

    package_file = audit.resolve_import_path("src.aac_app")
    assert package_file is not None
    assert package_file.name == "__init__.py"

    assert audit.resolve_import_path("src.missing_package.zzz") is None


def test_module_path_for_file_strips_file_component(audit, tmp_path):
    with open(tmp_path / "symbol.py", "w", encoding="utf-8"):
        pass
    # The helper resolves against the real repo SRC_DIR, so craft paths under
    # the real tree instead of an isolated tmp tree.
    real = audit.SRC_DIR / "aac_app" / "models" / "symbol.py"
    assert audit._module_path_for_file(real) == ("src", "aac_app", "models")
    init = audit.SRC_DIR / "aac_app" / "models" / "__init__.py"
    assert audit._module_path_for_file(init) == ("src", "aac_app", "models")


def test_import_target_module_resolves_relative_levels(audit):
    symbol = audit.SRC_DIR / "aac_app" / "models" / "symbol.py"
    service = audit.SRC_DIR / "aac_app" / "services" / "prediction_service.py"

    node = ast.parse("from ..db import get_session\n").body[0]
    assert audit._import_target_module(symbol, node, []) == "src.aac_app.db"

    node = ast.parse("from . import auth\n").body[0]
    deps_init = audit.SRC_DIR / "api" / "deps" / "__init__.py"
    assert audit._import_target_module(deps_init, node, []) == "src.api.deps.auth"

    node = ast.parse("from ..services.runtime_translation import x\n").body[0]
    assert (
        audit._import_target_module(service, node, [])
        == "src.aac_app.services.runtime_translation"
    )

    # ``from ... import config`` binds the ``src.config`` module itself.
    provider = audit.SRC_DIR / "aac_app" / "providers" / "model_download.py"
    node = ast.parse("from ... import config\n").body[0]
    assert audit._import_target_module(provider, node, []) == "src.config"


def test_is_submodule_accepts_child_modules_and_self_imports(audit):
    assert audit._is_submodule("src.api", "deps")
    assert audit._is_submodule("src.api.routers", "admin")
    assert audit._is_submodule("src", "config")
    assert not audit._is_submodule("src.api.routers", "does_not_exist")


def test_constant_string_folds_additions(audit):
    assert audit._constant_string(ast.Constant(value="oauth2_")) == "oauth2_"
    expr = ast.parse("'oauth2_' + 'scheme'", mode="eval").body
    assert audit._constant_string(expr) == "oauth2_scheme"


def test_audit_detects_missing_relative_module(audit, monkeypatch, tmp_path):
    tree = tmp_path / "src"
    (tree / "pkg").mkdir(parents=True)
    (tree / "pkg" / "__init__.py").write_text("from . import ghost\n", encoding="utf-8")
    (tree / "pkg" / "thing.py").write_text("VALUE = 1\n", encoding="utf-8")

    monkeypatch.setattr(audit, "SRC_DIR", tree)
    monkeypatch.setattr(audit, "PROJECT_ROOT", tmp_path)

    assert audit.audit_codebase() == 1


def test_audit_detects_missing_symbol(audit, monkeypatch, tmp_path):
    tree = tmp_path / "src"
    (tree / "pkg").mkdir(parents=True)
    (tree / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tree / "pkg" / "mod.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tree / "pkg" / "consumer.py").write_text(
        "from src.pkg.mod import MISSING\n", encoding="utf-8"
    )

    monkeypatch.setattr(audit, "SRC_DIR", tree)
    monkeypatch.setattr(audit, "PROJECT_ROOT", tmp_path)

    assert audit.audit_codebase() == 1


def test_audit_passes_clean_tree(audit, monkeypatch, tmp_path):
    tree = tmp_path / "src"
    (tree / "pkg").mkdir(parents=True)
    (tree / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tree / "pkg" / "mod.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tree / "pkg" / "consumer.py").write_text(
        "from src.pkg.mod import VALUE\n", encoding="utf-8"
    )

    monkeypatch.setattr(audit, "SRC_DIR", tree)
    monkeypatch.setattr(audit, "PROJECT_ROOT", tmp_path)

    assert audit.audit_codebase() == 0


def test_audit_accepts_dynamic_globals_definition(audit, monkeypatch, tmp_path):
    tree = tmp_path / "src"
    (tree / "pkg").mkdir(parents=True)
    (tree / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tree / "pkg" / "mod.py").write_text(
        "globals()['oauth2_' + 'scheme'] = object()\n", encoding="utf-8"
    )
    (tree / "pkg" / "consumer.py").write_text(
        "from src.pkg.mod import oauth2_scheme\n", encoding="utf-8"
    )

    monkeypatch.setattr(audit, "SRC_DIR", tree)
    monkeypatch.setattr(audit, "PROJECT_ROOT", tmp_path)

    assert audit.audit_codebase() == 0
