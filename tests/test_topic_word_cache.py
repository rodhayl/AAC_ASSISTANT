"""The topic-word cache is bounded and self-purging (PROMPT_13 D8).

``_topics_word_cache`` is keyed by the user-controlled topic string; expired
entries (TTL 1h) were only ever removed by a re-lookup of the same key, so a
bombardment of unique topics grew process memory monotonically. Insertions
now purge expired rows and evict the oldest beyond the size cap.
"""

import pytest

from src.aac_app.services import prediction_service as mod

pytestmark = pytest.mark.usefixtures("_clear_topic_word_cache")


@pytest.fixture(autouse=True)
def _clear_topic_word_cache():
    with mod._topics_word_lock:
        mod._topics_word_cache.clear()
    yield
    with mod._topics_word_lock:
        mod._topics_word_cache.clear()


def _fetcher_echo(_language: str, topic: str) -> list[str]:
    """Deterministic fetcher: one fresh word per topic."""
    return [f"word-for-{topic.replace(' ', '_')}"]


def test_mass_insertion_stays_bounded(monkeypatch):
    """Unique-topic bombardment cannot grow the cache beyond the cap."""
    monkeypatch.setattr(mod, "_TOPIC_WORD_CACHE_MAXSIZE", 50)
    for i in range(300):
        mod._cached_topic_words("en", f"unique topic {i}", _fetcher_echo)

    with mod._topics_word_lock:
        assert len(mod._topics_word_cache) <= 50
        # The newest entries survive (LRU-by-insertion eviction).
        assert ("en", "unique topic 299") in mod._topics_word_cache


def test_expired_entries_are_purged_on_insertion(monkeypatch):
    """Entries past the TTL are removed by the next insert's purge sweep."""
    monkeypatch.setattr(mod, "_TOPIC_WORD_CACHE_MAXSIZE", 1000)
    fake_now = {"t": 1000.0}
    monkeypatch.setattr(mod.time, "monotonic", lambda: fake_now["t"])

    mod._cached_topic_words("en", "old topic", _fetcher_echo)
    # Advance far beyond the 1h TTL.
    fake_now["t"] += mod._TOPIC_WORD_TTL_SECONDS + 1
    mod._cached_topic_words("en", "new topic", _fetcher_echo)

    with mod._topics_word_lock:
        assert ("en", "old topic") not in mod._topics_word_cache
        assert ("en", "new topic") in mod._topics_word_cache


def test_hit_within_ttl_does_not_recall_fetcher(monkeypatch):
    """A live entry serves repeated lookups without re-running the LLM call."""
    calls: list[str] = []

    def counting_fetcher(_language: str, topic: str) -> list[str]:
        calls.append(topic)
        return ["hola", "mundo"]

    first = mod._cached_topic_words("es", "  Viaje  ", counting_fetcher)
    second = mod._cached_topic_words("es", "viaje", counting_fetcher)

    assert first == ("hola", "mundo")
    assert second == first  # same normalized topic, single fetch
    assert len(calls) == 1
