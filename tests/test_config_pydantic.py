import json
import re
import tomllib
from pathlib import Path

from src import config
from src.aac_app.services.auth_service import password_strength_error
from src.config import Settings, ensure_env_file, ensure_jwt_secret, load_settings

REPO_ROOT = Path(__file__).parents[1]


def test_release_version_has_a_single_source(monkeypatch):
    """pyproject.toml is the only place the release version may be written."""
    installer = (REPO_ROOT / "installer.iss").read_text(encoding="utf-8")
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    uv_lock = (REPO_ROOT / "uv.lock").read_text(encoding="utf-8")
    frontend_package = json.loads(
        (REPO_ROOT / "src/frontend/package.json").read_text(encoding="utf-8")
    )
    version = tomllib.loads(pyproject)["project"]["version"]
    assert re.fullmatch(r"\d+\.\d+\.\d+", version)

    lock_version = re.search(r'name = "aac-assistant"\s+version = "([^"]+)"', uv_lock)
    assert lock_version is not None
    assert lock_version.group(1) == version, "uv.lock is stale; run uv lock"
    assert frontend_package["version"] == "0.0.0"

    # The runtime derives the version from pyproject.toml (a source checkout or
    # the frozen bundle both ship the file); an APP_VERSION variable is the
    # only intended override.
    monkeypatch.delenv("APP_VERSION", raising=False)
    assert version == Settings(_env_file=None).APP_VERSION
    assert config.read_project_version() == version

    # Every layer that once kept its own copy now derives the value from that
    # single source, so the literal must not reappear in any of them.
    duplicated = [
        relative
        for relative in (
            ".env.example",
            "env.properties.example",
            "installer.iss",
            "build_package.bat",
            "src/config.py",
            "src/frontend/src/config.ts",
            ".github/workflows/ci.yml",
            ".github/workflows/release.yml",
        )
        if version in (REPO_ROOT / relative).read_text(encoding="utf-8")
    ]
    assert duplicated == [], f"these files still duplicate the release version: {duplicated}"

    # The plumbing each layer needs to read that single source.
    spec = (REPO_ROOT / "AAC_Assistant.spec").read_text(encoding="utf-8")
    assert '("pyproject.toml", ".")' in spec
    build = (REPO_ROOT / "build_package.bat").read_text(encoding="utf-8")
    assert "uv version --short" in build
    assert "/DMyAppVersion=%VERSION%" in build
    assert "{#MyAppVersion}" in installer
    assert "#ifndef MyAppVersion" in installer
    for relative in (
        "src/frontend/src/config.ts",
        "src/frontend/vite.config.ts",
        "src/frontend/vitest.config.ts",
    ):
        assert "VITE_APP_VERSION" in (REPO_ROOT / relative).read_text(encoding="utf-8")


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


def test_explicit_bootstrap_password_reads_environment_then_dotenv(tmp_path, monkeypatch):
    monkeypatch.delenv("AAC_BOOTSTRAP_ADMIN_PASSWORD", raising=False)
    import src.config as config_module

    env_file = tmp_path / ".env"
    legacy_file = tmp_path / "env.properties"
    monkeypatch.setattr(config_module, "ENV_FILE", env_file)
    monkeypatch.setattr(config_module, "LEGACY_ENV_FILE", legacy_file)

    assert config_module.explicit_bootstrap_password() is None

    env_file.write_text("AAC_BOOTSTRAP_ADMIN_PASSWORD=EnvSecret123\n", encoding="utf-8")
    assert config_module.explicit_bootstrap_password() == "EnvSecret123"

    monkeypatch.setenv("AAC_BOOTSTRAP_ADMIN_PASSWORD", "ProcessSecret123")
    assert config_module.explicit_bootstrap_password() == "ProcessSecret123"


def test_resolve_bootstrap_password_returns_default_in_test_mode(tmp_path, monkeypatch):
    monkeypatch.delenv("AAC_BOOTSTRAP_ADMIN_PASSWORD", raising=False)
    monkeypatch.setenv("TESTING", "1")
    import src.config as config_module

    env_file = tmp_path / ".env"
    legacy_file = tmp_path / "env.properties"
    monkeypatch.setattr(config_module, "ENV_FILE", env_file)
    monkeypatch.setattr(config_module, "LEGACY_ENV_FILE", legacy_file)

    resolved = config_module.resolve_bootstrap_password()
    assert resolved == config_module.DEFAULT_BOOTSTRAP_ADMIN_PASSWORD
    assert not env_file.exists()


def test_resolve_bootstrap_password_returns_none_in_standard_runtime(tmp_path, monkeypatch):
    monkeypatch.delenv("AAC_BOOTSTRAP_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "development")
    import src.config as config_module

    env_file = tmp_path / ".env"
    legacy_file = tmp_path / "env.properties"
    monkeypatch.setattr(config_module, "ENV_FILE", env_file)
    monkeypatch.setattr(config_module, "LEGACY_ENV_FILE", legacy_file)

    resolved = config_module.resolve_bootstrap_password()
    assert resolved is None
    assert not env_file.exists()


def test_resolve_bootstrap_password_returns_explicit_value_verbatim(tmp_path, monkeypatch):
    monkeypatch.setenv("AAC_BOOTSTRAP_ADMIN_PASSWORD", "ConfiguredSecret123")
    import src.config as config_module

    assert config_module.resolve_bootstrap_password() == "ConfiguredSecret123"


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
