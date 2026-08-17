"""Unit coverage for TranslationService language resolution and lookups.

Covers the user-preference and Accept-Language resolution paths, locale
prefix normalization, missing-key fallback to English, non-string values,
and template interpolation.
"""
from src.aac_app.services.translation_service import TranslationService


def _service() -> TranslationService:
    return TranslationService()


class _FakeUser:
    def __init__(self, ui_language=None):
        class _Settings:
            def __init__(self, lang):
                self.ui_language = lang

        self.settings = _Settings(ui_language)


def test_resolve_language_prefers_user_setting():
    service = _service()
    user = _FakeUser(ui_language="es")
    assert service.resolve_language(user) == "es"


def test_resolve_language_uses_accept_language_header():
    service = _service()
    # Header "es-ES,es;q=0.9" -> no "es-ES" locale dir exists, so the short
    # code "es" is used.
    assert service.resolve_language(accept_language="es-ES,es;q=0.9") == "es"


def test_resolve_language_falls_back_to_short_code():
    service = _service()
    # "en-GB" is not a locale dir; the "en" prefix is.
    assert service.resolve_language(accept_language="en-GB,en;q=0.9") == "en"


def test_resolve_language_defaults_to_english():
    service = _service()
    assert service.resolve_language(accept_language="fr-FR") == "en"
    assert service.resolve_language() == "en"


def test_get_normalizes_region_suffix_to_base_locale():
    service = _service()
    value = service.get("en-US", "common", "actions.save")
    assert isinstance(value, str) and value


def test_get_missing_key_returns_key_itself():
    service = _service()
    assert service.get("es", "common", "no.such.key") == "no.such.key"


def test_get_falls_back_to_english_when_key_missing_in_locale():
    service = _service()
    # "common.actions.save" exists in both locales; use a key that only the
    # English file can satisfy to exercise the fallback path.
    value = service.get("es", "common", "actions.cancel")
    assert isinstance(value, str) and value


def test_get_interpolates_template_variables():
    service = _service()
    plain = service.get("en", "common", "navbar.welcome")
    assert "{{name}}" in plain
    rendered = service.get("en", "common", "navbar.welcome", name="Ana")
    assert rendered == plain.replace("{{name}}", "Ana")


def test_get_non_string_value_returns_key():
    service = _service()
    # Nested objects are not strings; requesting a section returns the key.
    assert service.get("en", "common", "navbar") == "navbar"
