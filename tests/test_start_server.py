from scripts import start_server


def test_server_command_includes_graceful_shutdown_timeout(monkeypatch):
    monkeypatch.setattr(start_server.config, "BACKEND_HOST", "127.0.0.1")
    monkeypatch.setattr(start_server.config, "BACKEND_PORT", 8099)
    monkeypatch.setattr(start_server.config, "BACKEND_GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS", 12)

    command = start_server._server_command()

    assert "--timeout-graceful-shutdown" in command
    timeout_index = command.index("--timeout-graceful-shutdown")
    assert command[timeout_index + 1] == "12"
