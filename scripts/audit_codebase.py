"""Check that internal Python imports resolve to existing modules and symbols."""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
EXCLUDES = {"__pycache__", ".git", ".pytest_cache", "node_modules", "dist", "frontend"}


class SymbolVisitor(ast.NodeVisitor):
    """Collect names that are available at module scope."""

    def __init__(self) -> None:
        self.defined_symbols: set[str] = set()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.defined_symbols.add(node.name)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.defined_symbols.add(node.name)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.defined_symbols.add(node.name)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if isinstance(target, ast.Name):
                self.defined_symbols.add(target.id)
            elif isinstance(target, ast.Subscript) and isinstance(
                target.value, ast.Call
            ) and isinstance(target.value.func, ast.Name) and target.value.func.id == "globals":
                name = _constant_string(target.slice)
                if name:
                    self.defined_symbols.add(name)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.target, ast.Name):
            self.defined_symbols.add(node.target.id)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.defined_symbols.add(alias.asname or alias.name.split(".")[0])

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            self.defined_symbols.add(alias.asname or alias.name)

    def visit_Call(self, node: ast.Call) -> None:
        # Recognize dynamic definitions such as
        # ``globals()["name"] = value`` (a Subscript on Call) and
        # ``globals().update({"name": value})``. Both are used by security
        # tooling to avoid plaintext scanner hits and still create real
        # module-level names at runtime.
        func = node.func
        is_globals = (
            isinstance(func, ast.Name) and func.id == "globals"
        ) or (
            isinstance(func, ast.Attribute)
            and func.attr == "update"
            and isinstance(func.value, ast.Call)
            and isinstance(func.value.func, ast.Name)
            and func.value.func.id == "globals"
        )
        if not is_globals:
            self.generic_visit(node)
            return
        if isinstance(func, ast.Attribute) and func.attr == "update":
            for arg in node.args:
                if isinstance(arg, ast.Dict):
                    for key in arg.keys:
                        if isinstance(key, ast.Constant) and isinstance(key.value, str):
                            self.defined_symbols.add(key.value)
        self.generic_visit(node)


def get_module_symbols(file_path: Path) -> set[str]:
    """Return defined names plus child-module names for package initializers."""
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    except (OSError, SyntaxError) as exc:
        print(f"Warning: could not parse {file_path}: {exc}")
        return set()

    visitor = SymbolVisitor()
    visitor.visit(tree)
    if file_path.name == "__init__.py":
        for child in file_path.parent.iterdir():
            if child.stem == "__init__":
                continue
            if child.suffix == ".py" or (
                child.is_dir() and (child / "__init__.py").exists()
            ):
                visitor.defined_symbols.add(child.stem)
    return visitor.defined_symbols


def resolve_import_path(module_path: str) -> Path | None:
    """Convert a dotted Python module path to its source file."""
    current = PROJECT_ROOT.joinpath(*module_path.split("."))
    module_file = current.with_suffix(".py")
    if module_file.exists():
        return module_file
    package_file = current / "__init__.py"
    return package_file if package_file.exists() else None


def _is_submodule(module: str, name: str) -> bool:
    """Return whether ``name`` resolves as a module child of ``module``.

    ``from src.api import deps`` binds the ``src.api.deps`` package and
    ``from src.api.routers import admin`` binds the ``admin.py`` sibling; both
    import submodules of the resolved package. ``from src import config`` is
    the special self-import case where the imported name *is* the module
    (``src.config``). Each of these is valid even when the package ``__init__``
    does not re-export the name.
    """
    if name == module.rsplit(".", 1)[-1]:
        # ``from src import config`` binds ``src.config`` itself.
        return True
    return resolve_import_path(f"{module}.{name}") is not None


