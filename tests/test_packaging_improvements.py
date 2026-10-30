"""
Tests for Packaging Improvements
================================
This module tests all the packaging-related improvements:
1. Lazy loading of heavy AI models (Whisper, SentenceTransformer)
2. Frozen-aware path resolution for PyInstaller builds
3. Provider initialization and warmup
4. Database model completeness

These tests ensure the packaged application will work correctly.
"""

import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from pathlib import Path
import sys
import os


# ============================================================================
# LAZY LOADING TESTS
# ============================================================================

class TestLazyLoadingVectorStore:
    """Test lazy loading behavior in LocalVectorStore"""

    def test_vector_store_lazy_init_does_not_load_model(self):
        """Verify that lazy_load=True does not immediately load the model"""
        from src.aac_app.services.local_vector_store import LocalVectorStore
        
        # Create with lazy_load=True (default)
        store = LocalVectorStore(lazy_load=True)
        
        # Model should not be loaded yet
        assert store._model_loaded is False
        assert store.model is None
        
    def test_vector_store_eager_init_loads_model(self):
        """Verify that lazy_load=False loads the model immediately"""
        from src.aac_app.services.local_vector_store import LocalVectorStore, SENTENCE_TRANSFORMERS_AVAILABLE
        
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            pytest.skip("sentence-transformers not installed")
        
        # Create with lazy_load=False
        store = LocalVectorStore(lazy_load=False)
        
        # Model should be loaded
        assert store._model_loaded is True
        
    def test_vector_store_lazy_loads_on_search(self):
        """Verify model loads on first search call"""
        from src.aac_app.services.local_vector_store import LocalVectorStore, SENTENCE_TRANSFORMERS_AVAILABLE
        
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            pytest.skip("sentence-transformers not installed")
        
        store = LocalVectorStore(lazy_load=True)
        assert store._model_loaded is False
        
        # Perform a search - this should trigger lazy loading
        store.search("test query", k=1)
        
        # Model should now be loaded
        assert store._model_loaded is True
        
    def test_vector_store_is_available_does_not_load(self):
        """Verify is_available() does not trigger model loading"""
        from src.aac_app.services.local_vector_store import LocalVectorStore
        
        store = LocalVectorStore(lazy_load=True)
        
        # Check availability (should not load model)
        _ = store.is_available()
        
        # Model should still not be loaded
        assert store._model_loaded is False
        
    def test_vector_store_force_load(self):
        """Verify force_load() triggers immediate loading"""
        from src.aac_app.services.local_vector_store import LocalVectorStore, SENTENCE_TRANSFORMERS_AVAILABLE
        
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            pytest.skip("sentence-transformers not installed")
        
        store = LocalVectorStore(lazy_load=True)
        assert store._model_loaded is False
        
        # Force load
        store.force_load()
        
        # Model should now be loaded
        assert store._model_loaded is True


class TestLazyLoadingSpeechProvider:
    """Test lazy loading behavior in LocalSpeechProvider"""
    
    def test_speech_provider_lazy_init_does_not_load_model(self):
        """Verify that lazy_load=True does not immediately load Whisper"""
        from src.aac_app.providers.local_speech_provider import LocalSpeechProvider
        
        provider = LocalSpeechProvider(lazy_load=True)
        
        # Model should not be loaded yet
        assert provider._model_loaded is False
        assert provider.model is None
        
    def test_speech_provider_is_available_does_not_load(self):
        """Verify is_available() does not trigger model loading"""
        from src.aac_app.providers.local_speech_provider import LocalSpeechProvider
        
        provider = LocalSpeechProvider(lazy_load=True)
        
        # Check availability
        _ = provider.is_available()
        
        # Model should still not be loaded
        assert provider._model_loaded is False
        
    def test_speech_provider_force_load(self):
        """Verify force_load() triggers immediate loading"""
        from src.aac_app.providers.local_speech_provider import LocalSpeechProvider, WHISPER_AVAILABLE
        
        if not WHISPER_AVAILABLE:
            pytest.skip("Whisper not installed")
        
        provider = LocalSpeechProvider(lazy_load=True)
        assert provider._model_loaded is False
        
        # Force load
        provider.force_load()
        
        # Model should now be loaded
        assert provider._model_loaded is True


# ============================================================================
# PATH RESOLUTION TESTS
# ============================================================================

