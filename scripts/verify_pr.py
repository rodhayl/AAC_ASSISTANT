"""Lightweight maintainer verification script for pull requests.

Runs the complete local test, lint, compilation, typecheck, coverage, and
link-validation checks before submitting or merging a PR.

Usage:
    uv run python scripts/verify_pr.py
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


def run_step(name: str, cmd: list[str], cwd: Path | None = None) -> bool:
    print(f"\n[RUNNING] {name}...")
    print(f"$ {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=str(cwd) if cwd else None)
    if res.returncode != 0:
        print(f"[FAILED] {name} exited with code {res.returncode}")
        return False
    print(f"[PASSED] {name}")
    return True


def check_markdown_links(root: Path) -> bool:
    print("\n[RUNNING] Checking Markdown links...")
    md_files = list(root.glob("*.md")) + list(root.glob("docs/**/*.md")) + list(root.glob(".github/**/*.md"))
    errors = []

    for md_file in md_files:
        content = md_file.read_text(encoding="utf-8")
        links = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", content)
        for text, target in links:
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            clean_target = target.split("#")[0]
            if not clean_target:
                continue
            resolved = (md_file.parent / clean_target).resolve()
            if not resolved.exists():
                errors.append(f"Broken link in {md_file}: [{text}]({target}) -> {resolved}")

    if errors:
        print(f"[FAILED] Found {len(errors)} broken links:")
        for err in errors:
            print("  -", err)
        return False

    print(f"[PASSED] Scanned {len(md_files)} markdown files with 0 broken links.")
    return True


def check_requirements_consistency(root: Path) -> bool:
    print("\n[RUNNING] Checking requirements.txt consistency with uv.lock...")
    req_file = root / "requirements.txt"
    if not req_file.exists():
        print("[FAILED] requirements.txt does not exist.")
        return False

    res = subprocess.run(
        ["uv", "export", "--format", "requirements-txt", "--no-dev", "--quiet"],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        print(f"[FAILED] uv export failed: {res.stderr}")
        return False

    def normalize(text: str) -> list[str]:
        return [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith("#")]

    expected = normalize(res.stdout)
    actual = normalize(req_file.read_text(encoding="utf-8"))
    if expected != actual:
        print("[FAILED] requirements.txt is out of sync with uv.lock.")
        print("Run: uv export --format requirements-txt --no-dev --output-file requirements.txt")
        return False

    print("[PASSED] requirements.txt is consistent with uv.lock.")
    return True


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    frontend_dir = root / "src" / "frontend"

    steps = [
        ("Backend Ruff Linter", ["uv", "run", "ruff", "check", "src", "tests", "scripts"], root),
        ("Backend Compileall", ["uv", "run", "python", "-m", "compileall", "-q", "src", "scripts"], root),
        ("Backend Pytest & Coverage", ["uv", "run", "pytest", "--cov=src", "--cov-report=term-missing:skip-covered", "--cov-branch", "-q"], root),
        ("Frontend TypeScript Typecheck", ["npm", "run", "typecheck"], frontend_dir),
        ("Frontend ESLint", ["npm", "run", "lint"], frontend_dir),
        ("Frontend Vitest & Coverage", ["npm", "run", "test", "--", "--run", "--coverage"], frontend_dir),
        ("Frontend Production Build", ["npm", "run", "build"], frontend_dir),
    ]

    for name, cmd, cwd in steps:
        if not run_step(name, cmd, cwd):
            return 1

    if not check_requirements_consistency(root):
        return 1

    if not check_markdown_links(root):
        return 1

    print("\n==================================================")
    print("ALL MAINTAINER VERIFICATION CHECKS PASSED!")
    print("==================================================")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
