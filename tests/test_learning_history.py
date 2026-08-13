from src.aac_app.services.learning.history import (
    MAX_CONVERSATION_HISTORY_ENTRIES,
    append_history_entry,
)


def test_append_history_entry_keeps_only_newest_entries():
    history = [{"id": index} for index in range(MAX_CONVERSATION_HISTORY_ENTRIES)]

    updated = append_history_entry(history, {"id": MAX_CONVERSATION_HISTORY_ENTRIES})

    assert len(updated) == MAX_CONVERSATION_HISTORY_ENTRIES
    assert updated[0]["id"] == 1
    assert updated[-1]["id"] == MAX_CONVERSATION_HISTORY_ENTRIES
