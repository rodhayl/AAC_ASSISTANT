from pathlib import Path

from scripts.install_dependencies import ensure_configuration, frontend_build_commands


def test_installer_creates_one_stable_jwt_secret(tmp_path: Path):
    (tmp_path / ".env.example").write_text(
        "BACKEND_PORT=8086\nJWT_SECRET_KEY=CHANGE_ME_TO_A_SECURE_RANDOM_STRING\n",
        encoding="utf-8",
    )

    first_path, first_secret = ensure_configuration(tmp_path)
    results = [ensure_configuration(tmp_path) for _ in range(2)]

    assert all(path == tmp_path / ".env" for path, _ in results)
    assert all(secret == first_secret for _, secret in results)
    secret_lines = [
        line for line in first_path.read_text(encoding="utf-8").splitlines()
        if line.startswith("JWT_SECRET_KEY=")
    ]
    assert secret_lines == [f"JWT_SECRET_KEY={first_secret}"]
    assert len(first_secret) >= 32


def test_frontend_build_plan_is_unattended_and_deterministic(tmp_path: Path):
    frontend = tmp_path / "src" / "frontend"
    frontend.mkdir(parents=True)

    assert frontend_build_commands(tmp_path) == [
        (["npm", "ci"], frontend),
        (["npm", "run", "build"], frontend),
    ]
