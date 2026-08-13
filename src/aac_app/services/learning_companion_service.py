"""Compatibility imports for the split learning companion service."""

from contextlib import contextmanager

from ..db import get_session as _get_session
from ..db import session_scope
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

    @staticmethod
    @contextmanager
    def _session_scope(db):
        """Preserve the historical get_session monkeypatch seam."""
        with session_scope(db, session_factory=get_session) as session:
            yield session


__all__ = [
    "AACPromptProfile",
    "AAC_SYSTEM_PROMPT",
    "LearningCompanionService",
    "_strip_reasoning",
    "get_session",
]
