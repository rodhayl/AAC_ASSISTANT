"""Bounded conversation-history helpers for learning sessions."""

from __future__ import annotations

from typing import Any

MAX_CONVERSATION_HISTORY_ENTRIES = 50


def append_history_entry(history: list[dict[str, Any]] | None, entry: dict[str, Any]) -> list[dict[str, Any]]:
    """Append an entry and retain only the newest bounded window."""
    updated = list(history or [])
    updated.append(entry)
    return updated[-MAX_CONVERSATION_HISTORY_ENTRIES:]
