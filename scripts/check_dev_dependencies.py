"""Check whether every dependency in the project's dev group is installed."""

from __future__ import annotations

import argparse
import importlib.metadata
import re
import sys
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DISTRIBUTION_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def development_distributions() -> list[str]:
    """Return normalized distribution names declared in dependency-groups.dev."""
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as project_file:
        project = tomllib.load(project_file)
    requirements = project.get("dependency-groups", {}).get("dev", [])
    names: list[str] = []
    for requirement in requirements:
        match = _DISTRIBUTION_NAME.match(str(requirement))
        if match:
            names.append(match.group(1))
    return names


def missing_development_distributions() -> list[str]:
    """Return dev distributions unavailable in the interpreter environment."""
    missing: list[str] = []
    for name in development_distributions():
        try:
            importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            missing.append(name)
    return missing


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line options without running the dependency scan."""
    parser = argparse.ArgumentParser(description=__doc__)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Check the development dependency group after parsing CLI options."""
    parse_args(argv)
    missing = missing_development_distributions()
    if missing:
        print("Missing development dependencies: " + ", ".join(missing), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
