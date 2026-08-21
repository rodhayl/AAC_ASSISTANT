"""Application configuration backed by :mod:`pydantic-settings`.

``.env`` is the canonical configuration file.  A legacy ``env.properties`` is
copied to ``.env`` on first run, rather than renamed, so existing installations
can roll back safely.
"""

from __future__ import annotations

import os
import secrets
import shutil
import sys
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic_settings import BaseSettings, SettingsConfigDict

# Determine if running as frozen executable (PyInstaller).
IS_FROZEN = getattr(sys, "frozen", False)

if IS_FROZEN:
    # The executable directory is the portable/project root. Bundled resources
    # live in _MEIPASS and are read-only.
    PROJECT_ROOT = Path(sys.executable).parent.absolute()
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", PROJECT_ROOT)).absolute()
else:
    PROJECT_ROOT = Path(__file__).parent.parent.absolute()
    BUNDLE_DIR = PROJECT_ROOT

def _is_program_files_path(path: Path) -> bool:
    """Return whether a path is under a standard Windows Program Files folder."""
    program_files_parts = {"program files", "program files (x86)"}
    return any(part.casefold() in program_files_parts for part in path.parts)


def resolve_runtime_root(
    project_root: Path,
    *,
    is_frozen: bool,
    appdata_root: Path | None = None,
) -> Path:
    """
    Resolve the writable runtime root for config, database, logs, and uploads.

    An onedir copy outside Program Files is portable and keeps data beside its
    executable. An installed copy under Program Files uses the per-user
    application data directory so standard users never need write access to the
    installation directory. ``AAC_ASSISTANT_PORTABLE=1`` explicitly forces
    portable behavior for a frozen copy.
    """
    project_root = Path(project_root).absolute()
    if not is_frozen or os.environ.get("AAC_ASSISTANT_PORTABLE", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return project_root

    if not _is_program_files_path(project_root):
        return project_root

    appdata = Path(
        appdata_root
        or os.environ.get("APPDATA")
        or (Path.home() / "AppData" / "Roaming")
    ).absolute()
    return appdata / "AACAssistant"


RUNTIME_ROOT = resolve_runtime_root(PROJECT_ROOT, is_frozen=IS_FROZEN)

ENV_FILE_NAME = ".env"
LEGACY_ENV_FILE_NAME = "env.properties"
ENV_FILE = RUNTIME_ROOT / ENV_FILE_NAME
LEGACY_ENV_FILE = RUNTIME_ROOT / LEGACY_ENV_FILE_NAME
DEFAULT_ALLOWED_ORIGINS = (
    "http://localhost:5176,http://localhost:3000,http://localhost:5173,"
    "http://127.0.0.1:5173,http://127.0.0.1:5176"
)
JWT_PLACEHOLDERS = frozenset(
    {
        "",
        "CHANGE_ME_TO_A_SECURE_RANDOM_STRING",
        "INSECURE_DEFAULT_CHANGE_IN_PRODUCTION",
    }
)
# Deterministic fallback credential retained strictly for automated test suites.
# Packaged, development, and production installations never create an account
# with a default password: operators configure a password explicitly or complete
# the first-run web setup screen (/setup).
DEFAULT_BOOTSTRAP_ADMIN_PASSWORD = "Admin123"
_BOOTSTRAP_PASSWORD_KEY = "AAC_BOOTSTRAP_ADMIN_PASSWORD"


class Settings(BaseSettings):
    """Typed application settings loaded from environment and dotenv files."""

    model_config = SettingsConfigDict(
        env_file=(".env", "env.properties"),
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    # Local-first default: bind to loopback so the app is not reachable from
    # the network unless the operator explicitly opts into a remote bind.
    BACKEND_HOST: str = "127.0.0.1"
    BACKEND_PORT: int = 8086
    BACKEND_GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS: int = 10
    FRONTEND_PORT: int = 5176

    DATABASE_NAME: str = "aac_assistant.db"
    DATA_DIR: str = "data"
    LOGS_DIR: str = "logs"
    UPLOADS_DIR: str = "uploads"

    JWT_SECRET_KEY: str = ""

    OLLAMA_BASE_URL: str = "http://localhost:11434"
    LMSTUDIO_BASE_URL: str = "http://localhost:1234/v1"
    AI_MAX_TOKENS: int = 1024
    AI_TEMPERATURE: float = 0.5
    OPENROUTER_API_KEY: str = ""

    APP_NAME: str = "AAC Assistant"
    APP_VERSION: str = "2.0.0"
    ENVIRONMENT: str = "development"
    DEFAULT_LOCALE: str = "es"
    # Localized UI values accepted by the preferences API. Short codes remain
    # supported for legacy installations and are normalized by the frontend.
    SUPPORTED_UI_LANGUAGES: str = "es-ES,en-US,es,en"

    ALLOWED_ORIGINS: str = DEFAULT_ALLOWED_ORIGINS
    ALLOW_DB_RESET: bool = False
    AAC_SEED_SAMPLE_DATA: bool = False

    AAC_BOOTSTRAP_ADMIN_ON_FIRST_RUN: bool = True
    AAC_BOOTSTRAP_ADMIN_USERNAME: str = "admin1"
    AAC_BOOTSTRAP_ADMIN_PASSWORD: str | None = None
    # Image backfill is maintenance work; keep it opt-in so normal startup
    # does not perform avoidable network and database work.
    AAC_ENABLE_SYMBOL_IMAGE_BACKFILL: bool = False
    AAC_SYMBOL_IMAGE_BACKFILL_LIMIT: int = 100
    # One-time bulk import of the full ARASAAC library at startup. Opt-in for
    # the same reason: it downloads every distinct pictogram on first run.
    AAC_ENABLE_ARASAAC_LIBRARY_IMPORT: bool = False
    # Comma-separated locale list to import. Pictograms are locale-independent,
    # so each locale materializes its translated labels reusing the same images.
    AAC_ARASAAC_LIBRARY_LOCALES: str = "es"
    # Rebuild the n-gram prediction models from real symbol usage logs at
    # startup. Opt-in: it scans the usage-log table and rewrites the writable
    # data/ngrams models (the bundled files are never modified).
    AAC_ENABLE_NGRAM_REBUILD: bool = False
    # Seconds between periodic n-gram rebuilds while the server runs, so the
    # model keeps learning from new usage without a restart. 0 disables the
    # periodic refresh (startup-only rebuild when the flag above is enabled).
    AAC_NGRAM_REBUILD_INTERVAL_SECONDS: int = 3600

    # Optional deterministic passwords are intentionally unset by default.
    AAC_SEED_DEFAULT_PASSWORD: str | None = None
    AAC_SEED_STUDENT1_PASSWORD: str | None = None
    AAC_SEED_TEACHER1_PASSWORD: str | None = None
    AAC_SEED_ADMIN1_PASSWORD: str | None = None

def _find_example_file(project_root: Path) -> Path | None:
    """Find the current example config in a project or frozen bundle."""
    candidates = (
        project_root / ".env.example",
        BUNDLE_DIR / ".env.example",
    )
    return next((path for path in candidates if path.exists()), None)


def ensure_env_file(project_root: Path | None = None) -> Path:
    """Create the canonical ``.env`` and migrate a legacy file when needed."""
    root = Path(project_root or RUNTIME_ROOT).absolute()
    env_path = root / ENV_FILE_NAME
    legacy_path = root / LEGACY_ENV_FILE_NAME

    if env_path.exists():
        return env_path

    if legacy_path.exists():
        shutil.copyfile(legacy_path, env_path)
        logger.info(
            "Migrated legacy configuration from {} to {} (legacy file preserved)",
            legacy_path,
            env_path,
        )
    else:
        example_path = _find_example_file(root)
        if example_path is not None:
            shutil.copyfile(example_path, env_path)
            logger.info("Created configuration file {} from {}", env_path, example_path)
        else:
            env_path.touch()
            logger.info("Created empty configuration file {}", env_path)

    return env_path


def _is_jwt_secret(value: str) -> bool:
    """Return whether a value is a usable generated or user-supplied secret."""
    return value.strip() not in JWT_PLACEHOLDERS and len(value.strip()) >= 32


def _env_key(line: str) -> str | None:
    """Return the key from a dotenv assignment, ignoring comments and blanks."""
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None
    return stripped.split("=", 1)[0].strip()


def ensure_jwt_secret(env_path: Path | None = None) -> str:
    """Ensure a stable JWT secret and one assignment for every dotenv key."""
    path = Path(env_path or ENV_FILE).absolute()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()

    original_content = path.read_text(encoding="utf-8")
    lines = original_content.splitlines()
    existing_values = [
        line.partition("=")[2].strip()
        for line in lines
        if _env_key(line) == "JWT_SECRET_KEY"
    ]
    secret = next((value for value in reversed(existing_values) if _is_jwt_secret(value)), None)
    if secret is None:
        secret = secrets.token_hex(32)

    last_occurrences: dict[str, int] = {}
    for index, line in enumerate(lines):
        key = _env_key(line)
        if key is not None and key != "JWT_SECRET_KEY":
            last_occurrences[key] = index

    updated_lines: list[str] = []
    inserted = False
    for index, line in enumerate(lines):
        key = _env_key(line)
        if key == "JWT_SECRET_KEY":
            if not inserted:
                updated_lines.append(f"JWT_SECRET_KEY={secret}")
                inserted = True
            continue
        if key is not None and last_occurrences.get(key) != index:
            continue
        updated_lines.append(line)

    if not inserted:
        if updated_lines and updated_lines[-1].strip():
            updated_lines.append("")
        updated_lines.append(f"JWT_SECRET_KEY={secret}")

    updated_content = "\n".join(updated_lines).rstrip() + "\n"
    if updated_content != original_content:
        path.write_text(updated_content, encoding="utf-8")

    return secret


def _dotenv_value(path: Path, key: str) -> str | None:
    """Return the last non-empty assignment for ``key`` in a dotenv file."""
    if not path.exists():
        return None
    for line in reversed(path.read_text(encoding="utf-8").splitlines()):
        if _env_key(line) == key:
            value = line.partition("=")[2].strip()
            if value:
                return value
    return None


def _is_test_environment() -> bool:
    """Return True if running inside an explicit automated test suite."""
    if os.environ.get("TESTING", "").strip().lower() in {"1", "true", "yes"}:
        return True
    return os.environ.get("ENVIRONMENT", "").strip().casefold() in {"test", "testing"}


def explicit_bootstrap_password() -> str | None:
    """Return an explicitly configured bootstrap password, or ``None``.

    Only the process environment and the local dotenv files are consulted. When
    the operator has not configured a password at all, callers fall back to the
    initial web setup screen or require explicit configuration in production.
    """
    environment_value = os.environ.get(_BOOTSTRAP_PASSWORD_KEY, "").strip()
    if environment_value:
        return environment_value
    for candidate in (ENV_FILE, LEGACY_ENV_FILE):
        value = _dotenv_value(candidate, _BOOTSTRAP_PASSWORD_KEY)
        if value is not None:
            return value
    return None


def resolve_bootstrap_password() -> str | None:
    """Return the bootstrap admin password if explicitly configured or in test mode.

    In packaged, development, and production runtime, when no password is
    configured in the environment or dotenv file, this returns ``None`` to
    signal that the operator must choose a password via the initial web setup
    screen (/setup). Deterministic credentials remain only in explicit test
    environments.
    """
    explicit = explicit_bootstrap_password()
    if explicit is not None:
        return explicit
    if _is_test_environment():
        return DEFAULT_BOOTSTRAP_ADMIN_PASSWORD
    return None


def load_settings(project_root: Path | None = None) -> Settings:
    """Prepare config files and load typed settings for a project root."""
    root = Path(project_root or RUNTIME_ROOT).absolute()
    env_path = root / ENV_FILE_NAME
    legacy_path = root / LEGACY_ENV_FILE_NAME
    environment_secret = os.environ.get("JWT_SECRET_KEY", "")

    # A managed/read-only deployment can provide all settings through the
    # process environment. Do not create or rewrite dotenv files in that case.
    # Existing files remain readable and environment variables still take
    # precedence through pydantic-settings.
    if env_path.exists():
        if not _is_jwt_secret(environment_secret):
            ensure_jwt_secret(env_path)
    elif not _is_jwt_secret(environment_secret):
        env_path = ensure_env_file(root)
        ensure_jwt_secret(env_path)
    elif _is_jwt_secret(environment_secret):
        logger.info("Using JWT_SECRET_KEY from the environment without writing dotenv files")

    # pydantic-settings gives later files precedence. Explicitly put .env last
    # so a retained legacy file cannot override migrated settings.
    env_files = tuple(
        path for path in (legacy_path, env_path) if path.exists()
    ) or (env_path,)
    return Settings(_env_file=env_files)


settings = load_settings()


def _path_setting(value: str) -> Path:
    """Resolve a path setting relative to the project root."""
    path = Path(value)
    return path if path.is_absolute() else RUNTIME_ROOT / path


def _sync_module_settings() -> None:
    """Expose typed settings through the legacy module-level API."""
    global DATA_DIR, DATABASE_PATH, LOGS_DIR, UPLOADS_DIR
    for field_name in Settings.model_fields:
        if field_name in {"DATA_DIR", "LOGS_DIR", "UPLOADS_DIR", "DATABASE_NAME"}:
            continue
        globals()[field_name] = getattr(settings, field_name)
    DATA_DIR = _path_setting(settings.DATA_DIR)
    DATABASE_PATH = DATA_DIR / settings.DATABASE_NAME
    LOGS_DIR = _path_setting(settings.LOGS_DIR)
    UPLOADS_DIR = _path_setting(settings.UPLOADS_DIR)


_sync_module_settings()

DATA_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


def get(key: str, default: Any = None) -> Any:
    """Get a typed setting, preserving compatibility for dynamic keys."""
    env_value = os.environ.get(key)
    if env_value is not None:
        return env_value
    if key in Settings.model_fields:
        return getattr(settings, key)
    return default if default is not None else ""


def get_int(key: str, default: int = 0) -> int:
    """Get a configuration value as an integer."""
    value = get(key, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def get_bool(key: str, default: bool = False) -> bool:
    """Get a configuration value as a boolean."""
    value = get(key, default)
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"true", "1", "yes", "on"}


def get_bundled_path(relative_path: str) -> Path:
    """
    Get the path to a bundled resource file.
    In frozen mode, looks in BUNDLE_DIR first, then PROJECT_ROOT.
    In development, looks in PROJECT_ROOT.
    """
    candidates = (
        (BUNDLE_DIR / relative_path, PROJECT_ROOT / relative_path)
        if IS_FROZEN
        else (PROJECT_ROOT / relative_path,)
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def get_bundled_models_dir() -> Path | None:
    """
    Return the read-only bundled AI-models cache directory, or None.

    Release builds ship optional model weights under ``models`` so the packaged
    application works fully offline. Providers load from this directory with
    ``local_files_only=True`` when it is present, and otherwise fall back to the
    writable ``data/models`` directory with on-demand download.
    """
    candidate = get_bundled_path("models")
    return candidate if candidate.is_dir() else None


def resolve_model_cache_dir(model_dir_name: str) -> tuple[Path, bool]:
    """
    Resolve an optional AI model's cache directory and offline mode.

    Returns ``(cache_dir, local_files_only)``. When the release bundle ships the
    requested model (identified by its Hugging Face cache directory name, e.g.
    ``models--Systran--faster-whisper-tiny``), the read-only bundled directory is
    used with ``local_files_only=True`` so no network access is attempted. Any
    other model size falls back to the writable ``data/models`` directory with
    on-demand download.
    """
    bundled = get_bundled_models_dir()
    if bundled is not None and (bundled / model_dir_name).is_dir():
        return bundled, True
    return get_data_path("models"), False


def get_data_path(relative_path: str = "") -> Path:
    """
    Get path within the data directory.
    Creates the directory if it doesn't exist.
    """
    path = DATA_DIR / relative_path if relative_path else DATA_DIR
    if relative_path and not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_ngrams_path() -> Path:
    """Get the path to N-gram models directory."""
    return get_bundled_path("src/aac_app/data/ngrams")
