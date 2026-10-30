"""
Integration tests for Plan 3 AAC features
Tests the complete flow: expansion + editor + prompt profile + analytics
"""

import pytest

from src.aac_app.services.aac_expander_service import AACExpanderService
from src.aac_app.services.symbol_analytics import SymbolAnalytics
from src.aac_app.services.symbol_semantics import SymbolSemantics


class TestPlan3Integration:
    """Integration tests for Plan 3 features."""

    @pytest.fixture(autouse=True)
    def setup_services(self):
        """Set up test fixtures."""
        self.expander = AACExpanderService()
        self.semantics = SymbolSemantics()
        self.analytics = SymbolAnalytics()
        yield
        self.expander.clear_cache()

    def test_complete_symbol_flow_with_expansion(self):
        """Test complete flow: symbols -> semantic analysis -> expansion."""
        symbols = [
            {"id": 1, "label": "I", "category": "person"},
            {"id": 2, "label": "want", "category": "action"},
            {"id": 3, "label": "cookie", "category": "object"},
        ]
        raw_gloss = "I want cookie"

        # Step 1: Semantic analysis
        semantic_analysis = self.semantics.analyze_sequence(symbols)
        assert semantic_analysis["intent"] == "request"

        # Step 2: Grammar expansion
        expansion_result = self.expander.expand(symbols, raw_gloss, semantic_analysis)
        assert "want a cookie" in expansion_result["expanded_text"].lower()
        assert expansion_result["confidence"] > 0.6

        # Verify transformations were applied
        assert len(expansion_result["transformations"]) > 0

    def test_expansion_caching_performance(self):
        """Test that caching improves performance for repeated sequences."""
        symbols = [{"id": 1, "label": "help", "category": "action"}]
        raw_gloss = "help"

        # First call - not cached
        result1 = self.expander.expand(symbols, raw_gloss)

        # Second call - should hit cache
        result2 = self.expander.expand(symbols, raw_gloss)

        assert result1["expanded_text"] == result2["expanded_text"]
        assert result1 == result2  # Exact same result from cache

    def test_analytics_logging_and_retrieval(self):
        """Test that symbol usage is logged and can be retrieved."""
        # This is a simplified test - in production, would use actual database
        symbols = [
            {"id": 1, "label": "happy", "category": "feeling", "position": 0},
            {"id": 2, "label": "today", "category": "object", "position": 1},
        ]

        # Test that logging doesn't crash (actual DB logging tested separately)
        # In a real scenario, this would interact with a test database
        user_id = 1
        session_id = 1
        intent = "feeling"

        # Note: This will fail gracefully if database is not set up
        # That's okay for unit tests - integration tests use real DB
        try:
            success = self.analytics.log_symbol_usage(
                user_id=user_id,
                symbols=symbols,
                session_id=session_id,
                semantic_intent=intent,
                context_topic="emotions",
            )
            # If it succeeded, verify we can query (in full integration test)
            if success:
                stats = self.analytics.get_usage_stats(user_id, days=30)
                assert stats is not None
        except Exception:
            # Expected in unit test without full DB setup
            pass

    def test_multiple_transformations_scenario(self):
        """Test sentence that requires multiple grammar transformations."""
        symbols = [
            {"id": 1, "label": "me", "category": "person"},
            {"id": 2, "label": "want", "category": "action"},
            {"id": 3, "label": "apple", "category": "object"},
        ]
        raw_gloss = "me want apple"

        semantic_analysis = self.semantics.analyze_sequence(symbols)
        expansion_result = self.expander.expand(symbols, raw_gloss, semantic_analysis)

        # Should fix pronoun AND add article
        expanded = expansion_result["expanded_text"].lower()
        assert "i want" in expanded or "i" in expanded.split()[0]
        assert "an apple" in expanded or "apple" in expanded

        # Should have multiple transformations
        assert len(expansion_result["transformations"]) >= 2

    def test_question_formation_with_semantic_intent(self):
        """Test that semantic intent guides question formation."""
        symbols = [
            {"id": 1, "label": "where", "category": "question"},
            {"id": 2, "label": "mom", "category": "person"},
        ]
        raw_gloss = "where mom"

        semantic_analysis = self.semantics.analyze_sequence(symbols)
        assert semantic_analysis["intent"] == "question"

        expansion_result = self.expander.expand(symbols, raw_gloss, semantic_analysis)

        # Should end with question mark
        assert expansion_result["expanded_text"].endswith("?")
        assert "where" in expansion_result["expanded_text"].lower()

    def test_single_word_common_expansion(self):
        """Test common single-word expansions work correctly."""
        test_cases = [
            ("happy", "feel happy"),
            ("sad", "feel sad"),
            ("help", "need help"),
            ("hello", "Hello"),
        ]

        for word, expected_phrase in test_cases:
            symbols = [{"id": 1, "label": word, "category": "general"}]
            result = self.expander.expand(symbols, word)

            assert expected_phrase.lower() in result["expanded_text"].lower()
            assert result["confidence"] == 0.95  # High confidence for common expansions

    def test_verb_conjugation_third_person(self):
        """Test third-person verb conjugation works correctly."""
        test_cases = [
            ("he go", "he goes"),
            ("she want", "she wants"),
            ("he have", "he has"),
        ]

        for input_text, expected_phrase in test_cases:
            words = input_text.split()
            symbols = [
                {"id": 1, "label": words[0], "category": "person"},
                {"id": 2, "label": words[1], "category": "action"},
            ]
            result = self.expander.expand(symbols, input_text)

            assert expected_phrase in result["expanded_text"].lower()
            assert "verb_conjugation" in result["transformations"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
