"""
Tests for Symbol Semantics Service
Tests intent detection, semantic role mapping, and context generation for AAC symbols.
"""

import pytest

from src.aac_app.services.symbol_semantics import SymbolSemantics


class TestSymbolSemantics:
    """Test suite for SymbolSemantics service."""

    @pytest.fixture(autouse=True)
    def setup_semantics(self):
        """Set up test fixtures."""
        self.semantics = SymbolSemantics()
        yield

    def test_request_intent_with_i_want_pattern(self):
        """Test detection of request intent with 'I want X' pattern."""
        symbols = [
            {"label": "I", "category": "person"},
            {"label": "want", "category": "action"},
            {"label": "cookie", "category": "object"},
        ]

        result = self.semantics.analyze_sequence(symbols)

        assert result["intent"] == "request"
        assert result["confidence"] > 0.7
        assert result["symbol_count"] == 3
        assert (
            "agent" in result["semantic_roles"] or "pronoun" in result["semantic_roles"]
        )
        assert (
            "verb" in result["semantic_roles"] or "activity" in result["semantic_roles"]
        )
        assert "REQUEST" in result["summary"]

    def test_question_intent_with_what_keyword(self):
        """Test detection of question intent with 'what' keyword."""
        symbols = [
            {"label": "what", "category": "question"},
            {"label": "time", "category": "object"},
            {"label": "lunch", "category": "object"},
        ]

        result = self.semantics.analyze_sequence(symbols)

        assert result["intent"] == "question"
        assert result["confidence"] > 0.7
        assert "what" in [s["label"].lower() for s in symbols]

    def test_feeling_intent_with_happy(self):
        """Test detection of feeling intent with emotion words."""
        symbols = [
            {"label": "I", "category": "person"},
            {"label": "happy", "category": "feeling"},
        ]

        result = self.semantics.analyze_sequence(symbols)

        assert result["intent"] == "feeling"
        assert result["confidence"] > 0.7
        assert len(result["unique_categories"]) >= 1

    def test_greeting_intent(self):
        """Test detection of greeting intent."""
        symbols = [{"label": "hello", "category": "general"}]

        result = self.semantics.analyze_sequence(symbols)

        assert result["intent"] == "greeting"
        assert result["confidence"] > 0.7

    def test_statement_fallback_for_unknown_pattern(self):
        """Test fallback to statement intent for unrecognized patterns."""
        symbols = [
            {"label": "the", "category": "general"},
            {"label": "cat", "category": "object"},
            {"label": "sleeps", "category": "action"},
        ]

        result = self.semantics.analyze_sequence(symbols)

        assert result["intent"] in [
            "statement",
            "request",
            "question",
            "feeling",
            "greeting",
        ]
        assert result["confidence"] >= 0.4

    def test_empty_symbols_returns_unknown(self):
        """Test that empty symbol list returns unknown intent."""
        symbols = []

        result = self.semantics.analyze_sequence(symbols)

        assert result["intent"] == "unknown"
        assert result["confidence"] == 0.0
        assert result["symbol_count"] == 0
        assert result["semantic_roles"] == []

    def test_semantic_roles_mapping(self):
        """Test correct mapping of categories to semantic roles."""
        symbols = [
            {"label": "I", "category": "person"},
            {"label": "go", "category": "action"},
            {"label": "home", "category": "place"},
        ]

        result = self.semantics.analyze_sequence(symbols)

        # Check that roles are mapped from categories
        assert len(result["semantic_roles"]) == 3
        # person -> agent/subject/pronoun
        assert result["semantic_roles"][0] in ["agent", "subject", "pronoun"]
        # action -> verb/activity
        assert result["semantic_roles"][1] in ["verb", "activity"]
        # place -> location/destination
        assert result["semantic_roles"][2] in ["location", "destination"]

    def test_generate_expansion_context_for_request(self):
        """Test context generation for request intent."""
        symbols = [
            {"label": "I", "category": "person"},
            {"label": "need", "category": "action"},
            {"label": "help", "category": "object"},
        ]

        analysis = self.semantics.analyze_sequence(symbols)
        context = self.semantics.generate_expansion_context(analysis, symbols)

        assert "AAC Intent: REQUEST" in context
        assert "I → need → help" in context
        assert "Guidance:" in context
        assert "request" in context.lower()

    def test_generate_expansion_context_for_question(self):
        """Test context generation for question intent."""
        symbols = [
            {"label": "where", "category": "question"},
            {"label": "mom", "category": "person"},
        ]

        analysis = self.semantics.analyze_sequence(symbols)
        context = self.semantics.generate_expansion_context(analysis, symbols)

        assert "AAC Intent: QUESTION" in context
        assert "where" in context.lower()
        assert "Guidance:" in context
        assert "question" in context.lower()

    def test_generate_expansion_context_for_feeling(self):
        """Test context generation for feeling intent."""
        symbols = [{"label": "sad", "category": "feeling"}]

        analysis = self.semantics.analyze_sequence(symbols)
        context = self.semantics.generate_expansion_context(analysis, symbols)

        assert "AAC Intent: FEELING" in context
        assert "emotion" in context.lower() or "empathy" in context.lower()

    def test_unique_categories_tracking(self):
        """Test that unique categories are correctly tracked."""
        symbols = [
            {"label": "I", "category": "person"},
            {"label": "want", "category": "action"},
            {"label": "red", "category": "descriptor"},
            {"label": "apple", "category": "object"},
            {"label": "please", "category": "action"},  # Duplicate category
        ]

        result = self.semantics.analyze_sequence(symbols)

        # Should have 4 unique categories: person, action, descriptor, object
        assert len(result["unique_categories"]) == 4
        assert "person" in result["unique_categories"]
        assert "action" in result["unique_categories"]
        assert "descriptor" in result["unique_categories"]
        assert "object" in result["unique_categories"]

    def test_summary_formatting(self):
        """Test that summary is correctly formatted."""
        symbols = [
            {"label": "I", "category": "person"},
            {"label": "want", "category": "action"},
        ]

        result = self.semantics.analyze_sequence(symbols)

        assert result["summary"]
        assert "I" in result["summary"]
        assert "want" in result["summary"]
        assert "→" in result["summary"]  # Should have arrow separators

    def test_case_insensitive_keyword_matching(self):
        """Test that keyword matching is case-insensitive."""
        symbols_upper = [
            {"label": "WANT", "category": "action"},
            {"label": "COOKIE", "category": "object"},
        ]

        result = self.semantics.analyze_sequence(symbols_upper)

        # Should still detect as request despite uppercase
        assert result["intent"] == "request"

    def test_partial_pattern_matching(self):
        """Test that partial pattern matches work (AAC users often drop words)."""
        # Just "want cookie" without pronoun - should still be request
        symbols = [
            {"label": "want", "category": "action"},
            {"label": "cookie", "category": "object"},
        ]

        result = self.semantics.analyze_sequence(symbols)

        assert result["intent"] == "request"
        assert result["confidence"] > 0.6

    def test_missing_category_defaults_to_general(self):
        """Test that missing category defaults to 'general' semantic role."""
        symbols = [
            {"label": "hello"},  # No category
        ]

        result = self.semantics.analyze_sequence(symbols)

        assert result["semantic_roles"][0] == "general"
        assert result["unique_categories"] == ["general"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
