import os

from slowapi import Limiter
from slowapi.util import get_remote_address


def is_testing() -> bool:
    return os.getenv("TESTING", "0") == "1" or os.getenv("ENVIRONMENT") == "testing"


def exempt_when_testing() -> bool:
    return is_testing()


limiter = Limiter(key_func=get_remote_address)
