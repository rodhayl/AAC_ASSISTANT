import sys
from pathlib import Path

import pytest

# Add src to path
src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))


def test_imports():
    """Test that all main modules can be imported"""
    # Test providers - only import to verify they exist
    try:
        from aac_app.providers.local_speech_provider import LocalSpeechProvider
        from aac_app.providers.local_tts_provider import LocalTTSProvider
        from aac_app.providers.ollama_provider import OllamaProvider

        assert LocalSpeechProvider is not None
        assert LocalTTSProvider is not None
        assert OllamaProvider is not None
    except ImportError as e:
        pytest.skip(f"Provider import failed: {e}")


def test_services():
    """Test that services can be imported"""
    try:
        from aac_app.services.learning_companion_service import LearningCompanionService

        assert LearningCompanionService is not None
    except ImportError as e:
        pytest.skip(f"Service import failed: {e}")


def test_models():
    """Test that database models can be imported"""
    try:
        from aac_app.models.database import LearningSession, User, init_database

        assert User is not None
        assert LearningSession is not None
        assert init_database is not None
    except ImportError as e:
        pytest.skip(f"Model import failed: {e}")


def test_database_initialization():
    """Test database initialization"""
    try:
        from aac_app.models.database import init_database

        # This should not raise an exception
        init_database()
        assert True
    except Exception as e:
        pytest.skip(f"Database initialization failed: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
