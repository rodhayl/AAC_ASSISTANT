"""Shared vocabulary lists for symbol prediction and intent filtering.

Both the prediction engine (``standard library`` fallbacks) and the analytics
router (``pronouns``/``articles``/``nouns``/``places`` intent filters) match
against the same core-vocabulary words. Keeping the lists in one module means
a vocabulary change needs only one edit, and the two features cannot drift
apart.
"""

from __future__ import annotations

# Labels that match these substrings are internal dev artifacts, not real
# symbols. Reject them so they never reach the database or suggestions.
BAD_LABEL_SUBSTRINGS: tuple[str, ...] = (
    "frontend-",
    "comm-",
    "node_modules",
    "dist/",
    "build/",
    "src-",
)


def label_looks_bad(label: str) -> bool:
    """True when a label is clearly an internal path/id, not a real symbol."""
    lower = (label or "").strip().lower()
    if not lower:
        return True
    if len(lower) > 50:
        return True
    if any(p in lower for p in BAD_LABEL_SUBSTRINGS):
        return True
    if "/" in lower or "\\" in lower:
        return True
    # More than 3 hyphens is almost certainly a path/id, not a word.
    return lower.count("-") > 3

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

# ARASAAC's pictogram catalog uses a small closed set of grammatical categories
# for function words; every other category is nominal (people, animals, food,
# objects, places, ...). Matching nouns by keyword (``noun``, ``food``,
# ``object``, ...) misses the hundreds of ARASAAC noun categories, so the noun
# classification is inverted: enumerate the closed classes and treat every
# other category as a noun.

VERB_CATEGORIES: frozenset[str] = frozenset({"verb", "usual verbs"})

ADVERB_CATEGORIES: frozenset[str] = frozenset(
    {
        "adverb",
        "adverb of degree",
        "adverb of manner",
        "adverb of place",
        "adverb of time",
    }
)

ADJECTIVE_CATEGORIES: frozenset[str] = frozenset(
    {
        "adjective",
        "qualifying adjective",
        "comparative adjective",
        "demonstrative adjective",
        "indefinite adjective",
        "ordinal adjective",
        "possessive adjective",
    }
)

PRONOUN_CATEGORIES: frozenset[str] = frozenset(
    {
        "pronoun",
        "personal pronoun",
        "indefinite pronoun",
        "interrogative pronoun",
    }
)

ARTICLE_CATEGORIES: frozenset[str] = frozenset(
    {"article", "preposition", "conjunction"}
)

SYMBOL_CATEGORIES: frozenset[str] = frozenset(
    {"number", "letter", "alphabet", "orthographic sign", "interjection"}
)

NON_NOUN_CATEGORIES: frozenset[str] = (
    VERB_CATEGORIES
    | ADVERB_CATEGORIES
    | ADJECTIVE_CATEGORIES
    | PRONOUN_CATEGORIES
    | ARTICLE_CATEGORIES
    | SYMBOL_CATEGORIES
)

PLACE_CATEGORIES: frozenset[str] = frozenset(
    {
        "place",
        "building",
        "building facility",
        "building room",
        "commercial building",
        "cultural building",
        "educational building",
        "educational institution",
        "educational space",
        "industrial building",
        "public building",
        "religious building",
        "residential building",
        "service building",
        "facility",
        "entertainment facility",
        "recreational facility",
        "sports facility",
        "catering establishment",
        "hospital room",
        "medical center",
        "playground",
        "room",
        "city",
        "country",
        "continent",
        "region",
        "province",
        "spain province",
        "spain region",
        "urban area",
        "rural area",
        "mountain",
        "river",
        "sea and oceans",
        "planet",
        "landform",
        "natural habitat",
        "home",
        "route",
        "street furniture",
        "traffic signal",
        "beach",
        "worksite",
        "workplace",
        "swimming pool",
    }
)


def _category_key(category: str | None) -> str | None:
    return category.strip().casefold() if category else None


def category_is_verb(category: str | None) -> bool:
    """Return True when an ARASAAC category denotes a verb."""
    return _category_key(category) in VERB_CATEGORIES


def category_is_pronoun(category: str | None) -> bool:
    """Return True when an ARASAAC category denotes a pronoun."""
    return _category_key(category) in PRONOUN_CATEGORIES


def category_is_article(category: str | None) -> bool:
    """Return True when an ARASAAC category is an article/preposition/conjunction."""
    return _category_key(category) in ARTICLE_CATEGORIES


def category_is_noun(category: str | None) -> bool:
    """Return True for nominal ARASAAC categories (anything not closed-class)."""
    key = _category_key(category)
    return key is not None and key not in NON_NOUN_CATEGORIES


def category_is_place(category: str | None) -> bool:
    """Return True for ARASAAC categories denoting locations."""
    return _category_key(category) in PLACE_CATEGORIES


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
