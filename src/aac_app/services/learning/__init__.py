"""Focused learning service package."""

from .common import AAC_SYSTEM_PROMPT, AACPromptProfile, _strip_reasoning
from .service import LearningCompanionService

__all__ = [
    "AACPromptProfile",
    "AAC_SYSTEM_PROMPT",
    "LearningCompanionService",
    "_strip_reasoning",
]
