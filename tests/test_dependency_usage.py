"""Regression tests for the direct-dependency evidence audit."""

from __future__ import annotations

import json

from scripts.check_dependency_usage import EvidenceRule, _has_evidence, check_dependency_usage


def test_current_dependency_manifests_have_scoped_evidence() -> None:
    assert check_dependency_usage() == []


def test_unreviewed_python_dependency_is_rejected(tmp_path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
dependencies = ["unused-library==1.0"]
[project.optional-dependencies]
voice = []
[dependency-groups]
dev = []
""",
        encoding="utf-8",
    )
    (tmp_path / "src" / "frontend").mkdir(parents=True)
    (tmp_path / "src" / "frontend" / "package.json").write_text(
        json.dumps({"dependencies": {}, "devDependencies": {}, "scripts": {}}),
        encoding="utf-8",
    )

    errors = check_dependency_usage(tmp_path)

    assert errors == ["Python runtime dependency 'unused-library' has no evidence rule"]


def test_evidence_is_limited_to_declared_paths(tmp_path) -> None:
    (tmp_path / "allowed.py").write_text("import reviewed_package\n", encoding="utf-8")
    (tmp_path / "tests.py").write_text("import reviewed_package\n", encoding="utf-8")
    rule = EvidenceRule((r"^import reviewed_package$",), ("allowed.py",))

    assert _has_evidence(tmp_path, rule)
    assert not _has_evidence(tmp_path, EvidenceRule(rule.patterns, ("missing.py",)))


def test_runtime_dependency_used_only_by_tests_is_rejected(tmp_path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
dependencies = ["fastapi==1.0"]
[project.optional-dependencies]
voice = []
[dependency-groups]
dev = []
""",
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_only.py").write_text(
        "from fastapi import FastAPI\n",
        encoding="utf-8",
    )
    (tmp_path / "src" / "frontend").mkdir(parents=True)
    (tmp_path / "src" / "frontend" / "package.json").write_text(
        json.dumps({"dependencies": {}, "devDependencies": {}, "scripts": {}}),
        encoding="utf-8",
    )

    errors = check_dependency_usage(tmp_path)

    assert errors == ["Python runtime dependency 'fastapi' has no evidence in its allowed scope"]


def test_frontend_runtime_dependency_used_only_by_tests_is_rejected(tmp_path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
dependencies = []
[project.optional-dependencies]
voice = []
[dependency-groups]
dev = []
""",
        encoding="utf-8",
    )
    frontend = tmp_path / "src" / "frontend"
    (frontend / "tests").mkdir(parents=True)
    (frontend / "tests" / "only-test.ts").write_text(
        "import axios from 'axios'\n",
        encoding="utf-8",
    )
    (frontend / "package.json").write_text(
        json.dumps({"dependencies": {"axios": "^1.0.0"}, "devDependencies": {}, "scripts": {}}),
        encoding="utf-8",
    )

    errors = check_dependency_usage(tmp_path)

    assert errors == ["Frontend runtime dependency 'axios' has no evidence in its allowed scope"]


def test_build_only_frontend_package_cannot_be_runtime_dependency(tmp_path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
dependencies = []
[project.optional-dependencies]
voice = []
[dependency-groups]
dev = []
""",
        encoding="utf-8",
    )
    frontend = tmp_path / "src" / "frontend"
    (frontend / "src").mkdir(parents=True)
    (frontend / "src" / "index.css").write_text(
        '@import "shadcn/tailwind.css";\n',
        encoding="utf-8",
    )
    (frontend / "package.json").write_text(
        json.dumps({"dependencies": {"shadcn": "^4.19.0"}, "devDependencies": {}, "scripts": {}}),
        encoding="utf-8",
    )

    errors = check_dependency_usage(tmp_path)

    assert errors == ["Frontend runtime dependency 'shadcn' has no evidence rule"]
