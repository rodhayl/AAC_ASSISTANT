"""Enforce evidence and scope for direct project dependencies.

This is deliberately a small, static guard rather than a replacement for a
package manager.  It catches the common failure mode where an agent adds a
library to a runtime manifest only for tests, or adds a direct package without
using it at all.  New packages must receive an explicit evidence rule here,
which makes the reason and scope reviewable in the same change.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class EvidenceRule:
    """Patterns and repository paths that demonstrate a dependency is needed."""

    patterns: tuple[str, ...]
    paths: tuple[str, ...]


_REQUIREMENT_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def _normalize_name(name: str) -> str:
    """Normalize a Python distribution name according to PEP 503."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _requirement_name(requirement: str) -> str | None:
    match = _REQUIREMENT_NAME.match(requirement)
    return _normalize_name(match.group(1)) if match else None


def _python_runtime_rules() -> dict[str, EvidenceRule]:
    """Return reviewed evidence rules for runtime and optional Python packages."""
    # Operator scripts are part of the supported production surface; tests are
    # intentionally excluded so test-only imports cannot justify runtime deps.
    source = ("src/**/*.py", "scripts/**/*.py")
    return {
        "fastapi": EvidenceRule((r"^\s*(?:from|import)\s+fastapi\b",), source),
        "uvicorn": EvidenceRule((r"^\s*(?:from|import)\s+uvicorn\b",), source),
        "sqlalchemy": EvidenceRule((r"^\s*from\s+sqlalchemy\b",), source),
        "pydantic": EvidenceRule((r"^\s*from\s+pydantic\b",), source),
        "pydantic-settings": EvidenceRule(
            (r"^\s*from\s+pydantic_settings\b",), source
        ),
        "pyjwt": EvidenceRule((r"^\s*(?:from|import)\s+jwt\b",), source),
        "pwdlib": EvidenceRule((r"^\s*(?:from|import)\s+pwdlib\b",), source),
        "httpx": EvidenceRule((r"^\s*(?:from|import)\s+httpx\b",), source),
        # FastAPI loads python-multipart when these multipart parameters are used.
        "python-multipart": EvidenceRule(
            (r"\b(?:File|Form|UploadFile)\b",), ("src/api/**/*.py",)
        ),
        "slowapi": EvidenceRule((r"^\s*(?:from|import)\s+slowapi\b",), source),
        "loguru": EvidenceRule((r"^\s*(?:from|import)\s+loguru\b",), source),
        "pillow": EvidenceRule((r"^\s*from\s+PIL\b",), source),
        "pyyaml": EvidenceRule((r"^\s*(?:from|import)\s+yaml\b",), source),
        # Pydantic's EmailStr delegates validation to email-validator.
        "email-validator": EvidenceRule((r"\bEmailStr\b",), ("src/**/*.py",)),
        "numpy": EvidenceRule((r"^\s*(?:from|import)\s+numpy\b",), source),
        "fastembed": EvidenceRule((r"^\s*(?:from|import)\s+fastembed\b",), source),
        "sqlite-vec": EvidenceRule(
            (r"^\s*(?:from|import)\s+sqlite_vec\b",), source
        ),
        "bcrypt": EvidenceRule((r"^\s*(?:from|import)\s+bcrypt\b",), source),
        # Uvicorn's WebSocket transport loads this optional protocol package.
        "websockets": EvidenceRule((r"\bWebSocket\b",), ("src/api/routers/collab.py",)),
        "drawsvg": EvidenceRule((r"^\s*(?:from|import)\s+drawsvg\b",), source),
        "resvg-py": EvidenceRule((r"^\s*(?:from|import)\s+resvg_py\b",), source),
        "faster-whisper": EvidenceRule(
            (r"^\s*(?:from|import)\s+faster_whisper\b",), source
        ),
        "kokoro-onnx": EvidenceRule(
            (r"^\s*(?:from|import)\s+kokoro_onnx\b",), source
        ),
    }


def _python_tool_rules() -> dict[str, EvidenceRule]:
    """Return reviewed evidence rules for Python development tools."""
    ci = (".github/workflows/*.yml", ".github/workflows/*.yaml")
    return {
        "pytest": EvidenceRule((r"\bpytest\b",), ("tests/**/*.py", *ci)),
        "pytest-cov": EvidenceRule((r"(?:--cov(?:=|\b)|pytest-cov)",), ci),
        "ruff": EvidenceRule((r"\bruff\s+check\b",), ci),
        "pyinstaller": EvidenceRule(
            (r"\bpyinstaller\b|AAC_Assistant\.spec",),
            ("build_package.bat", "AAC_Assistant.spec", *ci),
        ),
        "pip-audit": EvidenceRule((r"\bpip-audit\b",), ci),
    }


