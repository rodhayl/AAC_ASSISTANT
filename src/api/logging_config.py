"""
Comprehensive logging configuration for AAC Assistant.
Logs all requests, responses, errors, and warnings to both console and file.
"""

import sys
from datetime import datetime

from loguru import logger

from src import config

# Use config for logs directory
LOGS_DIR = config.LOGS_DIR
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Log file path with date
LOG_FILE = LOGS_DIR / f"aac_assistant_{datetime.now().strftime('%Y-%m-%d')}.log"

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


def setup_logging():
    """Configure loguru for comprehensive logging."""
    # Remove default handler
    logger.remove()

    # Console handler - colored output
    logger.add(
        sys.stderr,
        format=LOG_FORMAT,
        level="DEBUG",
        colorize=True,
        backtrace=True,
        diagnose=True,
    )

    # File handler - all logs
    logger.add(
        LOG_FILE,
        format=LOG_FORMAT_FILE,
        level="DEBUG",
        rotation="10 MB",
        retention="7 days",
        compression="zip",
        backtrace=True,
        diagnose=True,
        enqueue=True,  # Thread-safe
    )

    # Separate error log file
    error_log = LOGS_DIR / f"errors_{datetime.now().strftime('%Y-%m-%d')}.log"
    logger.add(
        error_log,
        format=LOG_FORMAT_FILE,
        level="WARNING",
        rotation="10 MB",
        retention="14 days",
        compression="zip",
        backtrace=True,
        diagnose=True,
        enqueue=True,
    )

    logger.info(f"Logging initialized. Log file: {LOG_FILE}")
    return logger


def get_request_logger():
    """Get a logger specifically for HTTP request/response logging."""
    return logger.bind(context="HTTP")


# Initialize logging on import
setup_logging()