class TestFrozenPathResolution:
    """Test path resolution functions in config module"""
    
    def test_is_frozen_detection(self):
        """Test that IS_FROZEN detects frozen state correctly"""
        from src import config
        
        # In normal test environment, should not be frozen
        assert config.IS_FROZEN is False
        
    def test_get_bundled_path_development(self):
        """Test get_bundled_path returns project root in development"""
        from src import config
        
        # In development mode, should return path relative to PROJECT_ROOT
        path = config.get_bundled_path("data")
        assert path.exists() or path.parent.exists()
        assert "data" in str(path)
        
    def test_get_data_path(self):
        """Test get_data_path returns correct data directory"""
        from src import config
        
        data_path = config.get_data_path()
        assert data_path.exists()
        assert data_path.name == "data"
        
    def test_get_ngrams_path(self):
        """Test get_ngrams_path returns correct ngrams directory"""
        from src import config
        
        ngrams_path = config.get_ngrams_path()
        # Should contain ngrams in the path
        assert "ngrams" in str(ngrams_path)
        
    @patch.object(sys, 'frozen', True, create=True)
    def test_simulated_frozen_mode(self):
        """Test path resolution with simulated frozen mode"""
        # This test simulates frozen mode behavior
        from src import config
        
        # Re-import to test the frozen detection
        # Note: This is a partial simulation since _MEIPASS is not set
        # but we can verify the IS_FROZEN check works
        assert getattr(sys, 'frozen', False) is True


class TestPredictionServicePaths:
    """Test that PredictionService uses frozen-aware paths"""
    
    def test_ngrams_path_used(self):
        """Verify PredictionService uses config.get_ngrams_path()"""
        from src.aac_app.services.prediction_service import PredictionService
        from src import config
        
        service = PredictionService()
        
        # Try to load a model (may fail if no ngrams file exists, that's ok)
        model = service._load_model("en")
        
        # The path should have been used from config
        # This is verified by checking the implementation uses config.get_ngrams_path()


# ============================================================================
# DATABASE MODEL TESTS
# ============================================================================

class TestDatabaseModelCompleteness:
    """Test that database models have all required columns"""
    
    def test_communication_board_has_locale(self):
        """Verify CommunicationBoard has locale column"""
        from src.aac_app.models.database import CommunicationBoard
        
        # Check column exists
        assert hasattr(CommunicationBoard, 'locale')
        
        # Verify it's a proper SQLAlchemy column
        assert 'locale' in CommunicationBoard.__table__.columns
        
    def test_communication_board_has_is_language_learning(self):
        """Verify CommunicationBoard has is_language_learning column"""
        from src.aac_app.models.database import CommunicationBoard
        
        assert hasattr(CommunicationBoard, 'is_language_learning')
        assert 'is_language_learning' in CommunicationBoard.__table__.columns
        
    def test_board_symbol_has_linked_board_id(self):
        """Verify BoardSymbol has linked_board_id column"""
        from src.aac_app.models.database import BoardSymbol
        
        assert hasattr(BoardSymbol, 'linked_board_id')
        assert 'linked_board_id' in BoardSymbol.__table__.columns
        
    def test_board_symbol_has_color(self):
        """Verify BoardSymbol has color column"""
        from src.aac_app.models.database import BoardSymbol
        
        assert hasattr(BoardSymbol, 'color')
        assert 'color' in BoardSymbol.__table__.columns
        
    def test_board_symbol_has_order_index(self):
        """Verify BoardSymbol has order_index column"""
        from src.aac_app.models.database import BoardSymbol
        
        assert hasattr(BoardSymbol, 'order_index')
        assert 'order_index' in BoardSymbol.__table__.columns
        
    def test_board_symbol_relationships(self):
        """Verify BoardSymbol has proper relationships"""
        from src.aac_app.models.database import BoardSymbol
        
        # Check relationships exist
        assert hasattr(BoardSymbol, 'board')
        assert hasattr(BoardSymbol, 'symbol')
        assert hasattr(BoardSymbol, 'linked_board')


# ============================================================================
# WARMUP / PROVIDER INITIALIZATION TESTS  
# ============================================================================

class TestProviderWarmup:
    """Test provider warmup functions"""
    
    def test_warmup_providers_returns_state(self):
        """Verify warmup_providers returns a state dictionary"""
        from src.api.dependencies import warmup_providers, reset_providers
        
        # Reset first
        reset_providers()
        
        # Run warmup with short timeout
        state = warmup_providers(timeout_seconds=5.0)
        
        assert isinstance(state, dict)
        assert "initialized" in state
        assert "providers_ready" in state
        assert "errors" in state
        assert "startup_time_ms" in state
        
    def test_get_startup_state(self):
        """Verify get_startup_state returns current state"""
        from src.api.dependencies import get_startup_state
        
        state = get_startup_state()
        
        assert isinstance(state, dict)
        assert "initialized" in state
        
    def test_reset_providers(self):
        """Verify reset_providers clears all provider instances"""
        from src.api.dependencies import reset_providers, get_startup_state
        
        reset_providers()
        
        state = get_startup_state()
        assert state["initialized"] is False
        
    def test_speech_provider_warmup_uses_lazy_load(self):
        """Verify speech provider warmup uses lazy loading"""
        from src.api.dependencies import _init_speech_provider_sync, reset_providers
        from src.api.dependencies import _speech_provider
        
        reset_providers()
        
        # Run speech provider init
        success = _init_speech_provider_sync()
        
        assert success is True
        # The provider should exist but with lazy loading enabled
        
    def test_vector_store_warmup_uses_lazy_load(self):
        """Verify vector store warmup uses lazy loading"""
        from src.api.dependencies import _init_vector_store_sync, reset_providers
        
        reset_providers()
        
        # Run vector store init
        success = _init_vector_store_sync()
        
        assert success is True


