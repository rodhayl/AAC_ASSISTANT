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
            # Quoted pair with an unquoted-or-quoted scalar: JSON ``"key": "v"``
            # and Python-repr ``'key': 'v'``, plus 123 / true / null. Must not
            # consume trailing braces/commas so '{"token": 123}' keeps its '}'.
            _re.compile(
                rf"""(?i)(['\"](?:{keys})['\"]\s*:\s*)(?:'[^']*'|"[^"]*"|true|false|null|-?\d+(?:\.\d+)?)"""
            ),
            # Bearer token
            _re.compile(r"(?i)(Bearer\s+)\S+"),
            # X-*-API-Key header forms
            _re.compile(r"(?i)(X-[A-Za-z0-9_-]*API-?Key\s*[:=]\s*)\S+"),
            # Bare key=value / key: value (authorization excluded — Bearer covers it)
            _re.compile(rf"(?i)(['\"]?({keys_bare})['\"]?\s*[:=]\s*)(\S+)"),
            # "password is <value>" copula shape — same guard semantics as bare.
            # Covers the Spanish-first renderings too (`password es <value>`),
            # since a translated log line must not leak a credential (Q11).
            # Scope: only the copula is localized. The key set stays the code
            # identifiers that actually appear in log messages (English);
            # localized UI copy is never logged, so a Spanish key spelling such
            # as `contraseña` is out of scope by evidence, not an oversight.
            _re.compile(rf"(?i)(['\"]?({keys_bare})['\"]?\s+(?:is|es)\s+)(\S+)"),
        ]
    # JSON "key": value pairs first — preserve key casing, mask only the value.
    # Unquoted numerics/booleans are quoted as "***" so the shape stays JSON-like.
    msg = _REDACT_PATTERNS[0].sub(r'\1"***"', msg)
    msg = _REDACT_PATTERNS[1].sub(r"\1***", msg)
    msg = _REDACT_PATTERNS[2].sub(r"\1***", msg)
    # Bare key=value / key: value last. Per-match guard: a value already
    # masked to "***" by an earlier pass must not be re-mangled (bare's \S+
    # would otherwise turn '"groq_api_key": "***"' into '"groq_api_key"=***'
    # or 'Bearer ***' into 'Bearer=*** ***'). Only bare assignments whose
    # captured value still looks like a secret are masked; an already-masked
    # message with an additional bare assignment (e.g. password=secret) is
    # still redacted. Guard on exact value, not substring — a real secret
    # containing "***" must still be masked. The bare \S+ also captures
    # trailing JSON punctuation ('"***"}' / '"***",'); strip it before the
    # exact check so a JSON-masked key is recognised as already handled.
    def _bare_repl(m: "_re.Match[str]") -> str:
        try:
            value = m.group(3) if m.lastindex and m.lastindex >= 3 else m.group(2)
            prefix = m.group(1)
        except IndexError:
            return m.group(0)
        # Strip surrounding quotes and trailing JSON punctuation (},],")
        stripped = value.strip().lstrip("\"'").rstrip("\"',}];:")
        if stripped == "***":
            return m.group(0)
        # Also handle already-quoted masked value '"***"' without trailing brace
        if value.strip().strip("\"'") == "***":
            return m.group(0)
        return f"{prefix}***"

    msg = _REDACT_PATTERNS[3].sub(_bare_repl, msg)
    msg = _REDACT_PATTERNS[4].sub(_bare_repl, msg)
    if len(msg) > 2000:
        msg = msg[:2000] + " ...[truncated]"
    return msg


def _redact_exception(value: BaseException) -> BaseException:
    """Return a leak-free stand-in for an exception about to be rendered.

    ``record["exception"]`` is rendered separately from the message, so a
    provider error that echoes a credential in its own text reached every sink
    verbatim even with the message patched (F09 residual, found by the live-sink
    canary probe). The live exception object is never mutated — the caller may
    still be handling it — a redacted copy is substituted for rendering only.
    """
    rendered = str(value)
    redacted = _redact_message(rendered)
    if redacted == rendered:
        return value
    try:
        return type(value)(redacted)
    except Exception:
        # Exceptions with required extra constructor args (JSONDecodeError,
        # HTTPStatusError, ...) cannot be rebuilt from the message alone; keep
        # the type name visible in the text instead of the raw message.
        return RuntimeError(f"{type(value).__name__}: {redacted}")


def _redacting_patcher(record) -> None:
    """Loguru core patcher: redact the message and any rendered exception.

    Loguru invokes the configure(patcher=...) callable with the record dict
    itself before any sink renders it.
    """
    with contextlib.suppress(Exception):  # noqa: SIM105
        record["message"] = _redact_message(record["message"])
    exception = record.get("exception")
    if exception is not None:
        with contextlib.suppress(Exception):  # noqa: SIM105
            record["exception"] = exception._replace(
                value=_redact_exception(exception.value)
            )


def setup_logging():
    """Configure loguru for comprehensive logging."""
    # Remove default handler
    logger.remove()
    _cleanup_old_logs()

    is_prod = _is_production()
    level = "INFO" if is_prod else "DEBUG"
    diagnose = not is_prod

    # Every sink routes records through the redaction patcher (F09): both the
    # message and the separately-rendered exception text are masked before any
    # sink renders them.
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
