import json
import re
from pathlib import Path
from typing import Any, Protocol

from loguru import logger

# ``lang`` and ``namespace`` become filesystem path components below. Only
# well-formed language tags (e.g. "en", "es-ES") and plain namespace names
# (letters, digits, '_', '-', '/', '.') are accepted; everything else is
# rejected before it can reach a path operation.
_LOCALE_TAG_RE = re.compile(r"^[A-Za-z]{2}(?:-[A-Za-z0-9]{1,8})?$")
_NAMESPACE_RE = re.compile(r"^[A-Za-z0-9_.\/-]+$")


class UserSettingsLanguage(Protocol):
    """Structural contract for the user-settings language preference."""

    ui_language: str | None


class UserLanguage(Protocol):
    """Structural contract for resolving a user's UI language."""

    settings: UserSettingsLanguage | None


def _resolve_locale_code(lang: str | None, available: frozenset[str]) -> str:
    """Map a requested language onto an existing locale directory name.

    Returns ``lang`` only when it equals a name already present in
    ``available``; otherwise its base tag (``"es-ES"`` → ``"es"``) is tried
    and finally the English code is returned. The result is always a member
    of ``available`` (or ``"en"``), so callers can safely build paths from
    it.
    """
    if not lang:
        return "en"
    prefix = lang.split("-")[0]
    for name in available:
        if name in (lang, prefix):
            return name
    return "en"


class TranslationService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # Resolve path relative to this file
        # src/aac_app/services/translation_service.py -> src/frontend/src/locales
        current_dir = Path(__file__).resolve().parent
        # Go up: services -> aac_app -> src
        # ../../frontend/src/locales
        self.locales_dir = current_dir.parent.parent / "frontend" / "src" / "locales"
        self._cache: dict[str, Any] = {}
        self._initialized = True

    def _available_locales(self) -> frozenset[str]:
        """Return the names of the locale directories that exist on disk."""
        try:
            return frozenset(
                entry.name for entry in self.locales_dir.iterdir() if entry.is_dir()
            )
        except OSError:
            return frozenset({"en"})

    def resolve_language(
        self, user: UserLanguage | None = None, accept_language: str | None = None
    ) -> str:
        """
        Resolve the best language to use based on user settings or headers.
        """
        # 1. User preference
        settings = user.settings if user is not None else None
        ui_language = settings.ui_language if settings is not None else None
        if ui_language:
            return ui_language

        # 2. Accept-Language header
        if accept_language:
            # Simple parser: take the first preferred language
            # e.g. "es-ES,es;q=0.9,en;q=0.8" -> "es-ES"
            parts = accept_language.split(",")
            if parts:
                # The header is attacker-controlled: map it onto the locale
                # directory names that exist on disk. The returned value is
                # always a server-side name (or the English fallback), never
                # the header text itself.
                first_lang = parts[0].split(";")[0].strip()
                return _resolve_locale_code(first_lang, self._available_locales())

        # 3. Default
        return "en"

    def get(self, lang: str, namespace: str, key: str, **kwargs) -> str:
        """
        Get a translation string.
        Args:
            lang: Language code (e.g., 'en', 'es')
            namespace: Namespace (e.g., 'pages/learning', 'common')
            key: Key in the JSON file (supports dot notation for nested keys)
            **kwargs: Variables to interpolate (e.g., name="John")
        """
        # Normalize lang (take first 2 chars usually, but directory names are
        # 'en', 'es'). ``lang`` may reach here from caller-supplied strings
        # (e.g. the Accept-Language header), so it is mapped onto the locale
        # directory names that exist on disk: the assigned value is always a
        # server-side directory name or the English code, never the caller's
        # string, so no path component below can depend on user input.
        lang = _resolve_locale_code(lang, self._available_locales())

        # Try to load
        data = self._load_locale(lang, namespace)
        if not data:
            # Fallback to 'en'
            if lang != "en":
                data = self._load_locale("en", namespace)

            if not data:
                return key

        # Retrieve key
        val = data
        parts = key.split(".")
        for part in parts:
            if isinstance(val, dict) and part in val:
                val = val[part]
            else:
                # Fallback to 'en' if key missing in target lang
                if lang != "en":
                    en_data = self._load_locale("en", namespace)
                    if en_data:
                        val = en_data
                        for en_part in parts:
                            if isinstance(val, dict) and en_part in val:
                                val = val[en_part]
                            else:
                                return key
                        break
                    else:
                        return key
                else:
                    return key

        if not isinstance(val, str):
            return key

        # Interpolate {{var}}
        def replace(match):
            var_name = match.group(1).strip()
            return str(kwargs.get(var_name, match.group(0)))

        return re.sub(r"\{\{(.*?)\}\}", replace, val)

    def _load_locale(self, lang: str, namespace: str) -> dict | None:
        cache_key = f"{lang}:{namespace}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Defense in depth on top of the caller-side tag checks: lang and
        # namespace build a filesystem path, so both must be well-formed and
        # the resolved file must stay inside the locales tree.
        if not _LOCALE_TAG_RE.fullmatch(lang) or not _NAMESPACE_RE.fullmatch(namespace):
            return None
        file_path = (self.locales_dir / lang / f"{namespace}.json").resolve()
        if not file_path.is_relative_to(self.locales_dir.resolve()):
            return None

        if not file_path.exists():
            return None

        try:
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)
                self._cache[cache_key] = data
                return data
        except Exception as e:
            logger.warning("Error loading locale {}: {}", file_path, e)
            return None


_translation_service = TranslationService()


def get_translation_service():
    return _translation_service
