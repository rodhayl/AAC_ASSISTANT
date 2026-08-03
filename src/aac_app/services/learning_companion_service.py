"""Compatibility imports for the split learning companion service."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.orm import Session

from ..db import get_session as _get_session
from .learning import (
    AAC_SYSTEM_PROMPT,
    AACPromptProfile,
    _strip_reasoning,
)
from .learning import (
    LearningCompanionService as _LearningCompanionService,
)

get_session = _get_session


class LearningCompanionService(_LearningCompanionService):
    """Backward-compatible facade preserving the historical import path."""

    @contextmanager
    def _session_scope(self, db: Session | None) -> Iterator[Session]:
        if db is not None:
            yield db
            return
        with get_session() as session:
            yield session


__all__ = [
    "AACPromptProfile",
    "AAC_SYSTEM_PROMPT",
    "LearningCompanionService",
    "_strip_reasoning",
    "get_session",
]
