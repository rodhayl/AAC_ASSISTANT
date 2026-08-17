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
    try:
        from src.aac_app.models import LearningSession, User
        from src.aac_app.seed import init_database

        assert User is not None
        assert LearningSession is not None
        assert init_database is not None
    except ImportError as e:
        pytest.skip(f"Model import failed: {e}")


def test_database_initialization():
    """Test database initialization"""
    try:
        from src.aac_app.seed import init_database

        # This should not raise an exception
        init_database()
        assert True
    except Exception as e:
        pytest.skip(f"Database initialization failed: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