def _frontend_runtime_rules() -> dict[str, EvidenceRule]:
    """Return reviewed evidence rules for browser runtime dependencies."""
    source = ("src/**/*",)
    return {
        "@base-ui/react": EvidenceRule((r"['\"]@base-ui/react/",), source),
        "@dnd-kit/core": EvidenceRule((r"['\"]@dnd-kit/core['\"]",), source),
        "@dnd-kit/sortable": EvidenceRule((r"['\"]@dnd-kit/sortable['\"]",), source),
        "@dnd-kit/utilities": EvidenceRule((r"['\"]@dnd-kit/utilities['\"]",), source),
        "axios": EvidenceRule((r"['\"]axios['\"]",), source),
        "class-variance-authority": EvidenceRule(
            (r"['\"]class-variance-authority['\"]",), source
        ),
        "clsx": EvidenceRule((r"['\"]clsx['\"]",), source),
        "i18next": EvidenceRule((r"['\"]i18next['\"]",), source),
        "i18next-browser-languagedetector": EvidenceRule(
            (r"['\"]i18next-browser-languagedetector['\"]",), source
        ),
        "lucide-react": EvidenceRule((r"['\"]lucide-react['\"]",), source),
        "react": EvidenceRule((r"['\"]react['\"]",), source),
        "react-dom": EvidenceRule((r"['\"]react-dom(?:/[^'\"]*)?['\"]",), source),
        "react-i18next": EvidenceRule((r"['\"]react-i18next['\"]",), source),
        "react-router": EvidenceRule((r"['\"]react-router(?:/[^'\"]*)?['\"]",), source),
        "sonner": EvidenceRule((r"['\"]sonner(?:/[^'\"]*)?['\"]",), source),
        "tailwind-merge": EvidenceRule((r"['\"]tailwind-merge['\"]",), source),
        "zustand": EvidenceRule((r"['\"]zustand['\"]",), source),
    }


def _frontend_tool_rules() -> dict[str, EvidenceRule]:
    """Return reviewed evidence rules for frontend build, test, and lint tools."""
    config = (
        "*.config.*",
        "tsconfig*.json",
        "vitest.setup.ts",
        "playwright.verify.config.ts",
        "tests/**/*",
        "e2e/**/*",
        "scripts/**/*",
    )
    return {
        "@axe-core/playwright": EvidenceRule((r"['\"]@axe-core/playwright['\"]",), config),
        "@eslint/js": EvidenceRule((r"['\"]@eslint/js['\"]",), ("eslint.config.js",)),
        "@playwright/test": EvidenceRule((r"['\"]@playwright/test['\"]",), config),
        "@tailwindcss/vite": EvidenceRule(
            (r"['\"]@tailwindcss/vite['\"]",), ("vite.config.ts",)
        ),
        "@testing-library/jest-dom": EvidenceRule(
            (r"['\"]@testing-library/jest-dom['\"]",), ("tests/**/*", "vitest.setup.ts")
        ),
        "@testing-library/react": EvidenceRule(
            (r"['\"]@testing-library/react['\"]",), ("tests/**/*",)
        ),
        "@testing-library/user-event": EvidenceRule(
            (r"['\"]@testing-library/user-event['\"]",), ("tests/**/*",)
        ),
        "@types/node": EvidenceRule((r"['\"]types['\"]\s*:\s*\[\s*['\"]node",), ("tsconfig.node.json",)),
        "@types/react": EvidenceRule((r"['\"]jsx['\"]\s*:",), ("tsconfig.app.json",)),
        "@types/react-dom": EvidenceRule((r"react-dom",), ("src/**/*", "tsconfig.app.json")),
        "@vitejs/plugin-react": EvidenceRule(
            (r"['\"]@vitejs/plugin-react['\"]",), ("vite.config.ts", "vitest.config.ts")
        ),
        "@vitest/coverage-v8": EvidenceRule(
            (r"provider\s*:\s*['\"]v8['\"]|--coverage",),
            ("vitest.config.ts", ".github/workflows/*.yml", ".github/workflows/*.yaml"),
        ),
        "shadcn": EvidenceRule((r"@import\s+['\"]shadcn/",), ("src/index.css",)),
        "tw-animate-css": EvidenceRule(
            (r"@import\s+['\"]tw-animate-css['\"]",), ("src/index.css",)
        ),
        "eslint": EvidenceRule((r"['\"]eslint/config['\"]|\beslint\s+\.",), config),
        "eslint-plugin-react-hooks": EvidenceRule(
            (r"['\"]eslint-plugin-react-hooks['\"]",), ("eslint.config.js",)
        ),
        "eslint-plugin-react-refresh": EvidenceRule(
            (r"['\"]eslint-plugin-react-refresh['\"]",), ("eslint.config.js",)
        ),
        "globals": EvidenceRule((r"['\"]globals['\"]",), ("eslint.config.js",)),
        "globby": EvidenceRule((r"['\"]globby['\"]",), ("scripts/**/*",)),
        "jsdom": EvidenceRule((r"environment\s*:\s*['\"]jsdom['\"]",), ("vitest.config.ts",)),
        "tailwindcss": EvidenceRule(
            (r"@import\s+['\"]tailwindcss['\"]|tailwindcss\(\)",),
            ("src/index.css", "vite.config.ts"),
        ),
        "typescript": EvidenceRule((r"\btsc\s+-b\b",), ("package.json", "*.config.*")),
        "typescript-eslint": EvidenceRule(
            (r"['\"]typescript-eslint['\"]",), ("eslint.config.js",)
        ),
        "vite": EvidenceRule(
            (r"['\"]vite['\"]|\bvite\s+(?:build|preview|dev)\b",),
            config + ("package.json",),
        ),
        "vitest": EvidenceRule(
            (r"['\"]vitest(?:/config)?['\"]|\bvitest\s+run\b",),
            config + ("package.json",),
        ),
    }


