import ast
import os
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

# Configuration
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
EXCLUDES = {"__pycache__", ".git", ".pytest_cache", "node_modules", "dist", "frontend"}

class SymbolVisitor(ast.NodeVisitor):
    def __init__(self):
        self.defined_symbols = set()
        self.imported_symbols = set()

    def visit_ClassDef(self, node):
        self.defined_symbols.add(node.name)
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        self.defined_symbols.add(node.name)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node):
        self.defined_symbols.add(node.name)
        self.generic_visit(node)

    def visit_Assign(self, node):
        # Capture global variables/constants
        for target in node.targets:
            if isinstance(target, ast.Name):
                self.defined_symbols.add(target.id)
        self.generic_visit(node)

    def visit_Import(self, node):
        for alias in node.names:
            name = alias.asname or alias.name.split('.')[0]
            self.defined_symbols.add(name)

    def visit_ImportFrom(self, node):
        for alias in node.names:
            name = alias.asname or alias.name
            self.defined_symbols.add(name)

def get_module_symbols(file_path: Path) -> Set[str]:
    """Parse a file and return all globally defined symbols (classes, functions, vars)."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(file_path))
        visitor = SymbolVisitor()
        visitor.visit(tree)
        return visitor.defined_symbols
    except Exception as e:
        print(f"⚠️  Error parsing {file_path}: {e}")
        return set()

def resolve_import_path(module_path: str) -> Path:
    """Convert dotted python path (src.foo.bar) to file path."""
    # Handle 'src.' prefix
    parts = module_path.split(".")
    current = PROJECT_ROOT
    for part in parts:
        current = current / part
    
    # Try .py
    if current.with_suffix(".py").exists():
        return current.with_suffix(".py")
    
    # Try package (__init__.py)
    if (current / "__init__.py").exists():
        return current / "__init__.py"
    
    return None

def audit_codebase():
    print(f"Starting Deep Codebase Audit...")
    print(f"Root: {PROJECT_ROOT}")
    
    errors = []
    
    for file_path in SRC_DIR.rglob("*.py"):
        rel_path = file_path.relative_to(PROJECT_ROOT)
        
        # Skip excluded dirs
        if any(part in EXCLUDES for part in rel_path.parts):
            continue

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=str(file_path))
        except Exception as e:
            errors.append(f"Syntax Error in {rel_path}: {e}")
            continue

        # Check imports
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module
                if not module:
                    continue
                
                # We only care about internal imports starting with 'src'
                if not module.startswith("src"):
                    continue

                # 1. Verify Module Exists
                target_file = resolve_import_path(module)
                if not target_file:
                    errors.append(f"{rel_path}:{node.lineno} - Module not found: '{module}'")
                    continue

                # 2. Verify Symbols Exist in Module
                target_symbols = get_module_symbols(target_file)
                
                for alias in node.names:
                    symbol = alias.name
                    if symbol == "*":
                        continue # Can't statically verify * imports easily
                    
                    if symbol not in target_symbols:
                        # Check if it's imported in the target file (re-export)
                        # This is a limitation of this simple script, but good enough for now
                        # To be safe, we mainly look for definitions. 
                        # If a file imports X and re-exports it, checking definitions fails.
                        # Relaxing rule: warn only? Or try to be smarter?
                        # For database.py, we define everything.
                        
                        # Special Case: sqlalchemy relationships or dymanic things
                        # Let's flag it, verification will confirm.
                         errors.append(f"{rel_path}:{node.lineno} - Symbol '{symbol}' not found in '{module}' (Target: {target_file.name})")

    if errors:
        print("\nAudit Found Issues:")
        for err in errors:
            print(err)
        print(f"\nFound {len(errors)} issues.")
        sys.exit(1)
    else:
        print("\nCodebase Audit Passed: No broken internal imports found.")
        sys.exit(0)

if __name__ == "__main__":
    audit_codebase()
