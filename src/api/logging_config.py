"""
Comprehensive logging configuration for AAC Assistant.
Logs all requests, responses, errors, and warnings to both console and file.
"""

import contextlib
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


def _is_production() -> bool:
    """Production check through the config layer so dotenv-set ENVIRONMENT is
    honored, not just the process environment (same precedence as config.get)."""
    env_name = str(config.get("ENVIRONMENT", "development")).strip().casefold()
    return env_name in {"production", "prod"}


_REDACT_PATTERNS: list = []  # compiled regexes, populated lazily


def _redact_message(msg: str) -> str:
    """Redact obvious secret assignments and truncate oversized content.

    Applied to every sink via a patcher so a stray secret in a log message
    never reaches console or file sinks (F09). Covers three shapes:
    * bare assignments ``key=value`` / ``key: value``
    * JSON pairs ``"key": "value"`` (quoted key + quoted value)
    * ``Bearer <token>`` and ``X-*-API-Key[:= ]value`` header forms.
    Length-truncation also bounds accidental verbatim child-message capture.
    """
    global _REDACT_PATTERNS
    import re as _re

    if not _REDACT_PATTERNS:
        keys = r"groq_api_key|openrouter_api_key|api_key|authorization|password|token"
        # Bare assignments should not double-mask an already handled
        # "Authorization: Bearer <token>" header — Bearer is handled above.
        keys_bare = r"groq_api_key|openrouter_api_key|api_key|password|token"
        _REDACT_PATTERNS = [
            # JSON quoted pair: "groq_api_key": "sk-..."
            _re.compile(rf'(?i)(\"(?:{keys})\"\s*:\s*)\"[^\"]*\"'),
            # Bearer token
            _re.compile(r"(?i)(Bearer\s+)\S+"),
            # X-*-API-Key header forms
            _re.compile(r"(?i)(X-[A-Za-z0-9_-]*API-?Key\s*[:=]\s*)\S+"),
            # Bare key=value / key: value (authorization excluded — Bearer covers it)
            _re.compile(rf"(?i)(?:\"?({keys_bare})\"?\s*[:=]\s*)\S+"),
        ]
    # JSON "key": "value" pairs first — preserve key casing, mask only the value.
    msg = _REDACT_PATTERNS[0].sub(r'\1"***"', msg)
    msg = _REDACT_PATTERNS[1].sub(r"\1***", msg)
    msg = _REDACT_PATTERNS[2].sub(r"\1***", msg)
    # Bare key=value / key: value last. Per-match guard: a value already
    # masked to "***" by an earlier pass must not be re-mangled (bare's \S+
    # would otherwise turn '"groq_api_key": "***"' into '"groq_api_key"=***'
    # or 'Bearer ***' into 'Bearer=*** ***'). Only bare assignments whose
    # captured value still looks like a secret are masked; an already-masked
    # message with an additional bare assignment (e.g. password=secret) is
    # still redacted.
    def _bare_repl(m: "_re.Match[str]") -> str:
        # group(0) contains key+delim+value; if value is already *** leave it
        if "***" in m.group(0):
            return m.group(0)
        return f"{m.group(1)}=***"

    msg = _REDACT_PATTERNS[3].sub(_bare_repl, msg)
    if len(msg) > 2000:
        msg = msg[:2000] + " ...[truncated]"
    return msg


def _redacting_patcher(record) -> None:
    """Loguru core patcher: rewrite each record's message through _redact_message.

    Loguru invokes the configure(patcher=...) callable with the record dict
    itself before any sink renders it.
    """
    with contextlib.suppress(Exception):  # noqa: SIM105
        record["message"] = _redact_message(record["message"])


def setup_logging():
    """Configure loguru for comprehensive logging."""
    # Remove default handler
    logger.remove()
    _cleanup_old_logs()

    is_prod = _is_production()
    level = "INFO" if is_prod else "DEBUG"
    diagnose = not is_prod

    # Every sink routes messages through the redaction patcher (F09):
    # credentials printed into a log line by any code path are masked before
    # any sink renders them.
    logger.configure(patcher=_redacting_patcher)

    # Console handler - colored output. Windowed PyInstaller processes expose
    # no stderr stream, so the file handlers below are the only sinks there.
    console_stream = sys.stderr or sys.__stderr__
    if console_stream is not None:
        logger.add(
            console_stream,
            format=LOG_FORMAT,
            level=level,
            colorize=True,
            backtrace=diagnose,
            diagnose=diagnose,
        )

    # File handler - all logs. Retention is explicit rather than in-place
    # rotation, because every process writes to its own active file.
    # Add rotation + redaction in prod.
    logger.add(
        LOG_FILE,
        format=LOG_FORMAT_FILE,
        level=level,
        retention=_cleanup_old_logs,
        rotation="20 MB",
        backtrace=diagnose,
        diagnose=diagnose,
        enqueue=True,  # Thread-safe
    )

    # Separate error log file
    logger.add(
        ERROR_LOG_FILE,
        format=LOG_FORMAT_FILE,
        level="WARNING",
        retention=_cleanup_old_logs,
        rotation="20 MB",
        backtrace=diagnose,
        diagnose=diagnose,
        enqueue=True,
    )

    logger.info(f"Logging initialized. Log file: {LOG_FILE}")
    return logger


# Initialize logging on import
setup_logging()
