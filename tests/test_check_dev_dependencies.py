"""Regression tests for the development-dependency checker CLI."""

from __future__ import annotations

import pytest

from scripts import check_dev_dependencies


def test_help_exits_before_dependency_scan(monkeypatch, capsys):
    """The help path is informational and must not run the dependency scan."""
    monkeypatch.setattr(
        check_dev_dependencies,
        "missing_development_distributions",
        lambda: pytest.fail("dependency scan ran during --help"),
    )

    with pytest.raises(SystemExit) as exc_info:
        check_dev_dependencies.main(["--help"])

    assert exc_info.value.code == 0
    assert "Check whether every dependency" in capsys.readouterr().out


def test_no_argument_path_still_scans_dependencies(monkeypatch):
    """The launcher-compatible no-argument command retains its scan behavior."""
    monkeypatch.setattr(
        check_dev_dependencies,
        "missing_development_distributions",
        lambda: [],
    )

    assert check_dev_dependencies.main([]) == 0
