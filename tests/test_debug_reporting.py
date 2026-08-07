from src.api import debug_reporting


def test_debug_reporting_is_opt_in(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("AAC_DEBUG_REPORTS", raising=False)
    assert debug_reporting._enabled() is False

    monkeypatch.setenv("AAC_DEBUG_REPORTS", "true")
    assert debug_reporting._enabled() is True


def test_debug_reporting_is_disabled_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("AAC_DEBUG_REPORTS", "true")
    assert debug_reporting._enabled() is False


def test_debug_reporting_allows_nonproduction_diagnostics(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("AAC_DEBUG_REPORTS", "1")
    assert debug_reporting._enabled() is True
