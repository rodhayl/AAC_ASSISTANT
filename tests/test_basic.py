import pytest


def test_imports():
    """Test that all main modules can be imported"""
    # Test providers - only import to verify they exist
    from src.aac_app.providers.local_speech_provider import LocalSpeechProvider
    from src.aac_app.providers.ollama_provider import OllamaProvider

    assert LocalSpeechProvider is not None
    assert OllamaProvider is not None


def test_services():
    """Test that services can be imported"""
    from src.aac_app.services.learning.service import LearningCompanionService

    assert LearningCompanionService is not None


def test_models():
    """Test that database models can be imported"""
    from src.aac_app.models import LearningSession, User
    from src.aac_app.seed import init_database

    assert User is not None
    assert LearningSession is not None
    assert init_database is not None


def test_database_initialization():
    """Test database initialization"""
    from src.aac_app.seed import init_database

    # The autouse reset_production_db fixture points DATABASE_URL at an
    # isolated in-memory database, so a real failure here is a regression
    # and must fail the test rather than be skipped.
    init_database()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
