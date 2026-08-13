from types import SimpleNamespace

from src.api.routers.auth import _build_preferences_response


def test_build_preferences_response_uses_defaults_without_settings():
    response = _build_preferences_response(None)

    assert response.model_dump() == {
        "tts_voice": "default",
        "tts_language": None,
        "ui_language": None,
        "notifications_enabled": True,
        "voice_mode_enabled": True,
        "dark_mode": False,
        "dwell_time": 0,
        "ignore_repeats": 0,
        "high_contrast": False,
    }


def test_build_preferences_response_handles_legacy_and_null_values():
    settings = SimpleNamespace(
        tts_voice=None,
        notifications_enabled=None,
        dark_mode=None,
        dwell_time=None,
        ignore_repeats=None,
        high_contrast=None,
    )

    response = _build_preferences_response(settings)

    assert response.tts_voice == "default"
    assert response.tts_language is None
    assert response.ui_language is None
    assert response.notifications_enabled is True
    assert response.voice_mode_enabled is True
    assert response.dark_mode is False
    assert response.dwell_time == 0
    assert response.ignore_repeats == 0
    assert response.high_contrast is False


def test_build_preferences_response_maps_populated_settings():
    settings = SimpleNamespace(
        tts_voice="female",
        tts_language="es",
        ui_language="es-ES",
        notifications_enabled=False,
        voice_mode_enabled=False,
        dark_mode=True,
        dwell_time=250,
        ignore_repeats=3,
        high_contrast=True,
    )

    response = _build_preferences_response(settings)

    assert response.model_dump() == {
        "tts_voice": "female",
        "tts_language": "es",
        "ui_language": "es-ES",
        "notifications_enabled": False,
        "voice_mode_enabled": False,
        "dark_mode": True,
        "dwell_time": 250,
        "ignore_repeats": 3,
        "high_contrast": True,
    }
