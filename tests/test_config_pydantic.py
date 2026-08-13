import json
import re
import tomllib
from pathlib import Path

from src.aac_app.services.auth_service import password_strength_error
from src.config import Settings, ensure_env_file, ensure_jwt_secret, load_settings

REPO_ROOT = Path(__file__).parents[1]


def test_release_version_defaults_are_aligned(monkeypatch):
    env_example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    legacy_example = (REPO_ROOT / "env.properties.example").read_text(encoding="utf-8")
    installer = (REPO_ROOT / "installer.iss").read_text(encoding="utf-8")
    pyproject_path = REPO_ROOT / "pyproject.toml"
    pyproject = pyproject_path.read_text(encoding="utf-8")
    uv_lock = (REPO_ROOT / "uv.lock").read_text(encoding="utf-8")
    frontend_config = (REPO_ROOT / "src/frontend/src/config.ts").read_text(encoding="utf-8")
    frontend_package = json.loads(
        (REPO_ROOT / "src/frontend/package.json").read_text(encoding="utf-8")
    )

    package_version = tomllib.loads(pyproject)["project"]["version"]
    installer_version = re.search(r'#define MyAppVersion "([^"]+)"', installer)
    lock_version = re.search(r'name = "aac-assistant"\s+version = "([^"]+)"', uv_lock)
    frontend_version = re.search(
        r"APP_VERSION: import\.meta\.env\.VITE_APP_VERSION \|\| '([^']+)'", frontend_config
    )
    assert installer_version is not None
    assert lock_version is not None
    assert frontend_version is not None

    versions = {
        package_version,
        installer_version.group(1),
        lock_version.group(1),
        frontend_version.group(1),
    }
    assert len(versions) == 1
    version = package_version

    monkeypatch.delenv("APP_VERSION", raising=False)
    assert [line for line in env_example.splitlines() if line.startswith("APP_VERSION=")] == [
        f"APP_VERSION={version}"
    ]
    assert [line for line in legacy_example.splitlines() if line.startswith("APP_VERSION=")] == [
        f"APP_VERSION={version}"
    ]
    assert f'version = "{version}"' in pyproject
    assert frontend_package["version"] == "0.0.0"
    assert version == Settings(_env_file=None).APP_VERSION


def test_production_bootstrap_password_uses_shared_strength_policy():
    weak_password = "weak-password"
    error = password_strength_error(weak_password)
    assert error is not None

    settings = Settings(
        _env_file=None,
        ENVIRONMENT="production",
        JWT_SECRET_KEY="a" * 32,
        AAC_BOOTSTRAP_ADMIN_PASSWORD=weak_password,
    )
    assert weak_password == settings.AAC_BOOTSTRAP_ADMIN_PASSWORD
    assert password_strength_error("A-unique-production-password-123") is None


def test_read_only_style_environment_secret_does_not_create_dotenv_file(tmp_path, monkeypatch):
    secret = "environment_secret_" + ("x" * 32)
    monkeypatch.setenv("JWT_SECRET_KEY", secret)

    settings = load_settings(tmp_path)

    assert secret == settings.JWT_SECRET_KEY
    assert not (tmp_path / ".env").exists()


def test_settings_uses_pydantic_settings_and_ignores_unknown_keys():
    assert Settings.model_config["env_file"] == (".env", "env.properties")
    assert Settings.model_config["extra"] == "ignore"

    settings = Settings(
        _env_file=None,
        BACKEND_PORT=8086,
        FORCE_HTTPS=True,
        SECURE_COOKIES=True,
        ENABLE_AAC_EXPANSION=True,
        OLLAMA_DEFAULT_MODEL="qwen:7b",
    )

    assert settings.BACKEND_PORT == 8086
    assert not hasattr(settings, "FORCE_HTTPS")
    assert not hasattr(settings, "SECURE_COOKIES")
    assert not hasattr(settings, "ENABLE_AAC_EXPANSION")
    assert not hasattr(settings, "OLLAMA_DEFAULT_MODEL")


def test_first_run_creates_env_and_reuses_one_jwt_secret(tmp_path: Path):
    (tmp_path / ".env.example").write_text(
        "BACKEND_PORT=8086\nJWT_SECRET_KEY=CHANGE_ME_TO_A_SECURE_RANDOM_STRING\n",
        encoding="utf-8",
    )

    env_path = ensure_env_file(tmp_path)
    first_secret = ensure_jwt_secret(env_path)
    for _ in range(2):
        assert ensure_jwt_secret(env_path) == first_secret

    lines = env_path.read_text(encoding="utf-8").splitlines()
    secret_lines = [line for line in lines if line.startswith("JWT_SECRET_KEY=")]
    assert secret_lines == [f"JWT_SECRET_KEY={first_secret}"]
    assert len(first_secret) >= 32
    assert first_secret != "CHANGE_ME_TO_A_SECURE_RANDOM_STRING"


def test_legacy_env_properties_is_copied_and_values_are_preserved(
    tmp_path: Path, monkeypatch
):
    monkeypatch.delenv("BACKEND_PORT", raising=False)
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

    legacy_path = tmp_path / "env.properties"
    legacy_secret = "legacy-test-" + ("x" * 40)
    legacy_path.write_text(
        "BACKEND_PORT=8123\n"
        "BACKEND_PORT=8124\n"
        f"JWT_SECRET_KEY={legacy_secret}\n",
        encoding="utf-8",
    )

    env_path = ensure_env_file(tmp_path)
    assert env_path == tmp_path / ".env"
    assert env_path.read_text(encoding="utf-8") == legacy_path.read_text(encoding="utf-8")
    assert legacy_path.exists()

    settings = load_settings(tmp_path)
    assert settings.BACKEND_PORT == 8124
    assert legacy_secret == settings.JWT_SECRET_KEY

    migrated_lines = env_path.read_text(encoding="utf-8").splitlines()
    assert [line for line in migrated_lines if line.startswith("BACKEND_PORT=")] == [
        "BACKEND_PORT=8124"
    ]
