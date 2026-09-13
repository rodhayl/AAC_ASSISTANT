"""Regression tests for process-safe Loguru file logging."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _worker_environment(log_dir: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment["LOGS_DIR"] = str(log_dir)
    return environment


def test_parallel_processes_use_independent_log_files_without_rotation_errors(tmp_path):
    """Two concurrent processes must not rotate or rename one active file."""
    worker_script = r"""
import io
import os
import sys
import time
from contextlib import redirect_stderr
from pathlib import Path

ready_path = Path(sys.argv[1])
start_path = Path(sys.argv[2])
captured = io.StringIO()

with redirect_stderr(captured):
    from loguru import logger
    import src.api.main

    ready_path.write_text("ready", encoding="utf-8")
    while not start_path.exists():
        time.sleep(0.01)

    payload = "x" * (6 * 1024 * 1024)
    logger.info("worker {} {}", os.getpid(), payload)
    logger.info("worker {} {}", os.getpid(), payload)
    logger.complete()
    logger.remove()

print("PERMISSION_ERROR" if "PermissionError" in captured.getvalue() else "OK")
"""
    start_path = tmp_path / "start"
    ready_paths = [tmp_path / "ready-1", tmp_path / "ready-2"]
    workers = [
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                worker_script,
                str(ready_path),
                str(start_path),
            ],
            cwd=REPO_ROOT,
            env=_worker_environment(tmp_path),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for ready_path in ready_paths
    ]

    try:
        # Full-suite runs can have several Python workers starting at once;
        # allow process startup to finish without weakening the assertion.
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline and not all(path.exists() for path in ready_paths):
            time.sleep(0.05)
        assert all(path.exists() for path in ready_paths)

        start_path.write_text("start", encoding="utf-8")
        results = [worker.communicate(timeout=60) for worker in workers]
    finally:
        for worker in workers:
            if worker.poll() is None:
                worker.kill()
                worker.wait()

    for worker, (stdout, stderr) in zip(workers, results, strict=True):
        assert worker.returncode == 0, stderr
        assert stdout.strip() == "OK", stderr

    log_files = sorted(tmp_path.glob("aac_assistant_*.log"))
    assert len(log_files) == 2
    assert all("worker " in path.read_text(encoding="utf-8") for path in log_files)


def test_logging_setup_cleans_aged_process_logs(tmp_path):
    """Aged log files from prior process runs are removed without failing startup."""
    old_log = tmp_path / "aac_assistant_2020-01-01_111.log"
    old_error_log = tmp_path / "errors_2020-01-01_111.log"
    old_log.write_text("old application log", encoding="utf-8")
    old_error_log.write_text("old error log", encoding="utf-8")
    old_log_timestamp = time.time() - (8 * 24 * 60 * 60)
    old_error_timestamp = time.time() - (15 * 24 * 60 * 60)
    os.utime(old_log, (old_log_timestamp, old_log_timestamp))
    os.utime(old_error_log, (old_error_timestamp, old_error_timestamp))

    worker_script = r"""
import sys
from loguru import logger
import src.api.main

logger.complete()
logger.remove()
"""
    result = subprocess.run(
        [sys.executable, "-c", worker_script],
        cwd=REPO_ROOT,
        env=_worker_environment(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert not old_log.exists()
    assert not old_error_log.exists()


def test_redaction_covers_the_live_file_sink(tmp_path):
    """F09 residual: the patcher only rewrote ``record["message"]``, so the
    separately-rendered exception text carried a credential straight into the
    console and file sinks. The live sinks must show the masked form while the
    actionable context and the exception type survive.
    """
    worker_script = r"""
import sys
from loguru import logger
import src.api.main

CANARY = "sk-livesinkcanary9876"
try:
    raise RuntimeError(
        f'provider failed: {{"groq_api_key": "{CANARY}"}} Authorization: Bearer {CANARY}'
    )
except RuntimeError:
    logger.exception("upstream call failed")
try:
    raise ValueError(f"bad payload api_key={CANARY}")
except ValueError:
    logger.exception("validation failed")
