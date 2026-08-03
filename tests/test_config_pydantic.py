from pathlib import Path

from src.config import Settings, ensure_env_file, ensure_jwt_secret, load_settings


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


def test_legacy_env_properties_is_copied_and_values_are_preserved(tmp_path: Path):
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
