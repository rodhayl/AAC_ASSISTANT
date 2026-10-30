"""
Tests for Analytics API endpoints
Tests REST API endpoints for symbol usage analytics.
"""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from src.aac_app.models.database import SymbolUsageLog
from src.api.dependencies import get_current_active_user
from src.api.main import app

# Mark all tests to use test database
pytestmark = pytest.mark.usefixtures("setup_test_db")

client = TestClient(app)


@pytest.fixture(scope="function", autouse=True)
def setup_auth(regular_user):
    """Ensure auth override is set for all tests in this module."""

    def override_get_current_active_user():
        return regular_user

    app.dependency_overrides[get_current_active_user] = override_get_current_active_user
    yield
    # Restore if needed
    app.dependency_overrides.pop(get_current_active_user, None)


@pytest.fixture(scope="function")
def sample_usage_logs(test_db_session, regular_user):
    """Create sample symbol usage logs for testing."""
    from src.aac_app.models.database import LearningSession, Symbol

    # Create required symbols
    symbols_data = [
        Symbol(id=1, label="I", category="pronoun", language="en", is_builtin=True),
        Symbol(id=2, label="want", category="verb", language="en", is_builtin=True),
        Symbol(id=3, label="cookie", category="noun", language="en", is_builtin=True),
        Symbol(id=4, label="milk", category="noun", language="en", is_builtin=True),
        Symbol(id=5, label="happy", category="emotion", language="en", is_builtin=True),
    ]
    for symbol in symbols_data:
        test_db_session.add(symbol)

    # Create learning sessions
    sessions_data = [
        LearningSession(
            id=1, user_id=regular_user.id, topic_name="practice", purpose="test"
        ),
        LearningSession(
            id=2, user_id=regular_user.id, topic_name="practice", purpose="test"
        ),
        LearningSession(
            id=3, user_id=regular_user.id, topic_name="practice", purpose="test"
        ),
    ]
    for session in sessions_data:
        test_db_session.add(session)

    test_db_session.flush()

    # Create usage logs directly in test database
    logs_data = [
        # First utterance: "I want cookie"
        {
            "user_id": regular_user.id,
            "session_id": 1,
            "symbol_id": 1,
            "symbol_label": "I",
            "symbol_category": "pronoun",
            "position_in_utterance": 0,
            "utterance_length": 3,
            "semantic_intent": "request",
            "timestamp": datetime.now(),
        },
        {
            "user_id": regular_user.id,
            "session_id": 1,
            "symbol_id": 2,
            "symbol_label": "want",
            "symbol_category": "verb",
            "position_in_utterance": 1,
            "utterance_length": 3,
            "semantic_intent": "request",
            "timestamp": datetime.now(),
        },
        {
            "user_id": regular_user.id,
            "session_id": 1,
            "symbol_id": 3,
            "symbol_label": "cookie",
            "symbol_category": "noun",
            "position_in_utterance": 2,
            "utterance_length": 3,
            "semantic_intent": "request",
            "timestamp": datetime.now(),
        },
        # Second utterance: "I want milk"
        {
            "user_id": regular_user.id,
            "session_id": 2,
            "symbol_id": 1,
            "symbol_label": "I",
            "symbol_category": "pronoun",
            "position_in_utterance": 0,
            "utterance_length": 3,
            "semantic_intent": "request",
            "timestamp": datetime.now(),
        },
        {
            "user_id": regular_user.id,
            "session_id": 2,
            "symbol_id": 2,
            "symbol_label": "want",
            "symbol_category": "verb",
            "position_in_utterance": 1,
            "utterance_length": 3,
            "semantic_intent": "request",
            "timestamp": datetime.now(),
        },
        {
            "user_id": regular_user.id,
            "session_id": 2,
            "symbol_id": 4,
            "symbol_label": "milk",
            "symbol_category": "noun",
            "position_in_utterance": 2,
            "utterance_length": 3,
            "semantic_intent": "request",
            "timestamp": datetime.now(),
        },
        # Third utterance: "happy"
        {
            "user_id": regular_user.id,
            "session_id": 3,
            "symbol_id": 5,
            "symbol_label": "happy",
            "symbol_category": "emotion",
            "position_in_utterance": 0,
            "utterance_length": 1,
            "semantic_intent": "statement",
            "timestamp": datetime.now(),
        },
    ]

    for log_data in logs_data:
        log = SymbolUsageLog(**log_data)
        test_db_session.add(log)

    test_db_session.commit()
    return test_db_session