def _files_for_patterns(root: Path, patterns: tuple[str, ...]) -> list[Path]:
    """Return unique, readable files for a set of repository-relative globs."""
    files: set[Path] = set()
    for pattern in patterns:
        candidate = root / pattern
        if candidate.is_file():
            files.add(candidate)
        else:
            files.update(path for path in root.glob(pattern) if path.is_file())
    return sorted(files)


def _read_evidence_text(root: Path, rule: EvidenceRule, *, package_json_scripts: str = "") -> str:
    text_parts = [package_json_scripts]
    for path in _files_for_patterns(root, rule.paths):
        try:
            text_parts.append(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
    return "\n".join(text_parts)


def _has_evidence(root: Path, rule: EvidenceRule, *, package_json_scripts: str = "") -> bool:
    text = _read_evidence_text(root, rule, package_json_scripts=package_json_scripts)
    return any(re.search(pattern, text, flags=re.MULTILINE) for pattern in rule.patterns)


def _python_dependencies(root: Path) -> dict[str, list[str]]:
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    grouped = {
        "runtime": [str(value) for value in project["project"].get("dependencies", [])],
        "optional": [
            str(value)
            for values in project["project"].get("optional-dependencies", {}).values()
            for value in values
        ],
        "dev": [
            str(value)
            for value in project.get("dependency-groups", {}).get("dev", [])
        ],
    }
    names = {
        scope: [name for value in values if (name := _requirement_name(value))]
        for scope, values in grouped.items()
    }
    return names


def _frontend_dependencies(root: Path) -> tuple[dict[str, list[str]], str]:
    package_file = root / "src" / "frontend" / "package.json"
    package = json.loads(package_file.read_text(encoding="utf-8"))
    grouped = {
        "runtime": sorted(package.get("dependencies", {})),
        "dev": sorted(package.get("devDependencies", {})),
    }
    scripts = "\n".join(str(value) for value in package.get("scripts", {}).values())
    return grouped, scripts


def check_dependency_usage(root: Path = PROJECT_ROOT) -> list[str]:
    """Return policy violations for direct dependency declarations."""
    errors: list[str] = []
    python_dependencies = _python_dependencies(root)
    python_rules = {
        "runtime": _python_runtime_rules(),
        "optional": _python_runtime_rules(),
        "dev": _python_tool_rules(),
    }
    for scope, names in python_dependencies.items():
        rules = python_rules[scope]
        for name in names:
            rule = rules.get(name)
            if rule is None:
                errors.append(f"Python {scope} dependency '{name}' has no evidence rule")
            elif not _has_evidence(root, rule):
                errors.append(f"Python {scope} dependency '{name}' has no evidence in its allowed scope")

    frontend_dependencies, scripts = _frontend_dependencies(root)
    frontend_root = root / "src" / "frontend"
    frontend_rules = {
        "runtime": _frontend_runtime_rules(),
        "dev": _frontend_tool_rules(),
    }
    for scope, names in frontend_dependencies.items():
        rules = frontend_rules[scope]
        for name in names:
            rule = rules.get(name)
            if rule is None:
                errors.append(f"Frontend {scope} dependency '{name}' has no evidence rule")
            elif not _has_evidence(frontend_root, rule, package_json_scripts=scripts):
                errors.append(f"Frontend {scope} dependency '{name}' has no evidence in its allowed scope")
    return errors


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    parse_args(argv)
    errors = check_dependency_usage()
    if errors:
        print("Dependency usage audit failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Dependency usage audit passed: all direct dependencies have scoped evidence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