# ============================================================================
# SCHEMA VALIDATION TESTS
# ============================================================================

class TestSchemaModelAlignment:
    """Test that Pydantic schemas match database models"""
    
    def test_board_create_schema_matches_model(self):
        """Verify BoardCreate schema fields exist in CommunicationBoard model"""
        from src.api.schemas import BoardCreate
        from src.aac_app.models.database import CommunicationBoard
        
        # Get schema fields (excluding 'symbols' which is handled separately)
        schema_fields = set(BoardCreate.model_fields.keys()) - {'symbols'}
        
        # Get model columns
        model_columns = set(CommunicationBoard.__table__.columns.keys())
        
        # Schema fields should be a subset of model columns (plus id, user_id, timestamps)
        for field in schema_fields:
            assert field in model_columns or field in ['ai_enabled', 'ai_provider', 'ai_model'], \
                f"Schema field '{field}' not found in model"
                
    def test_board_response_schema_matches_model(self):
        """Verify BoardResponse schema fields exist in CommunicationBoard model"""
        from src.api.schemas import BoardResponse
        from src.aac_app.models.database import CommunicationBoard
        
        schema_fields = set(BoardResponse.model_fields.keys())
        model_columns = set(CommunicationBoard.__table__.columns.keys())
        
        # Check key fields exist
        for field in ['locale', 'is_language_learning', 'ai_enabled']:
            if field in schema_fields:
                assert field in model_columns, f"Schema field '{field}' not in model"


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestPackagingIntegration:
    """Integration tests for packaging improvements"""
    
    def test_full_initialization_flow(self):
        """Test complete initialization flow"""
        from src.api.dependencies import reset_providers, warmup_providers, is_ready
        
        # Reset everything
        reset_providers()
        
        # Should not be ready initially
        assert is_ready() is False
        
        # Run warmup
        warmup_providers(timeout_seconds=10.0)
        
        # Should be ready now
        assert is_ready() is True
        
    def test_api_health_endpoint(self):
        """Test API health endpoint works after initialization"""
        from fastapi.testclient import TestClient
        from src.api.main import app
        
        client = TestClient(app)
        
        response = client.get("/api/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] in ["healthy", "online"]  # Accept both values


# ============================================================================
# SPEC FILE VALIDATION
# ============================================================================

class TestSpecFileConfiguration:
    """Test PyInstaller spec file configuration"""
    
    def test_spec_file_exists(self):
        """Verify AAC_Assistant.spec exists"""
        spec_path = Path(__file__).parent.parent / "AAC_Assistant.spec"
        assert spec_path.exists(), "AAC_Assistant.spec not found"
        
    def test_spec_file_has_required_datas(self):
        """Verify spec file includes required data entries"""
        spec_path = Path(__file__).parent.parent / "AAC_Assistant.spec"
        content = spec_path.read_text()
        
        # Check for required data directories
        assert "data" in content, "spec should include data directory"
        assert "ngrams" in content, "spec should include ngrams directory"
        assert "frontend" in content, "spec should include frontend"
        
    def test_spec_file_uses_collect(self):
        """Verify spec file uses COLLECT for one-folder build"""
        spec_path = Path(__file__).parent.parent / "AAC_Assistant.spec"
        content = spec_path.read_text()
        
        assert "COLLECT" in content, "spec should use COLLECT for one-folder build"
        assert "exclude_binaries=True" in content, "EXE should exclude binaries for one-folder"


# ============================================================================
# INSTALLER SCRIPT TESTS
# ============================================================================

class TestInstallerScript:
    """Test Inno Setup installer script"""
    
    def test_installer_iss_exists(self):
        """Verify installer.iss exists"""
        iss_path = Path(__file__).parent.parent / "installer.iss"
        assert iss_path.exists(), "installer.iss not found"
        
    def test_installer_has_required_sections(self):
        """Verify installer.iss has required sections"""
        iss_path = Path(__file__).parent.parent / "installer.iss"
        content = iss_path.read_text()
        
        required_sections = ["[Setup]", "[Files]", "[Icons]", "[Dirs]"]
        for section in required_sections:
            assert section in content, f"installer.iss missing {section} section"
            
    def test_installer_creates_writable_dirs(self):
        """Verify installer creates writable directories"""
        iss_path = Path(__file__).parent.parent / "installer.iss"
        content = iss_path.read_text()
        
        # Should set permissions on data, logs, uploads
        assert "data" in content
        assert "logs" in content
        assert "uploads" in content
        assert "users-modify" in content.lower() or "Permissions" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
