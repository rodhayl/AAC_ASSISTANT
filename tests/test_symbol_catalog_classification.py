"""Focused tests for ARASAAC category part-of-speech classification."""

from src.aac_app.services.symbol_catalog import (
    category_is_article,
    category_is_noun,
    category_is_place,
    category_is_pronoun,
    category_is_verb,
)


def test_verb_classification_excludes_adverbs():
    assert category_is_verb("verb")
    assert category_is_verb("usual verbs")
    assert category_is_verb("VERB")
    assert not category_is_verb("adverb")
    assert not category_is_verb("adverb of place")


def test_pronoun_classification():
    assert category_is_pronoun("pronoun")
    assert category_is_pronoun("personal pronoun")
    assert category_is_pronoun("interrogative pronoun")


def test_article_classification():
    assert category_is_article("article")
    assert category_is_article("preposition")
    assert category_is_article("conjunction")


def test_noun_classification_is_inverted():
    # ARASAAC noun categories are everything that is not closed-class.
    assert category_is_noun("fruit")
    assert category_is_noun("human anatomy")
    assert category_is_noun("clothes")
    assert category_is_noun("building room")
    assert category_is_noun("noun")
    # Closed-class categories must not be treated as nouns.
    assert not category_is_noun("verb")
    assert not category_is_noun("pronoun")
    assert not category_is_noun("personal pronoun")
    assert not category_is_noun("adverb")
    assert not category_is_noun("qualifying adjective")
    assert not category_is_noun("article")
    assert not category_is_noun("number")


def test_place_classification():
    assert category_is_place("place")
    assert category_is_place("building room")
    assert category_is_place("city")
    assert category_is_place("country")
    assert not category_is_place("fruit")


def test_none_categories_are_not_classified():
    assert not category_is_noun(None)
    assert not category_is_verb(None)
    assert not category_is_place("")
