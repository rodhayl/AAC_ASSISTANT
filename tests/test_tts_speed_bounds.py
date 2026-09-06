"""TTS speed bounds live in exactly one backend home (PROMPT_13 D7).

The [0.5, 2.0] range used to be spelled out in the preference schema, the
synthesize endpoint schema, and the legacy-value clamp. All three now import
``TTS_SPEED_MIN``/``TTS_SPEED_MAX`` from src.api.schemas; these tests pin
that agreement including the inclusive endpoints.
"""

from types import SimpleNamespace

from src.api import schemas
from src.api.routers import auth_helpers, providers


def test_speed_bounds_constants_are_the_historical_range():
    assert schemas.TTS_SPEED_MIN == 0.5
    assert schemas.TTS_SPEED_MAX == 2.0


def test_preference_update_schema_uses_the_single_home():
    field = schemas.UserPreferencesUpdate.model_fields["tts_local_speed"]
    ge = [m for m in field.metadata if getattr(m, "ge", None) is not None]
    le = [m for m in field.metadata if getattr(m, "le", None) is not None]
    assert ge and ge[0].ge == schemas.TTS_SPEED_MIN
    assert le and le[0].le == schemas.TTS_SPEED_MAX


def test_synthesize_endpoint_schema_uses_the_single_home():
    schema = providers.TTSSynthesizeRequest.model_json_schema()
    speed = schema["properties"]["speed"]
    assert speed["minimum"] == schemas.TTS_SPEED_MIN
    assert speed["maximum"] == schemas.TTS_SPEED_MAX


def test_legacy_clamp_clamps_to_the_single_home():
    # The clamp lives inside build_preferences_response; a stub settings row
    # with an extreme value exercises the real min/max path.
    low = auth_helpers.build_preferences_response(
        SimpleNamespace(tts_local_speed=-5)
    )
    assert low.tts_local_speed == schemas.TTS_SPEED_MIN

    high = auth_helpers.build_preferences_response(
        SimpleNamespace(tts_local_speed=99)
    )
    assert high.tts_local_speed == schemas.TTS_SPEED_MAX

    # Endpoints are inclusive: exactly the boundary values pass through.
    at_min = auth_helpers.build_preferences_response(
        SimpleNamespace(tts_local_speed=schemas.TTS_SPEED_MIN)
    )
    assert at_min.tts_local_speed == schemas.TTS_SPEED_MIN

    # Garbage falls back to neutral 1.0.
    garbage = auth_helpers.build_preferences_response(
        SimpleNamespace(tts_local_speed="not-a-number")
    )
    assert garbage.tts_local_speed == 1.0
