"""
Centralized configuration module for AAC Assistant.
Reads configuration from env.properties file.
"""

import os
import sys
from pathlib import Path
from typing import Optional

# Determine if running as frozen executable (PyInstaller)
IS_FROZEN = getattr(sys, 'frozen', False)

# Project root directory
if IS_FROZEN:
    # For one-folder PyInstaller builds, executable is in the root folder
    # sys._MEIPASS contains bundled data, but we use exe parent for user data
    PROJECT_ROOT = Path(sys.executable).parent.absolute()
    # BUNDLE_DIR contains the extracted/bundled resources
    BUNDLE_DIR = Path(getattr(sys, '_MEIPASS', PROJECT_ROOT)).absolute()
else:
    PROJECT_ROOT = Path(__file__).parent.parent.absolute()
    BUNDLE_DIR = PROJECT_ROOT

CONFIG_FILE = PROJECT_ROOT / "env.properties"

# For frozen mode, also check bundle dir for env.properties.example
if IS_FROZEN and not CONFIG_FILE.exists():
    bundle_config = BUNDLE_DIR / "env.properties"
    if bundle_config.exists():
        CONFIG_FILE = bundle_config
    else:
        # Copy from example if available
        example_config = BUNDLE_DIR / "env.properties.example"
        if example_config.exists():
            import shutil
            try:
                shutil.copy(example_config, PROJECT_ROOT / "env.properties")
                CONFIG_FILE = PROJECT_ROOT / "env.properties"
            except Exception:
                pass  # Will use defaults

_config_cache: dict = {}


def _load_config() -> dict:
    """Load configuration from env.properties file."""
    global _config_cache
    if _config_cache:
        return _config_cache

    config = {}
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    config[key.strip()] = value.strip()

    _config_cache = config
    return config


def get(key: str, default: Optional[str] = None) -> str:
    """Get a configuration value by key."""
    config = _load_config()
    # Environment variables take precedence
    env_value = os.environ.get(key)
    if env_value is not None:
        return env_value
    return config.get(key, default or "")


def get_int(key: str, default: int = 0) -> int:
    """Get a configuration value as integer."""
    value = get(key, str(default))
    try:
        return int(value)
    except ValueError:
        return default


def get_bool(key: str, default: bool = False) -> bool:
    """Get a configuration value as boolean."""
    value = get(key, str(default)).lower()
    return value in ("true", "1", "yes", "on")


def reload():
    """Reload configuration from file."""
    global _config_cache
    _config_cache = {}
    _load_config()


# Server Configuration
BACKEND_HOST = get("BACKEND_HOST", "0.0.0.0")
BACKEND_PORT = get_int("BACKEND_PORT", 8086)
FRONTEND_PORT = get_int("FRONTEND_PORT", 5176)

# Database Configuration
DATABASE_NAME = get("DATABASE_NAME", "aac_assistant.db")
DATA_DIR = PROJECT_ROOT / get("DATA_DIR", "data")
DATABASE_PATH = DATA_DIR / DATABASE_NAME

# Logging Configuration
LOGS_DIR = PROJECT_ROOT / get("LOGS_DIR", "logs")

# AI Provider Configuration
OLLAMA_BASE_URL = get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_DEFAULT_MODEL = get("OLLAMA_DEFAULT_MODEL", "qwen:7b-q4_0")
OPENROUTER_API_KEY = get("OPENROUTER_API_KEY", "")

# Application Settings
APP_NAME = get("APP_NAME", "AAC Assistant")
APP_VERSION = get("APP_VERSION", "1.0.0")
ENVIRONMENT = get("ENVIRONMENT", "development")  # development, staging, production
DEFAULT_LOCALE = get("DEFAULT_LOCALE", "es")

# Security Settings
FORCE_HTTPS = get_bool("FORCE_HTTPS", False)  # Redirect HTTP to HTTPS in production
SECURE_COOKIES = get_bool("SECURE_COOKIES", False)  # Set secure flag on cookies
ALLOWED_ORIGINS = get(
    "ALLOWED_ORIGINS",
    "http://localhost:5176,http://localhost:3000,http://localhost:5173,http://127.0.0.1:5173,http://127.0.0.1:5176",
)  # Comma-separated CORS origins

# Feature Flags
ENABLE_AAC_EXPANSION = get_bool(
    "ENABLE_AAC_EXPANSION", True
)  # Enable AAC grammar expansion by default

# Admin Features - Security
ALLOW_DB_RESET = get_bool(
    "ALLOW_DB_RESET", False
)  # Allow database reset endpoint (disable in production!)

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Create uploads directory
UPLOADS_DIR = PROJECT_ROOT / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


def get_api_base_url(host: str = "localhost") -> str:
    """Get the full API base URL."""
    return f"http://{host}:{BACKEND_PORT}/api"


def get_ws_base_url(host: str = "localhost") -> str:
    """Get the WebSocket base URL."""
    return f"ws://{host}:{BACKEND_PORT}/api"


def get_bundled_path(relative_path: str) -> Path:
    """
    Get the path to a bundled resource file.
    In frozen mode, looks in BUNDLE_DIR first, then PROJECT_ROOT.
    In development, looks in PROJECT_ROOT.
    """
    if IS_FROZEN:
        bundle_path = BUNDLE_DIR / relative_path
        if bundle_path.exists():
            return bundle_path
    return PROJECT_ROOT / relative_path


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
    if IS_FROZEN:
        # In frozen mode, ngrams are bundled in src/aac_app/data/ngrams
        bundled_ngrams = BUNDLE_DIR / "src" / "aac_app" / "data" / "ngrams"
        if bundled_ngrams.exists():
            return bundled_ngrams
    # Development mode
    return PROJECT_ROOT / "src" / "aac_app" / "data" / "ngrams"
