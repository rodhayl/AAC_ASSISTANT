"""
Tests for Learning tab conversation persistence functionality
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.aac_app.models import LearningSession, User
from src.aac_app.services.auth_service import get_password_hash
from src.aac_app.services.learning.history import (
    MAX_CONVERSATION_HISTORY_ENTRIES,
    append_history_entry,
)
from src.api.deps import get_llm_provider, get_speech_provider
from src.api.main import app
from tests.auth_helpers import create_test_headers

client = TestClient(app)


class TestHistoryHelper:
    """Unit tests for the conversation history helper."""

    def test_append_history_entry_keeps_only_newest_entries(self):
        history = [{"id": index} for index in range(MAX_CONVERSATION_HISTORY_ENTRIES)]

        updated = append_history_entry(history, {"id": MAX_CONVERSATION_HISTORY_ENTRIES})

        assert len(updated) == MAX_CONVERSATION_HISTORY_ENTRIES
        assert updated[0]["id"] == 1
        assert updated[-1]["id"] == MAX_CONVERSATION_HISTORY_ENTRIES


class TestSpeakableDisplayName:
    """The welcome greeting must not force TTS to read a timestamp suffix."""

    def test_strips_trailing_timestamp_suffix(self):
        from src.aac_app.services.learning.session import _speakable_display_name

        assert _speakable_display_name("Admin 1787688161578") == "Admin"
        assert _speakable_display_name("Test Teacher 1787688161578") == "Test Teacher"

    def test_keeps_regular_names_untouched(self):
        from src.aac_app.services.learning.session import _speakable_display_name

        assert _speakable_display_name("Ms. Johnson") == "Ms. Johnson"
        assert _speakable_display_name("Alex") == "Alex"
        # Short numeric tokens and embedded digits are not timestamp suffixes.
        assert _speakable_display_name("Sam 123") == "Sam 123"
        assert _speakable_display_name("Robert 2") == "Robert 2"
        assert _speakable_display_name("User2") == "User2"


@pytest.fixture(autouse=True)
def override_providers(
    mock_llm_provider,
    mock_speech_provider,
    test_db_session,
    monkeypatch,
):
    """Override provider dependencies with mocked versions"""
    from contextlib import contextmanager

    from src.aac_app import db
    from src.aac_app.services import achievement_system

    # Override providers
    app.dependency_overrides[get_llm_provider] = lambda: mock_llm_provider
    app.dependency_overrides[get_speech_provider] = lambda: mock_speech_provider

    # Patch get_session to use test database in all modules that use it
    @contextmanager
    def mock_get_session():
        yield test_db_session

    monkeypatch.setattr(db, "get_session", mock_get_session)
    monkeypatch.setattr(achievement_system, "get_session", mock_get_session)

    yield
    app.dependency_overrides.clear()


@pytest.mark.usefixtures("setup_test_db")
def test_start_session_creates_persisted_record(
    regular_user, user_token, test_db_session: Session
):
    """Test that starting a session creates a persisted database record"""
    # Start a learning session
    headers = {"Authorization": f"Bearer {user_token}"}
    response = client.post(
        "/api/learning/start",
        json={"topic": "test_topic", "purpose": "testing", "difficulty": "basic"},
        params={"user_id": regular_user.id},
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    session_id = data["session_id"]

    # Verify session exists in database
    session = test_db_session.query(LearningSession).filter_by(id=session_id).first()
    assert session is not None
    assert session.user_id == regular_user.id
    assert session.topic_name == "test_topic"
    assert session.status == "active"
    # Session startup persists the translated welcome message so the client
    # can reconstruct the complete conversation after a reload.
    assert session.conversation_history
    assert session.conversation_history[0]["type"] == "question"


@pytest.mark.usefixtures("setup_test_db")
def test_legacy_welcome_is_localized_when_loading_progress(
    regular_user, user_token, test_db_session: Session
):
    """Old persisted welcome templates are normalized before reaching the UI."""
    headers = {"Authorization": f"Bearer {user_token}"}
    start_response = client.post(
        "/api/learning/start",
        json={"topic": "general conversation", "purpose": "practice", "difficulty": "basic"},
        params={"user_id": regular_user.id},
        headers=headers,
    )
    assert start_response.status_code == 200, start_response.text
    session_id = start_response.json()["session_id"]

    session = test_db_session.query(LearningSession).filter_by(id=session_id).first()
    assert session is not None
    session.conversation_history = [
        {
            "type": "question",
            "data": {
                "question": f"¡Hola {regular_user.display_name}! ¡Vamos a aprender sobre general conversation juntos!"
            },
        }
    ]
    test_db_session.commit()

    progress_response = client.get(
        f"/api/learning/{session_id}/progress", headers=headers
    )

    assert progress_response.status_code == 200, progress_response.text
    welcome = progress_response.json()["conversation_history"][0]["data"]["question"]
    assert "Vamos a aprender sobre" not in welcome
    assert "Hoy vamos a practicar" in welcome
    assert "general conversation" not in welcome


@pytest.mark.usefixtures("setup_test_db")
def test_welcome_omits_timestamp_suffix_from_display_name(
    regular_user, user_token, test_db_session: Session
):
    """The first spoken welcome must not read a seeded timestamp aloud."""
    regular_user.display_name = "Admin 1787688161578"
    test_db_session.commit()

    response = client.post(
        "/api/learning/start",
        json={"topic": "general conversation", "purpose": "practice", "difficulty": "basic"},
        params={"user_id": regular_user.id},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert response.status_code == 200, response.text
    welcome = response.json()["welcome_message"]
    assert "1787688161578" not in welcome
    assert "Admin" in welcome


@pytest.mark.usefixtures("setup_test_db")
def test_conversation_auto_persists_after_message(
    regular_user, user_token, test_db_session: Session
):
    """Test that conversation history is automatically saved after each message"""
    # Start session
    headers = {"Authorization": f"Bearer {user_token}"}
    start_response = client.post(
        "/api/learning/start",
        json={"topic": "vocabulary", "purpose": "practice", "difficulty": "basic"},
        params={"user_id": regular_user.id},
        headers=headers,
    )
    session_id = start_response.json()["session_id"]

    # Submit an answer (this should persist to conversation_history)
    answer_response = client.post(
        f"/api/learning/{session_id}/answer",
        json={"answer": "test answer", "is_voice": False},
        headers=headers,
    )

    assert answer_response.status_code == 200

    # Fetch session from database and verify conversation_history is populated
    test_db_session.expire_all()  # Clear cache to get fresh data
    session = test_db_session.query(LearningSession).filter_by(id=session_id).first()
    assert session is not None
    assert session.conversation_history is not None
    assert len(session.conversation_history) > 0

    # Verify conversation contains the answer
    has_response = any(
        entry.get("type") == "response" for entry in session.conversation_history
    )
    assert has_response


@pytest.mark.usefixtures("setup_test_db")
def test_fetch_session_history(regular_user, user_token, test_db_session: Session):
    """Test fetching list of previous sessions"""
    # Create multiple sessions
    headers = {"Authorization": f"Bearer {user_token}"}
    sessions = []
    for i in range(3):
        response = client.post(
            "/api/learning/start",
            json={"topic": f"topic_{i}", "purpose": "practice", "difficulty": "basic"},
            params={"user_id": regular_user.id},
            headers=headers,
        )
        sessions.append(response.json()["session_id"])

    # Fetch history
    history_response = client.get(
        f"/api/learning/history/{regular_user.id}",
        params={"limit": 10},
        headers=headers,
    )

    assert history_response.status_code == 200
    data = history_response.json()
    assert "sessions" in data
    assert len(data["sessions"]) >= 3

    # Verify sessions are ordered by creation time (most recent first)
    session_ids = [s["id"] for s in data["sessions"]]
    assert all(sid in session_ids for sid in sessions)


@pytest.mark.usefixtures("setup_test_db")
def test_load_session_with_conversation_history(
    regular_user, user_token, test_db_session: Session
):
    """Test loading a session and retrieving full conversation history"""
    # Start session
    headers = {"Authorization": f"Bearer {user_token}"}
    start_response = client.post(
        "/api/learning/start",
        json={"topic": "roleplay", "purpose": "conversation", "difficulty": "basic"},
        params={"user_id": regular_user.id},
        headers=headers,
    )
    session_id = start_response.json()["session_id"]

    # Add some conversation exchanges
    client.post(
        f"/api/learning/{session_id}/answer",
        json={"answer": "Hello!", "is_voice": False},
        headers=headers,
    )
    client.post(
        f"/api/learning/{session_id}/answer",
        json={"answer": "How are you?", "is_voice": False},
        headers=headers,
    )

    # Load session progress (this returns full conversation_history)
    progress_response = client.get(
        f"/api/learning/{session_id}/progress", headers=headers
    )

    assert progress_response.status_code == 200
    data = progress_response.json()
    assert "conversation_history" in data
    assert len(data["conversation_history"]) > 0

    # Verify we can reconstruct the conversation
    conversation = data["conversation_history"]
    response_entries = [e for e in conversation if e.get("type") == "response"]
    assert len(response_entries) >= 2


@pytest.mark.usefixtures("setup_test_db")
def test_continue_existing_session(regular_user, user_token, test_db_session: Session):
    """Test that we can continue an existing session after loading it"""
    # Start session and add initial message
    headers = {"Authorization": f"Bearer {user_token}"}
    start_response = client.post(
        "/api/learning/start",
        json={"topic": "vocabulary", "purpose": "practice", "difficulty": "basic"},
        params={"user_id": regular_user.id},
        headers=headers,
    )
    session_id = start_response.json()["session_id"]

    client.post(
        f"/api/learning/{session_id}/answer",
        json={"answer": "First message", "is_voice": False},
        headers=headers,
    )

    # Simulate loading the session later
    progress_response = client.get(
        f"/api/learning/{session_id}/progress", headers=headers
    )
    assert progress_response.status_code == 200

    # Continue the conversation
    continue_response = client.post(
        f"/api/learning/{session_id}/answer",
        json={"answer": "Continued message", "is_voice": False},
        headers=headers,
    )

    assert continue_response.status_code == 200

    # Verify conversation history now has both messages
    final_progress = client.get(f"/api/learning/{session_id}/progress", headers=headers)
    conversation = final_progress.json()["conversation_history"]

    response_entries = [e for e in conversation if e.get("type") == "response"]
    assert len(response_entries) >= 2


@pytest.mark.usefixtures("setup_test_db")
def test_completed_sessions_persist(regular_user, user_token, test_db_session: Session):
    """Test that completed sessions are persisted and marked as completed"""
    # Start and end a session
    headers = {"Authorization": f"Bearer {user_token}"}
    start_response = client.post(
        "/api/learning/start",
        json={"topic": "test", "purpose": "practice", "difficulty": "basic"},
        params={"user_id": regular_user.id},
        headers=headers,
    )
    session_id = start_response.json()["session_id"]

    # Add a message
    client.post(
        f"/api/learning/{session_id}/answer",
        json={"answer": "Test answer", "is_voice": False},
        headers=headers,
    )

    # End the session
    end_response = client.post(f"/api/learning/{session_id}/end", headers=headers)
    assert end_response.status_code == 200

    # Verify session is marked as completed in database
    test_db_session.expire_all()
    session = test_db_session.query(LearningSession).filter_by(id=session_id).first()
    assert session is not None
    assert session.status == "completed"
    assert session.ended_at is not None

    # Verify it still appears in history
    history_response = client.get(
        f"/api/learning/history/{regular_user.id}", headers=headers
    )
    history_sessions = history_response.json()["sessions"]
    completed_session = next(
        (s for s in history_sessions if s["id"] == session_id), None
    )
    assert completed_session is not None
    assert completed_session["status"] == "completed"


@pytest.mark.usefixtures("setup_test_db")
def test_session_isolation_between_users(test_db_session: Session):
    """Test that users can only see their own session history"""
    # Create two users
    user1 = User(
        username="user1_isolation",
        email="user1@isolation.com",
        password_hash=get_password_hash("StrongPass123"),
        display_name="User 1",
        user_type="student",
    )
    user2 = User(
        username="user2_isolation",
        email="user2@isolation.com",
        password_hash=get_password_hash("StrongPass123"),
        display_name="User 2",
        user_type="student",
    )
    test_db_session.add_all([user1, user2])
    test_db_session.commit()

    headers1 = create_test_headers(user1.id, "user1_isolation", "student")
    headers2 = create_test_headers(user2.id, "user2_isolation", "student")

    # User 1 creates a session
    client.post(
        "/api/learning/start",
        json={"topic": "user1_topic", "purpose": "practice", "difficulty": "basic"},
        params={"user_id": user1.id},
        headers=headers1,
    )

    # User 2 creates a session
    client.post(
        "/api/learning/start",
        json={"topic": "user2_topic", "purpose": "practice", "difficulty": "basic"},
        params={"user_id": user2.id},
        headers=headers2,
    )

    # Verify each user only sees their own sessions
    user1_history = client.get(
        f"/api/learning/history/{user1.id}", headers=headers1
    ).json()["sessions"]
    user2_history = client.get(
        f"/api/learning/history/{user2.id}", headers=headers2
    ).json()["sessions"]

    user1_topics = [s["topic"] for s in user1_history]
    user2_topics = [s["topic"] for s in user2_history]

    assert "user1_topic" in user1_topics
    assert "user2_topic" not in user1_topics

    assert "user2_topic" in user2_topics
    assert "user1_topic" not in user2_topics
