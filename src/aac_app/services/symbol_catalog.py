"""Shared vocabulary lists for symbol prediction and intent filtering.

Both the prediction engine (``standard library`` fallbacks) and the analytics
router (``pronouns``/``articles``/``nouns``/``places`` intent filters) match
against the same core-vocabulary words. Keeping the lists in one module means
a vocabulary change needs only one edit, and the two features cannot drift
apart.
"""

from __future__ import annotations

EN_PRONOUNS: tuple[str, ...] = (
    "I",
    "you",
    "he",
    "she",
    "it",
    "we",
    "they",
    "me",
    "my",
    "your",
)

ES_PRONOUNS: tuple[str, ...] = (
    "yo",
    "tú",
    "tu",
    "me",
    "mi",
    "nosotros",
    "nosotras",
    "ellos",
    "ellas",
)

EN_ARTICLES: tuple[str, ...] = (
    "the",
    "a",
    "an",
    "to",
    "in",
    "on",
)

ES_ARTICLES: tuple[str, ...] = (
    "el",
    "la",
    "un",
    "una",
    "a",
    "en",
)

# Additional pronouns used only by the analytics intent filter (the prediction
# fallback keeps its compact list to control suggestion ordering).
ANALYTICS_EXTRA_EN_PRONOUNS: tuple[str, ...] = (
    "his",
    "her",
    "our",
    "their",
)

ANALYTICS_EXTRA_ES_PRONOUNS: tuple[str, ...] = (
    "él",
    "ella",
    "mis",
)

# Additional articles/prepositions used only by the analytics intent filter.
ANALYTICS_EXTRA_EN_ARTICLES: tuple[str, ...] = (
    "is",
    "are",
    "am",
    "was",
    "were",
    "at",
    "for",
    "of",
    "with",
)

ANALYTICS_EXTRA_ES_ARTICLES: tuple[str, ...] = (
    "los",
    "las",
    "unos",
    "unas",
    "es",
    "son",
    "está",
    "están",
    "de",
    "con",
    "para",
    "por",
)

# Common verbs and function words used by the prediction ``standard_library``
# fallback (in priority order) when the user history has no signal yet.
EN_STANDARD_VERBS: tuple[str, ...] = (
    "want",
    "go",
    "like",
    "help",
    "stop",
    "eat",
    "drink",
    "play",
    "see",
    "have",
)

ES_STANDARD_VERBS: tuple[str, ...] = (
    "quiero",
    "ir",
    "ayudar",
    "parar",
    "comer",
    "beber",
    "jugar",
    "ver",
    "tener",
)

EN_STANDARD_FUNCTION_WORDS: tuple[str, ...] = (
    "please",
    "more",
    "no",
    "yes",
    "the",
    "a",
    "an",
    "to",
    "in",
    "on",
)

ES_STANDARD_FUNCTION_WORDS: tuple[str, ...] = (
    "por favor",
    "más",
    "no",
    "sí",
    "a",
    "el",
    "la",
    "un",
    "una",
)

# Category keywords (substring-matched, lowercased) used to split fallback
# suggestions into nouns and other words, and by the analytics noun filter.
NOUN_CATEGORY_KEYWORDS: tuple[str, ...] = (
    "food",
    "drink",
    "toy",
    "animal",
    "place",
    "object",
    "noun",
)

# Category keywords used by the analytics ``places`` intent filter.
PLACE_CATEGORY_KEYWORDS: tuple[str, ...] = (
    "place",
    "places",
    "location",
    "room",
    "home",
    "school",
    "city",
    "country",
    "nature",
    "transport",
    "vehicle",
)

# Additional noun categories matched only by the analytics noun filter.
ANALYTICS_EXTRA_NOUN_CATEGORIES: tuple[str, ...] = (
    "person",
    "body",
    "clothing",
    "vehicle",
    "home",
    "school",
    "nature",
    "generated",
)


def standard_library_labels(lang_code: str) -> list[str]:
    """Return the core-vocabulary labels for the prediction fallback.

    The order is intentional: pronouns/core first, then verbs, then function
    words, matching the historical fallback ordering.
    """
    if lang_code == "es":
        return [
            *ES_PRONOUNS,
            *ES_STANDARD_VERBS,
            *ES_STANDARD_FUNCTION_WORDS,
        ]
    return [
        *EN_PRONOUNS,
        *EN_STANDARD_VERBS,
        *EN_STANDARD_FUNCTION_WORDS,
    ]


def intent_pronouns(lang_code: str) -> list[str]:
    """Return the analytics ``pronouns`` filter labels for a language."""
    if lang_code.startswith("es"):
        return [*ES_PRONOUNS, *ANALYTICS_EXTRA_ES_PRONOUNS]
    return [*EN_PRONOUNS, *ANALYTICS_EXTRA_EN_PRONOUNS]


def intent_articles(lang_code: str) -> list[str]:
    """Return the analytics ``articles`` filter labels for a language."""
    if lang_code.startswith("es"):
        return [*ES_ARTICLES, *ANALYTICS_EXTRA_ES_ARTICLES]
    return [*EN_ARTICLES, *ANALYTICS_EXTRA_EN_ARTICLES]
