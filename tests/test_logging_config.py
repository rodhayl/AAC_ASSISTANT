"""Regression tests for process-safe Loguru file logging."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

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
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and not all(path.exists() for path in ready_paths):
            time.sleep(0.05)
        assert all(path.exists() for path in ready_paths)

        start_path.write_text("start", encoding="utf-8")
        results = [worker.communicate(timeout=30) for worker in workers]
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