logger.info("token={}", CANARY)
logger.complete()
logger.remove()
"""
    result = subprocess.run(
        [sys.executable, "-c", worker_script],
        cwd=REPO_ROOT,
        env=_worker_environment(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    log_files = sorted(tmp_path.glob("*.log"))
    assert log_files
    contents = "\n".join(path.read_text(encoding="utf-8") for path in log_files)

    # No sink — file or console — may carry the canary.
    assert "sk-livesinkcanary9876" not in contents
    assert "sk-livesinkcanary9876" not in result.stderr
    # The masked form and the actionable context survive the substitution.
    assert "RuntimeError: provider failed" in contents
    assert '{"groq_api_key": "***"}' in contents
    assert "Authorization: Bearer ***" in contents
    assert "ValueError: bad payload api_key=***" in contents
    assert "upstream call failed" in contents
    assert "validation failed" in contents


class TestRedactException:
    """F09 residual: the exception about to be rendered must be redacted too."""

    SECRET = "sk-supersecret123"

    @staticmethod
    def _redact(value: BaseException) -> BaseException:
        from src.api.logging_config import _redact_exception

        return _redact_exception(value)

    def test_message_bearing_exception_is_rebuilt_redacted(self) -> None:
        original = RuntimeError(f'provider said {{"groq_api_key": "{self.SECRET}"}}')
        safe = self._redact(original)

        assert isinstance(safe, RuntimeError)
        assert self.SECRET not in str(safe)
        assert "***" in str(safe)
        # The live exception the caller may still handle is never mutated.
        assert self.SECRET in str(original)

    def test_exception_without_secrets_is_returned_unchanged(self) -> None:
        original = ValueError("plain failure")

        assert self._redact(original) is original

    def test_exception_that_cannot_be_rebuilt_keeps_its_type_name(self) -> None:
        class _NeedsExtraArgs(Exception):
            def __init__(self, message: str, *, detail: str) -> None:  # noqa: D107
                super().__init__(message)
                self.detail = detail

        original = _NeedsExtraArgs(f"api_key={self.SECRET}", detail="x")
        safe = self._redact(original)

        assert isinstance(safe, RuntimeError)
        assert self.SECRET not in str(safe)
        assert "_NeedsExtraArgs" in str(safe)


class TestRedactMessage:
    """N2/D1: the log redactor must mask every known secret shape.

    Provider error paths and request logs emit JSON bodies, ``Authorization``
    headers and bare assignments; a missed shape means a real credential can
    reach a log sink.
    """

    SECRET = "sk-supersecret123"

    @staticmethod
    def _redact(message: str) -> str:
        from src.api.logging_config import _redact_message

        return _redact_message(message)

    @pytest.mark.parametrize(
        "rendered",
        [
            '{"groq_api_key": "sk-supersecret123"}',
            '{"openrouter_api_key":"sk-supersecret123"}',
            "{'password': 'sk-supersecret123'}",
            "X-Groq-API-Key: sk-supersecret123",
            "X-Groq-API-Key=sk-supersecret123",
            "Authorization: Bearer sk-supersecret123",
            "groq_api_key=sk-supersecret123",
            "api_key: sk-supersecret123",
            "password is sk-supersecret123",
        ],
    )
    def test_secret_shapes_are_masked(self, rendered: str) -> None:
        redacted = self._redact(rendered)
        assert self.SECRET not in redacted, redacted
        assert "***" in redacted

    def test_spanish_copula_is_masked(self) -> None:
        """Q11: the app is Spanish-first, so a translated log line rendering
        ``password es <value>`` must be masked like the English ``is`` form."""
        redacted = self._redact("password es sk-supersecret123")
        assert self.SECRET not in redacted, redacted
        assert "***" in redacted

    def test_secret_containing_asterisks_is_still_masked(self) -> None:
        """A real secret that itself contains ``***`` must not bypass the
        double-mask guard (the old substring check skipped it entirely)."""
        redacted = self._redact("my password is foo***bar baz")
        assert "foo***bar" not in redacted, redacted
        assert "***" in redacted

    def test_unquoted_json_scalars_keep_their_structure(self) -> None:
        """Masking an unquoted JSON scalar must not eat the closing brace."""
        redacted = self._redact('{"token": 12345678}')
        assert "12345678" not in redacted, redacted
        assert redacted.endswith("}"), redacted

    def test_already_masked_values_are_not_double_masked(self) -> None:
        once = self._redact('{"groq_api_key": "sk-supersecret123"}')
        twice = self._redact(once)
        assert twice == once, (once, twice)

    def test_long_messages_stay_truncated(self) -> None:
        redacted = self._redact("x" * 5000)
        assert len(redacted) <= 2020
        assert redacted.endswith("[truncated]")
