import pytest
import io
import wave
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from src.api.main import app
from src.aac_app.models.database import Symbol
from src.aac_app.services.vector_utils import index_all_symbols

# Use the setup_test_db fixture to ensure API dependency overrides are active
pytestmark = pytest.mark.usefixtures("setup_test_db")

client = TestClient(app)

@pytest.fixture(scope="function")
def auth_headers(test_db_session, test_password):
    """Create a user and return auth headers"""
    # We need to create user via API to ensure password hashing etc is consistent with app logic
    # BUT if we use API, it uses the patched DB.
    # If we use test_db_session here, we are on the same DB.
    
    username = "gui_tester"
    client.post("/api/auth/register", json={
        "username": username,
        "password": test_password,
        "display_name": "GUI Tester",
        "user_type": "teacher"
    })
    # Login
    resp = client.post("/api/auth/token", data={"username": username, "password": test_password})
    if resp.status_code != 200:
        raise ValueError(f"Login failed: {resp.text}")
        
    token = resp.json()["access_token"]
    
    # Get ID
    from src.aac_app.models.database import User
    user = test_db_session.query(User).filter(User.username == username).first()
    user_id = user.id
        
    return {"Authorization": f"Bearer {token}"}, user_id

def create_dummy_wav():
    """Create a small valid WAV file in memory"""
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        # Write 1 second of silence
        wav_file.writeframes(b'\x00' * 32000)
    buf.seek(0)
    return buf

class TestGUICoverage:
    
    def test_semantic_symbol_search(self, auth_headers, test_db_session):
        """Test the semantic search functionality used by the Symbol Picker GUI"""
        headers, _ = auth_headers
        
        # 1. Create symbols directly in the shared test session
        s1 = Symbol(label="feline", description="A cat animal", keywords="pet, meow")
        s2 = Symbol(label="canine", description="A dog animal", keywords="pet, bark")
        test_db_session.add(s1)
        test_db_session.add(s2)
        test_db_session.commit()
            
        # 2. Index symbols - We need to patch get_session inside index_all_symbols 
        # because it likely imports it from database.py
        # OR we can manually index using the session we have.
        # Let's mock get_session in vector_utils to return our session context manager
        
        from contextlib import contextmanager
        @contextmanager
        def mock_get_session_cm():
            yield test_db_session
            
        with patch("src.aac_app.services.vector_utils.get_session", side_effect=mock_get_session_cm):
            # Also patch get_vector_store to return a mock, since we don't want real GPU usage here
            with patch("src.aac_app.services.vector_utils.get_vector_store") as mock_get_vs_utils:
                mock_vs = MagicMock()
                mock_vs.metadata = [] # Simulate empty
                mock_get_vs_utils.return_value = mock_vs
                
                index_all_symbols(force=True)
                
                # Verify add_texts was called
                assert mock_vs.add_texts.called
                
        # 3. Search via API
        with patch("src.api.dependencies.get_vector_store") as mock_get_vs:
            mock_vs = MagicMock()
            mock_get_vs.return_value = mock_vs
            
            # We need the actual ID from DB
            feline = test_db_session.query(Symbol).filter(Symbol.label == "feline").first()
            feline_id = feline.id
            
            mock_vs.search.return_value = [{"id": feline_id, "type": "symbol", "score": 0.9}]
            
            response = client.get("/api/boards/symbols?search=kitty", headers=headers)
            assert response.status_code == 200
            data = response.json()
            
            # Verify we got results
            assert len(data) > 0
            assert any(s["label"] == "feline" for s in data)
            
            # Verify fallback: Search for something not in vector store
            mock_vs.search.return_value = []
            response = client.get("/api/boards/symbols?search=unknown_term", headers=headers)
            assert response.status_code == 200
            assert len(response.json()) == 0

    def test_voice_answer_upload(self, auth_headers, test_db_session):
        """Test voice answer upload flow used in Learning Mode"""
        headers, user_id = auth_headers
        
        # 1. Start a session
        with patch("src.aac_app.services.learning_companion_service.LearningCompanionService.start_learning_session") as mock_start:
            mock_start.return_value = {"success": True, "session_id": 999}
            
            start_res = client.post(
                f"/api/learning/start?user_id={user_id}",
                json={"topic": "test", "purpose": "test"},
                headers=headers
            )
            assert start_res.status_code == 200
            
        # 2. Create dummy DB session for the endpoint to find
        from src.aac_app.models.database import LearningSession
        ls = LearningSession(user_id=user_id, topic_name="test", id=999)
        test_db_session.add(ls)
        test_db_session.commit()

        # 3. Upload voice answer
        wav_file = create_dummy_wav()
        files = {"file": ("answer.wav", wav_file, "audio/wav")}
        
        with patch("src.aac_app.services.learning_companion_service.LearningCompanionService.process_response") as mock_process:
            mock_process.return_value = {
                "success": True, 
                "feedback": "Good job", 
                "transcription": "Hello"
            }
            
            response = client.post(
                "/api/learning/999/answer/voice",
                files=files,
                headers=headers
            )
            
            assert response.status_code == 200
            assert response.json()["success"] is True
            
            # Verify process_response was called with is_voice=True
            mock_process.assert_called_once()
            call_kwargs = mock_process.call_args.kwargs
            assert call_kwargs["is_voice"] is True
            assert call_kwargs["session_id"] == 999

    def test_symbol_hunt_data_access(self, auth_headers):
        """Test that a user can access board data required for Symbol Hunt"""
        headers, user_id = auth_headers
        
        # 1. Create a board
        create_res = client.post(
            f"/api/boards/?user_id={user_id}",
            json={"name": "Game Board", "category": "games"},
            headers=headers
        )
        assert create_res.status_code == 200
        board_id = create_res.json()["id"]
        
        # 2. Fetch it (simulates Symbol Hunt loading the board)
        get_res = client.get(f"/api/boards/{board_id}", headers=headers)
        assert get_res.status_code == 200
        data = get_res.json()
        assert data["name"] == "Game Board"
        assert "symbols" in data
        assert "playable_symbols_count" in data