class TestAnalyticsAPI:
    """Test suite for Analytics API endpoints."""

    def test_get_frequent_sequences_success(self, sample_usage_logs):
        """Test retrieving frequent symbol sequences."""
        response = client.get("/api/analytics/frequent-sequences")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_frequent_sequences_with_params(self, sample_usage_logs):
        """Test frequent sequences with custom parameters."""
        response = client.get(
            "/api/analytics/frequent-sequences",
            params={"limit": 5, "min_occurrences": 1},
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) <= 5

    def test_get_next_symbol_suggestions_no_context(self, sample_usage_logs):
        """Test next symbol suggestions without current symbols."""
        response = client.post("/api/analytics/next-symbol", json={})

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

        # Should return most frequent symbols
        if len(data) > 0:
            assert "label" in data[0]
            assert "confidence" in data[0]

    def test_get_next_symbol_suggestions_with_context(self, sample_usage_logs):
        """Test next symbol suggestions with current symbols."""
        response = client.post(
            "/api/analytics/next-symbol",
            json={"current_symbols": "I,want", "limit": 3},
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        # Filter out always-included punctuation for limit check
        non_punctuation = [s for s in data if s.get("category") != "punctuation"]
        assert len(non_punctuation) <= 3

    def test_get_category_preferences(self, sample_usage_logs):
        """Test retrieving category preferences."""
        response = client.get("/api/analytics/category-preferences")

        assert response.status_code == 200
        data = response.json()
        assert "categories" in data
        assert "total_symbols_used" in data
        assert "unique_categories" in data
        assert isinstance(data["categories"], dict)
        assert data["total_symbols_used"] > 0

    def test_get_usage_statistics_default_period(self, sample_usage_logs):
        """Test usage statistics with default 30-day period."""
        response = client.get("/api/analytics/usage-stats")

        assert response.status_code == 200
        data = response.json()
        assert "period_days" in data
        assert "total_symbols_used" in data
        assert "unique_symbols" in data
        assert "average_utterance_length" in data
        assert "most_used_symbols" in data
        assert "intent_distribution" in data

        assert data["period_days"] == 30
        assert data["total_symbols_used"] > 0
        assert isinstance(data["most_used_symbols"], list)
        assert isinstance(data["intent_distribution"], dict)

    def test_get_usage_statistics_custom_period(self, sample_usage_logs):
        """Test usage statistics with custom period."""
        response = client.get("/api/analytics/usage-stats", params={"days": 7})

        assert response.status_code == 200
        data = response.json()
        assert data["period_days"] == 7

    def test_analytics_endpoints_require_auth(self):
        """Test that analytics endpoints require authentication."""
        # Save current override state
        saved_override = app.dependency_overrides.get(get_current_active_user)

        # Temporarily remove auth override
        if get_current_active_user in app.dependency_overrides:
            app.dependency_overrides.pop(get_current_active_user)

        get_endpoints = [
            "/api/analytics/frequent-sequences",
            "/api/analytics/category-preferences",
            "/api/analytics/usage-stats",
        ]
        
        post_endpoints = [
            "/api/analytics/next-symbol",
        ]

        for endpoint in get_endpoints:
            response = client.get(endpoint)
            # Should return 401 or 403 without auth
            assert response.status_code in [401, 403, 422]

        for endpoint in post_endpoints:
            response = client.post(endpoint, json={})
            assert response.status_code in [401, 403, 422]

        # Restore auth override if it existed
        if saved_override is not None:
            app.dependency_overrides[get_current_active_user] = saved_override

    def test_frequent_sequences_pagination(self, sample_usage_logs):
        """Test pagination parameters for frequent sequences."""
        # Test with limit of 1
        response = client.get("/api/analytics/frequent-sequences", params={"limit": 1})

        assert response.status_code == 200
        data = response.json()
        assert len(data) <= 1

    def test_next_symbol_limit_validation(self, sample_usage_logs):
        """Test limit parameter validation."""
        # Test within valid range
        response = client.post("/api/analytics/next-symbol", json={"limit": 10})
        assert response.status_code == 200

        # Test edge case
        response = client.post("/api/analytics/next-symbol", json={"limit": 1})
        assert response.status_code == 200
        data = response.json()
        
        # Filter out always-included punctuation for limit check
        non_punctuation = [s for s in data if s.get("category") != "punctuation"]
        assert len(non_punctuation) <= 1
