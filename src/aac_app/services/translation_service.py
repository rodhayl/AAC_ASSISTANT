import json
import re
from pathlib import Path
from typing import Any, Dict, Optional


class TranslationService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TranslationService, cls).__new__(cls)
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
        self._cache: Dict[str, Any] = {}
        self._initialized = True

    def resolve_language(
        self, user: Any = None, accept_language: Optional[str] = None
    ) -> str:
        """
        Resolve the best language to use based on user settings or headers.
        """
        # 1. User preference
        if (
            user
            and hasattr(user, "settings")
            and user.settings
            and user.settings.ui_language
        ):
            return user.settings.ui_language

        # 2. Accept-Language header
        if accept_language:
            # Simple parser: take the first preferred language
            # e.g. "es-ES,es;q=0.9,en;q=0.8" -> "es-ES"
            parts = accept_language.split(",")
            if parts:
                first_lang = parts[0].split(";")[0].strip()
                # Check if we support it
                if (self.locales_dir / first_lang).exists():
                    return first_lang
                # Try short code
                short_lang = first_lang.split("-")[0]
                if (self.locales_dir / short_lang).exists():
                    return short_lang

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
        # Normalize lang (take first 2 chars usually, but directory names are 'en', 'es')
        if not lang:
            lang = "en"
        else:
            # Handle 'en-US' -> 'en' if directory is just 'en'
            # Check if directory exists, otherwise try prefix
            if not (self.locales_dir / lang).exists():
                short_lang = lang.split("-")[0]
                if (self.locales_dir / short_lang).exists():
                    lang = short_lang

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

    def _load_locale(self, lang: str, namespace: str) -> Optional[Dict]:
        cache_key = f"{lang}:{namespace}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Construct file path
        file_path = self.locales_dir / lang / f"{namespace}.json"

        if not file_path.exists():
            # print(f"DEBUG: Locale file not found: {file_path}")
            return None

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._cache[cache_key] = data
                # Locale loaded successfully - no need to log every load
                return data
        except Exception as e:
            print(f"Error loading locale {file_path}: {e}")
            return None


_translation_service = TranslationService()


def get_translation_service():
    return _translation_service
