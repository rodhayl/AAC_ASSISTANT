from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest


def test_ensure_ok_accepts_successful_json_and_empty_responses():
    from scripts.verify_common import ensure_ok

    assert ensure_ok(SimpleNamespace(status_code=200, content=b'{"ok": true}', json=lambda: {"ok": True}), "read") == {"ok": True}
    assert ensure_ok(SimpleNamespace(status_code=204, content=b"", json=lambda: None), "delete") is None


def test_ensure_ok_rejects_non_2xx(monkeypatch):
    from scripts.verify_common import ensure_ok

    with pytest.raises(SystemExit):
        ensure_ok(SimpleNamespace(status_code=500, content=b"failure", text="failure"), "write")


@pytest.mark.parametrize("module_name", [
    "scripts.verify_fix",
    "scripts.verify_settings",
    "scripts.verify_smartbar",
])
def test_verification_scripts_support_package_import(module_name):
    module = importlib.import_module(module_name)
    assert callable(module.main)
