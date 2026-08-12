"""
Comprehensive logging configuration for AAC Assistant.
Logs all requests, responses, errors, and warnings to both console and file.
"""

import os
import sys
import time
from datetime import datetime

from loguru import logger

from src import config

# Use config for logs directory
LOGS_DIR = config.LOGS_DIR
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Each process owns its active files. Windows cannot rename an open file, so a
# shared date-only path makes Loguru's size rotation race with other app
# instances (or a test runner) and emit a non-fatal PermissionError.
LOG_DATE = datetime.now().strftime("%Y-%m-%d")
PROCESS_ID = str(os.getpid())
LOG_FILE = LOGS_DIR / f"aac_assistant_{LOG_DATE}_{PROCESS_ID}.log"
ERROR_LOG_FILE = LOGS_DIR / f"errors_{LOG_DATE}_{PROCESS_ID}.log"
LOG_RETENTION_SECONDS = 7 * 24 * 60 * 60
ERROR_LOG_RETENTION_SECONDS = 14 * 24 * 60 * 60

# Custom format for detailed logging
LOG_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
    "<level>{message}</level>"
)

LOG_FORMAT_FILE = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
    "{level: <8} | "
    "{name}:{function}:{line} | "
    "{message}"
)


def _cleanup_old_logs(_logs: list[str] | None = None) -> None:
    """Remove aged logs from all process-specific files.

    Loguru's built-in retention only sees files matching the active sink path,
    which would limit cleanup to the current PID. Scan the unchanged log
    directory instead and ignore files that another process still holds.
    A single os.scandir pass replaces per-pattern globs so process startup
    stays fast even when the log directory has accumulated many files.
    """
    now = time.time()
    retention_rules = (
        ("aac_assistant_", LOG_RETENTION_SECONDS),
        ("errors_", ERROR_LOG_RETENTION_SECONDS),
    )
    try:
        with os.scandir(LOGS_DIR) as iterator:
            entries = list(iterator)
    except OSError:
        return
    for entry in entries:
        try:
            if not entry.is_file():
                continue
            name = entry.name
            for prefix, retention_seconds in retention_rules:
                if not name.startswith(prefix) or ".log" not in name:
                    continue
                try:
                    if entry.stat().st_mtime <= now - retention_seconds:
                        os.unlink(entry.path)
                except OSError:
                    # A different process may still have an aged file open on
                    # Windows. It will be retried by a later process startup.
                    continue
                break
        except OSError:
            continue


def setup_logging():
    """Configure loguru for comprehensive logging."""
    # Remove default handler
    logger.remove()
    _cleanup_old_logs()

    # Console handler - colored output. Windowed PyInstaller processes expose
    # no stderr stream, so the file handlers below are the only sinks there.
    console_stream = sys.stderr or sys.__stderr__
    if console_stream is not None:
        logger.add(
            console_stream,
            format=LOG_FORMAT,
            level="DEBUG",
            colorize=True,
            backtrace=True,
            diagnose=True,
        )

    # File handler - all logs. Retention is explicit rather than in-place
    # rotation, because every process writes to its own active file.
    logger.add(
        LOG_FILE,
        format=LOG_FORMAT_FILE,
        level="DEBUG",
        retention=_cleanup_old_logs,
        backtrace=True,
        diagnose=True,
        enqueue=True,  # Thread-safe
    )

    # Separate error log file
    logger.add(
        ERROR_LOG_FILE,
        format=LOG_FORMAT_FILE,
        level="WARNING",
        retention=_cleanup_old_logs,
        backtrace=True,
        diagnose=True,
        enqueue=True,
    )

    logger.info(f"Logging initialized. Log file: {LOG_FILE}")
    return logger


# Initialize logging on import
setup_logging()