def _constant_string(node: ast.expr | None) -> str | None:
    """Return a string literal value, concatenating constant additions.

    ``"oauth2_" + "scheme"`` resolves to ``"oauth2_scheme"`` so dynamically
    defined module-level names are auditable.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if (
        isinstance(node, ast.BinOp)
        and isinstance(node.op, ast.Add)
    ):
        left = _constant_string(node.left)
        right = _constant_string(node.right)
        if left is not None and right is not None:
            return left + right
    return None


def _module_path_for_file(file_path: Path) -> tuple[str, ...] | None:
    """Return the dotted path of the package containing a file under ``src``.

    Relative imports are always relative to the *containing package*, so the
    file component (and ``__init__`` markers) are stripped: ``access.py`` in
    ``src/api/deps`` and ``src/api/deps/__init__.py`` both map to
    ``("src", "api", "deps")``.
    """
    try:
        relative = file_path.resolve().relative_to(SRC_DIR.resolve())
    except ValueError:
        return None
    parts = [part for part in relative.parts if part not in {"", "."}]
    if not parts:
        return None
    if parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    # Both the module file itself and ``__init__`` markers are part of the
    # current package directory, never an ancestor package.
    parts = parts[:-1]
    return ("src", *parts)


def _import_target_module(
    file_path: Path, node: ast.ImportFrom, errors: list[str]
) -> str | None:
    """Resolve an absolute or relative internal import to a dotted module path."""
    if node.level == 0:
        if not node.module or not node.module.startswith("src"):
            return None
        return node.module
    package_parts = _module_path_for_file(file_path)
    if package_parts is None:
        errors.append(
            f"{file_path}:{node.lineno} - Cannot resolve relative import outside src"
        )
        return None
    # ``level`` counts leading dots; ``from ..x`` (level 2) walks up one
    # directory from the current package, ``from .x`` (level 1) stays put.
    # Explicit length math avoids the ``[:0]`` empty-slice trap.
    keep = max(len(package_parts) - (node.level - 1), 0)
    parent_parts = list(package_parts[:keep])
    if node.module:
        parent_parts.extend(node.module.split("."))
    else:
        # ``from . import sibling`` has no module part; the imported name is
        # the sibling module to validate.
        parent_parts.extend(node.names[0].name.split("."))
    return ".".join(parent_parts)


def audit_codebase() -> int:
    """Print import problems and return a process exit code."""
    print("Starting Deep Codebase Audit...")
    print(f"Root: {PROJECT_ROOT}")
    errors: list[str] = []

    def check_import(
        file_path: Path,
        node: ast.ImportFrom,
        module: str,
        names: list[ast.alias],
        relative_path: Path,
    ) -> None:
        """Validate one internal import resolves to a module and its symbols."""
        target_file = resolve_import_path(module)
        if target_file is None:
            errors.append(
                f"{relative_path}:{node.lineno} - Module not found: '{module}'"
            )
            return
        target_symbols = get_module_symbols(target_file)
        for alias in names:
            if alias.name == "*":
                continue
            if alias.name in target_symbols:
                continue
            # ``from package import submodule`` binds the module object even
            # when the package does not re-export it, so a direct child module
            # is a valid import target.
            if _is_submodule(module, alias.name):
                continue
            errors.append(
                f"{relative_path}:{node.lineno} - Symbol '{alias.name}' not found "
                f"in '{module}' (target: {target_file.name})"
            )

    for file_path in SRC_DIR.rglob("*.py"):
        relative_path = file_path.relative_to(PROJECT_ROOT)
        if any(part in EXCLUDES for part in relative_path.parts):
            continue
        try:
            tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        except (OSError, SyntaxError) as exc:
            errors.append(f"Syntax error in {relative_path}: {exc}")
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name
                    if not module.startswith("src"):
                        continue
                    target_file = resolve_import_path(module)
                    if target_file is None:
                        errors.append(
                            f"{relative_path}:{node.lineno} - Module not found: '{module}'"
                        )
                continue
            if not isinstance(node, ast.ImportFrom):
                continue
            if node.level > 0:
                module = _import_target_module(file_path, node, errors)
                if module is None:
                    continue
                check_import(file_path, node, module, node.names, relative_path)
                continue
            if not node.module or not node.module.startswith("src"):
                continue
            if node.module == "src":
                # ``from src import config`` resolves through ``src.__init__``,
                # which does not re-export submodules; only verify existence.
                target_file = resolve_import_path(node.module)
                if target_file is None:
                    errors.append(
                        f"{relative_path}:{node.lineno} - Module not found: 'src'"
                    )
                continue
            check_import(file_path, node, node.module, node.names, relative_path)

    if errors:
        print("\nAudit Found Issues:")
        print("\n".join(errors))
        print(f"\nFound {len(errors)} issues.")
        return 1
    print("\nCodebase Audit Passed: No broken internal imports found.")
    return 0


if __name__ == "__main__":
    # ``--help`` must never start the audit scan.
    argparse.ArgumentParser(description=__doc__).parse_args()
    sys.exit(audit_codebase())
