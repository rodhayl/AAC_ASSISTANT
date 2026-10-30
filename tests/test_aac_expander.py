"""
Tests for AAC Expander Service
Tests grammar expansion rules, article insertion, verb conjugation, etc.
"""

import pytest

from src.aac_app.services.aac_expander_service import AACExpanderService


class TestAACExpander:
    """Test suite for AACExpanderService."""

    @pytest.fixture(autouse=True)
    def setup_expander(self):
        self.expander = AACExpanderService()
        yield
        self.expander.clear_cache()

    def test_article_insertion_want_cookie(self):
        """Test article insertion for 'want cookie' -> 'want a cookie'."""
        symbols = [
            {"label": "want", "category": "action"},
            {"label": "cookie", "category": "object"},
        ]
        raw_gloss = "want cookie"

        result = self.expander.expand(symbols, raw_gloss)

        assert "want a cookie" in result["expanded_text"].lower()
        assert "article_insertion" in result["transformations"]
        assert result["confidence"] > 0.6

    def test_article_insertion_an_before_vowel(self):
        """Test 'an' is used before vowel sounds."""
        symbols = [
            {"label": "want", "category": "action"},
            {"label": "apple", "category": "object"},
        ]
        raw_gloss = "want apple"

        result = self.expander.expand(symbols, raw_gloss)

        assert "want an apple" in result["expanded_text"].lower()
        assert "article_insertion" in result["transformations"]

    def test_pronoun_normalization_me_want(self):
        """Test 'me want' -> 'I want'."""
        symbols = [
            {"label": "me", "category": "person"},
            {"label": "want", "category": "action"},
            {"label": "cookie", "category": "object"},
        ]
        raw_gloss = "me want cookie"

        result = self.expander.expand(symbols, raw_gloss)

        assert result["expanded_text"].lower().startswith("i want")
        assert "pronoun_fix" in result["transformations"]

    def test_verb_conjugation_he_go(self):
        """Test 'he go' -> 'he goes'."""
        symbols = [
            {"label": "he", "category": "person"},
            {"label": "go", "category": "action"},
            {"label": "home", "category": "place"},
        ]
        raw_gloss = "he go home"

        result = self.expander.expand(symbols, raw_gloss)

        assert "he goes" in result["expanded_text"].lower()
        assert "verb_conjugation" in result["transformations"]

    def test_verb_conjugation_she_have(self):
        """Test 'she have' -> 'she has' (irregular verb)."""
        symbols = [
            {"label": "she", "category": "person"},
            {"label": "have", "category": "action"},
            {"label": "toy", "category": "object"},
        ]
        raw_gloss = "she have toy"

        result = self.expander.expand(symbols, raw_gloss)

        assert "she has" in result["expanded_text"].lower()
        assert "verb_conjugation" in result["transformations"]

    def test_tense_marker_past_yesterday(self):
        """Test past tense with 'yesterday eat' -> 'I ate yesterday'."""
        symbols = [
            {"label": "yesterday", "category": "time"},
            {"label": "eat", "category": "action"},
        ]
        raw_gloss = "yesterday eat"

        result = self.expander.expand(symbols, raw_gloss)

        assert "ate yesterday" in result["expanded_text"].lower()
        assert "tense_conjugation" in result["transformations"]
        assert result["confidence"] > 0.6

    def test_tense_marker_past_irregular_go(self):
        """Test past tense with irregular verb: 'yesterday go' -> 'I went yesterday'."""
        symbols = [
            {"label": "yesterday", "category": "time"},
            {"label": "go", "category": "action"},
        ]
        raw_gloss = "yesterday go"

        result = self.expander.expand(symbols, raw_gloss)

        assert "went yesterday" in result["expanded_text"].lower()
        assert "tense_conjugation" in result["transformations"]

    def test_tense_marker_future_tomorrow(self):
        """Test future tense with 'tomorrow play' -> 'I will play tomorrow'."""
        symbols = [
            {"label": "tomorrow", "category": "time"},
            {"label": "play", "category": "action"},
        ]
        raw_gloss = "tomorrow play"

        result = self.expander.expand(symbols, raw_gloss)

        assert "will play tomorrow" in result["expanded_text"].lower()
        assert "tense_conjugation" in result["transformations"]
        assert result["confidence"] > 0.6

    def test_tense_marker_past_regular_verb(self):
        """Test past tense with regular verb: 'yesterday play' -> 'I played yesterday'."""
        symbols = [
            {"label": "yesterday", "category": "time"},
            {"label": "play", "category": "action"},
        ]
        raw_gloss = "yesterday play"

        result = self.expander.expand(symbols, raw_gloss)

        assert "played yesterday" in result["expanded_text"].lower()
        assert "tense_conjugation" in result["transformations"]

    def test_question_formation_what_time(self):
        """Test question formation with semantic analysis."""
        symbols = [
            {"label": "what", "category": "question"},
            {"label": "time", "category": "object"},
            {"label": "lunch", "category": "object"},
        ]
        raw_gloss = "what time lunch"
        semantic_analysis = {"intent": "question", "confidence": 0.8}

        result = self.expander.expand(symbols, raw_gloss, semantic_analysis)

        assert result["expanded_text"].endswith("?")
        assert "what" in result["expanded_text"].lower()

    def test_question_formation_where_mom(self):
        """Test 'where mom' -> 'Where is mom?'."""
        symbols = [
            {"label": "where", "category": "question"},
            {"label": "mom", "category": "person"},
        ]
        raw_gloss = "where mom"
        semantic_analysis = {"intent": "question", "confidence": 0.85}

        result = self.expander.expand(symbols, raw_gloss, semantic_analysis)

        assert result["expanded_text"].endswith("?")
        assert "where" in result["expanded_text"].lower()
        assert "question" in result["transformations"] or result[
            "expanded_text"
        ].endswith("?")

    def test_common_expansion_single_word_happy(self):
        """Test single-word common expansion: 'happy' -> 'I feel happy.'."""
        symbols = [{"label": "happy", "category": "feeling"}]
        raw_gloss = "happy"

        result = self.expander.expand(symbols, raw_gloss)

        assert "feel happy" in result["expanded_text"].lower()
        assert "common_expansion" in result["transformations"]
        assert result["confidence"] == 0.95

    def test_common_expansion_single_word_help(self):
        """Test 'help' -> 'I need help.'."""
        symbols = [{"label": "help", "category": "action"}]
        raw_gloss = "help"

        result = self.expander.expand(symbols, raw_gloss)

        assert "need help" in result["expanded_text"].lower()
        assert "common_expansion" in result["transformations"]

    def test_capitalization_and_punctuation(self):
        """Test that output is capitalized and has punctuation."""
        symbols = [
            {"label": "I", "category": "person"},
            {"label": "want", "category": "action"},
            {"label": "cookie", "category": "object"},
        ]
        raw_gloss = "i want cookie"

        result = self.expander.expand(symbols, raw_gloss)

        # Should start with capital letter
        assert result["expanded_text"][0].isupper()
        # Should end with punctuation
        assert result["expanded_text"][-1] in ".!?"

    def test_cache_hit_same_symbols(self):
        """Test that cache works for repeated symbol sequences."""
        symbols = [
            {"label": "want", "category": "action"},
            {"label": "cookie", "category": "object"},
        ]
        raw_gloss = "want cookie"

        # First call
        result1 = self.expander.expand(symbols, raw_gloss)

        # Second call should hit cache
        result2 = self.expander.expand(symbols, raw_gloss)

        assert result1["expanded_text"] == result2["expanded_text"]
        assert result1["transformations"] == result2["transformations"]

    def test_empty_symbols_returns_empty(self):
        """Test that empty symbols returns empty result."""
        symbols = []
        raw_gloss = ""

        result = self.expander.expand(symbols, raw_gloss)

        assert result["expanded_text"] == ""
        assert result["confidence"] == 0.0
        assert result["transformations"] == []

    def test_multiple_transformations_increase_confidence(self):
        """Test that multiple transformations increase confidence."""
        symbols = [
            {"label": "me", "category": "person"},
            {"label": "want", "category": "action"},
            {"label": "cookie", "category": "object"},
        ]
        raw_gloss = "me want cookie"

        result = self.expander.expand(symbols, raw_gloss)

        # Should have pronoun fix + article insertion
        assert len(result["transformations"]) >= 2
        assert result["confidence"] > 0.7

    def test_go_to_the_location(self):
        """Test 'go store' -> 'go to the store'."""
        symbols = [
            {"label": "go", "category": "action"},
            {"label": "store", "category": "place"},
        ]
        raw_gloss = "go store"

        result = self.expander.expand(symbols, raw_gloss)

        assert "to the" in result["expanded_text"].lower()
        assert "article_insertion" in result["transformations"]

    def test_complex_sentence_i_want_cookie(self):
        """Test complete expansion of 'I want cookie'."""
        symbols = [
            {"label": "I", "category": "person"},
            {"label": "want", "category": "action"},
            {"label": "cookie", "category": "object"},
        ]
        raw_gloss = "I want cookie"

        result = self.expander.expand(symbols, raw_gloss)

        text = result["expanded_text"].lower()
        assert "i want" in text
        assert "cookie" in text
        # Should add article
        assert "a cookie" in text or "cookie." in text

    def test_case_insensitive_processing(self):
        """Test that expansion works regardless of input case."""
        symbols_upper = [
            {"label": "WANT", "category": "action"},
            {"label": "COOKIE", "category": "object"},
        ]
        raw_gloss_upper = "WANT COOKIE"

        symbols_lower = [
            {"label": "want", "category": "action"},
            {"label": "cookie", "category": "object"},
        ]
        raw_gloss_lower = "want cookie"

        result_upper = self.expander.expand(symbols_upper, raw_gloss_upper)
        self.expander.clear_cache()  # Clear cache between tests
        result_lower = self.expander.expand(symbols_lower, raw_gloss_lower)

        # Should produce similar results (both capitalized and punctuated)
        assert result_upper["expanded_text"][0].isupper()
        assert result_lower["expanded_text"][0].isupper()

    def test_greeting_expansion(self):
        """Test greeting expansion: 'hello' -> 'Hello.'."""
        symbols = [{"label": "hello", "category": "general"}]
        raw_gloss = "hello"

        result = self.expander.expand(symbols, raw_gloss)

        assert result["expanded_text"] == "Hello."
        assert "common_expansion" in result["transformations"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
