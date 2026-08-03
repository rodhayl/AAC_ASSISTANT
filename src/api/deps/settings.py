"""Cached access to application settings stored in SQLite."""

from threading import RLock

from loguru import logger

from src.aac_app.db import get_session
from src.aac_app.models import AppSettings

_settings_cache: dict[str, str] = {}
_settings_cache_lock = RLock()


def get_setting_value(key: str, default: str = "") -> str:
    """Return a setting value, reading SQLite only on the first cache miss."""
    with _settings_cache_lock:
        if key in _settings_cache:
            return _settings_cache[key]

    try:
        with get_session() as db:
            setting = (
                db.query(AppSettings).filter(AppSettings.setting_key == key).first()
            )
            value = setting.setting_value if setting else default
    except Exception as exc:
        logger.warning(f"Failed to get setting {key}: {exc}")
        value = default

    with _settings_cache_lock:
        # Another thread may have populated the value while this query ran.
        # Returning the existing value keeps the cache deterministic.
        return _settings_cache.setdefault(key, value)


def invalidate_setting(key: str) -> None:
    """Remove one setting from the process-local cache after an update."""
    with _settings_cache_lock:
        _settings_cache.pop(key, None)


def clear_settings_cache() -> None:
    """Clear all cached settings, primarily for tests and database resets."""
    with _settings_cache_lock:
        _settings_cache.clear()
