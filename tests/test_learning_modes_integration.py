"""
Tests for Learning Modes integration and regression testing for session conflicts.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session

from src.aac_app.models import LearningMode, User
from src.aac_app.services.auth_service import get_password_hash
from src.aac_app.services.guardian_profile_service import get_guardian_profile_service
from src.aac_app.services.learning.service import LearningCompanionService
from src.api.deps import get_llm_provider, get_speech_provider
from src.api.main import app


@pytest.fixture
def client(override_providers):
    """Use a scoped client whose lifespan follows dependency setup/cleanup."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def override_providers(
    mock_llm_provider,
    mock_speech_provider,
    test_db_session,
    test_db_engine,
    setup_test_db,
    monkeypatch,
):
    """Override provider dependencies with mocked versions"""
    from contextlib import contextmanager

    from src.aac_app import db
    from src.aac_app.services import achievement_system

    # Override providers
    app.dependency_overrides[get_llm_provider] = lambda: mock_llm_provider
    app.dependency_overrides[get_speech_provider] = lambda: mock_speech_provider

    # Each request/service call owns its own session. SQLAlchemy sessions are
    # not thread-safe and TestClient executes requests in another thread.
    from sqlalchemy.orm import sessionmaker

    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=test_db_engine,
    )

    @contextmanager
    def mock_get_session():
        session = TestingSessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    monkeypatch.setattr(db, "get_session", mock_get_session)
    monkeypatch.setattr(achievement_system, "get_session", mock_get_session)

    yield
    app.dependency_overrides.pop(get_llm_provider, None)
    app.dependency_overrides.pop(get_speech_provider, None)


@pytest.mark.usefixtures("setup_test_db")
def test_learning_mode_list_uses_one_query_and_scopes_custom_modes(
    admin_user, admin_token, test_db_session: Session, client
):
    """List returns defaults plus own modes in one query, excluding other users."""
    other_user = User(
        username="other_mode_owner",
        password_hash="test",
        display_name="Other Mode Owner",
        user_type="teacher",
        is_active=True,
    )
    test_db_session.add(other_user)
    test_db_session.flush()
    test_db_session.add_all(
        [
            LearningMode(
                name="System Mode",
                key="system_mode",
                prompt_instruction="Use the system learning style.",
                created_by=None,
                is_custom=False,
            ),
            LearningMode(
                name="Own Mode",
                key="own_mode",
                prompt_instruction="Use the owner's learning style.",
                created_by=admin_user.id,
                is_custom=True,
                auto_ask_enabled=False,
            ),
            LearningMode(
                name="Other Mode",
                key="other_mode",
                prompt_instruction="Use another owner's learning style.",
                created_by=other_user.id,
                is_custom=True,
            ),
        ]
    )
    test_db_session.commit()

    headers = {"Authorization": f"Bearer {admin_token}"}
    mode_statement_count = 0

    def count_statements(_conn, _cursor, statement, _parameters, _context, _executemany):
        nonlocal mode_statement_count
        if "learning_modes" in statement.lower():
            mode_statement_count += 1

    event.listen(test_db_session.bind, "before_cursor_execute", count_statements)
    try:
        response = client.get("/api/learning-modes/", headers=headers)
    finally:
        event.remove(test_db_session.bind, "before_cursor_execute", count_statements)

    assert response.status_code == 200, response.text
    assert mode_statement_count == 1
    modes = response.json()
    names = [mode["name"] for mode in modes]
    assert "System Mode" in names
    assert "Own Mode" in names
    assert "Other Mode" not in names
    assert [mode["id"] for mode in modes] == sorted(mode["id"] for mode in modes)
    own = next(mode for mode in modes if mode["name"] == "Own Mode")
    assert own["auto_ask_enabled"] is False


@pytest.mark.usefixtures("setup_test_db")
def test_learning_mode_preview_does_not_leak_other_teachers_prompt(
    admin_user, test_db_session: Session, client
):
    """A teacher cannot preview a saved mode owned by another teacher."""
    from src.aac_app.utils.jwt_utils import create_access_token

    owner = User(
        username="private_mode_owner",
        password_hash=get_password_hash("OwnerPass123"),
        display_name="Private Mode Owner",
        user_type="teacher",
        is_active=True,
    )
    viewer = User(
        username="private_mode_viewer",
        password_hash=get_password_hash("ViewerPass123"),
        display_name="Private Mode Viewer",
        user_type="teacher",
        is_active=True,
    )
    test_db_session.add_all([owner, viewer])
    test_db_session.flush()
    mode = LearningMode(
        name="Private Mode",
        key="private_mode_key",
        prompt_instruction="Do not expose this teacher's private instruction.",
        created_by=owner.id,
        is_custom=True,
    )
    test_db_session.add(mode)
    test_db_session.commit()

    token = create_access_token(
        data={"sub": viewer.username, "user_id": viewer.id, "user_type": viewer.user_type}
    )
    response = client.post(
        "/api/learning-modes/preview",
        json={"mode_key": mode.key, "prompt_instruction": mode.prompt_instruction},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


@pytest.mark.usefixtures("setup_test_db")
def test_learning_mode_auto_ask_enabled_flag_roundtrip(
    admin_user, admin_token, test_db_session: Session, client
):
    """auto_ask_enabled defaults on, persists through create/update, and is listed."""
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Default is enabled when omitted
    default_create = client.post(
        "/api/learning-modes/",
        json={
            "name": "Quiz Mode",
            "key": "quiz_default",
            "description": "Question drills",
            "prompt_instruction": "Ask one question at a time.",
        },
        headers=headers,
    )
    assert default_create.status_code == 200, default_create.text
    assert default_create.json()["auto_ask_enabled"] is True

    # Create a conversational mode with auto-asking disabled
    create = client.post(
        "/api/learning-modes/",
        json={
            "name": "Role Play",
            "key": "roleplay_no_auto",
            "description": "Conversational role play",
            "prompt_instruction": "Act as a friendly shopkeeper.",
            "auto_ask_enabled": False,
        },
        headers=headers,
    )
    assert create.status_code == 200, create.text
    mode_id = create.json()["id"]
    assert create.json()["auto_ask_enabled"] is False

    # The list exposes the flag
    modes = client.get("/api/learning-modes/", headers=headers).json()
    saved = next(m for m in modes if m["id"] == mode_id)
    assert saved["auto_ask_enabled"] is False

    # Re-enable auto-asking through the update endpoint
    update = client.put(
        f"/api/learning-modes/{mode_id}",
        json={"auto_ask_enabled": True},
        headers=headers,
    )
    assert update.status_code == 200, update.text
    assert update.json()["auto_ask_enabled"] is True

    modes_after = client.get("/api/learning-modes/", headers=headers).json()
    saved_after = next(m for m in modes_after if m["id"] == mode_id)
    assert saved_after["auto_ask_enabled"] is True


@pytest.mark.usefixtures("setup_test_db")
def test_learning_mode_duplicate_error_is_localized(admin_token, client):
    """Duplicate mode errors must not leak a raw English-only implementation string."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    existing_key = "duplicate_localized_mode"
    created = client.post(
        "/api/learning-modes/",
        json={
            "name": "Original",
            "key": existing_key,
            "prompt_instruction": "Be encouraging.",
        },
        headers=headers,
    )
    assert created.status_code == 200, created.text

    response = client.post(
        "/api/learning-modes/",
        json={
            "name": "Duplicate",
            "key": existing_key,
            "prompt_instruction": "Be concise.",
        },
        headers=headers,
    )

    assert response.status_code == 400
    assert response.json()["detail"] != f"Mode with key '{existing_key}' already exists"
    assert response.json()["detail"] != "errors.learningModes.duplicate"


@pytest.mark.usefixtures("setup_test_db")
def test_learning_chat_with_custom_mode_regression(
    admin_user, admin_token, test_db_session: Session, client
):
    """
    Regression test for variable shadowing in the learning service.

    The bug caused a session conflict when a LearningMode lookup (inner session)
    occurred within the process_response (outer session) block.
    """

    # 1. Create a custom Learning Mode
    # We can do this directly in DB or via API. Let's use DB to be fast.
    custom_mode = LearningMode(
        name="Regression Test Mode",
        key="regression_mode",
        description="A mode for testing regressions",
        prompt_instruction="Respond with 'Regression Test Passed'",
        created_by=admin_user.id,
        is_custom=True
    )
    test_db_session.add(custom_mode)
    test_db_session.commit()

    # 2. Start a session using this mode
    headers = {"Authorization": f"Bearer {admin_token}"}
    start_response = client.post(
        "/api/learning/start",
        json={"topic": "testing", "purpose": "regression_mode", "difficulty": "basic"},
        params={"user_id": admin_user.id},
        headers=headers,
    )

    assert start_response.status_code == 200
    session_id = start_response.json()["session_id"]

    # 3. Send a message
    # This triggers process_response -> _get_system_prompt -> DB lookup for mode
    # If variable shadowing exists, this will fail with 500 or "Object attached to another session"
    answer_response = client.post(
        f"/api/learning/{session_id}/answer",
        json={"answer": "Hello test", "is_voice": False},
        headers=headers,
    )

    # 4. Verify success
    assert answer_response.status_code == 200
    data = answer_response.json()
    assert data["success"] is True
    # The mocked LLM should return something, we don't care exactly what,
    # as long as the request succeeded without crashing.


@pytest.mark.usefixtures("setup_test_db")
def test_mode_prompt_instruction_reaches_llm_system_prompt(
    admin_user, admin_token, test_db_session: Session, mock_llm_provider, client
):
    """
    Verify that a session started with a Learning Mode key actually appends
    the mode's prompt_instruction to the system prompt sent to the LLM.

    Regression: previously the mode dropdown was purely cosmetic - the
    prompt_instruction was stored but never applied to the conversation.
    """

    # 1. Create a custom Learning Mode with a distinctive instruction
    custom_mode = LearningMode(
        name="Andalusian Mode",
        key="andalusian",
        description="Hablante andaluz exagerado",
        prompt_instruction=(
            "Habla de forma exagerada como si fueras de la Andalucía profunda."
        ),
        created_by=admin_user.id,
        is_custom=True,
    )
    test_db_session.add(custom_mode)
    test_db_session.commit()

    # 2. Start a session passing the mode key
    headers = {"Authorization": f"Bearer {admin_token}"}
    start_response = client.post(
        "/api/learning/start",
        json={"topic": "animals", "purpose": "practice", "mode_key": "andalusian"},
        params={"user_id": admin_user.id},
        headers=headers,
    )
    assert start_response.status_code == 200
    session_id = start_response.json()["session_id"]

    # 3. Store the session's mode key (round-trip check)
    stored_session = test_db_session.get(
        __import__("src.aac_app.models", fromlist=["LearningSession"]).LearningSession,
        session_id,
    )
    assert stored_session.mode_key == "andalusian"

    # 4. Send a message; the LLM system prompt must include the mode instruction
    mock_llm_provider.generate.reset_mock()
    answer_response = client.post(
        f"/api/learning/{session_id}/answer",
        json={"answer": "Hola", "is_voice": False},
        headers=headers,
    )
    assert answer_response.status_code == 200

    assert mock_llm_provider.generate.await_count >= 1
    call = mock_llm_provider.generate.await_args_list[-1]
    system = call.kwargs.get("system") or call.kwargs.get("system_prompt") or ""
    assert "Andalucía profunda" in system, (
        "Mode prompt_instruction was not appended to the LLM system prompt"
    )

    # The conversational user prompt uses the same template as the Settings
    # preview (build_conversation_user_prompt): the student's message and the
    # session topic must appear verbatim. (Temperature/max-tokens forwarding
    # is covered separately in test_llm_behavior_settings.py.)
    user_prompt = call.kwargs.get("prompt") or ""
    assert "Student's latest message: Hola" in user_prompt
    assert "Topic: animals" in user_prompt

    # 5. A session WITHOUT a mode key must not inject the instruction
    mock_llm_provider.generate.reset_mock()
    start_plain = client.post(
        "/api/learning/start",
        json={"topic": "animals", "purpose": "practice"},
        params={"user_id": admin_user.id},
        headers=headers,
    )
    plain_session_id = start_plain.json()["session_id"]
    client.post(
        f"/api/learning/{plain_session_id}/answer",
        json={"answer": "Hola", "is_voice": False},
        headers=headers,
    )
    call_plain = mock_llm_provider.generate.await_args_list[-1]
    system_plain = call_plain.kwargs.get("system") or call_plain.kwargs.get("system_prompt") or ""
    assert "Andalucía profunda" not in system_plain


@pytest.mark.usefixtures("setup_test_db")
def test_preview_system_prompt_default(admin_user, admin_token, test_db_session: Session, client):
    """
    The preview endpoint renders the exact prompt for an unsaved mode.

    Without a selected student the base (default) prompt plus the mode's
    instruction is returned, and it must be identical to what the learning
    service would assemble for a session.
    """
    headers = {"Authorization": f"Bearer {admin_token}"}
    instruction = "Responde siempre de forma exagerada como andaluz."

    response = client.post(
        "/api/learning-modes/preview",
        json={"prompt_instruction": instruction},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["has_guardian_profile"] is False
    assert data["template_name"] == "default"
    assert data["mode_instruction"] == instruction
    assert instruction in data["prompt"]

    # Exactness: the endpoint output is what the service would send.
    service = LearningCompanionService(object(), object())
    expected = service.preview_system_prompt(
        user_id=admin_user.id,
        mode_instruction=instruction,
        db=test_db_session,
    )
    assert data["prompt"] == expected


@pytest.mark.usefixtures("setup_test_db")
def test_preview_system_prompt_with_guardian_profile(
    admin_user, admin_token, test_db_session: Session, client
):
    """
    Previewing against a student includes their guardian profile content.
    """
    student = User(
        username="student_preview",
        email="student_preview@test.com",
        password_hash=get_password_hash("TestPassword123"),
        user_type="student",
        is_active=True,
        display_name="Student Preview",
    )
    test_db_session.add(student)
    test_db_session.commit()
    test_db_session.refresh(student)

    guardian_service = get_guardian_profile_service()
    guardian_service.update_profile(
        student_id=student.id,
        updated_by=admin_user.id,
        changes={"custom_instructions": "El estudiante prefiere frases cortas y mucho ánimo."},
        change_reason="test",
        db=test_db_session,
    )
    test_db_session.commit()

    instruction = "Usa vocabulario de animales."
    headers = {"Authorization": f"Bearer {admin_token}"}
    response = client.post(
        "/api/learning-modes/preview",
        json={"prompt_instruction": instruction, "student_id": student.id},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["has_guardian_profile"] is True
    assert data["template_name"] == "default"
    # Guardian profile content AND the mode instruction are both present.
    assert "frases cortas" in data["prompt"]
    assert instruction in data["prompt"]


@pytest.mark.usefixtures("setup_test_db")
def test_preview_system_prompt_forbidden_for_non_staff(regular_user, user_token, client):
    """Students cannot preview system prompts."""
    response = client.post(
        "/api/learning-modes/preview",
        json={"prompt_instruction": "x"},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert response.status_code == 403


@pytest.mark.usefixtures("setup_test_db")
def test_preview_system_prompt_with_sample_question(
    admin_user, admin_token, test_db_session: Session, client
):
    """
    Previewing with a sample question returns the full LLM request: the system
    prompt plus the exact user message the conversational path would build.
    """
    instruction = "Habla como un andaluz exagerado."
    question = "¿Por qué llueve?"
    headers = {"Authorization": f"Bearer {admin_token}"}

    response = client.post(
        "/api/learning-modes/preview",
        json={"prompt_instruction": instruction, "sample_question": question},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()

    # The rendered user message contains the student's question and topic.
    assert data["user_message"]
    assert question in data["user_message"]
    assert "general conversation" in data["user_message"]

    # The full chat request is returned as [system, user].
    assert data["messages"] is not None
    assert len(data["messages"]) == 2
    assert data["messages"][0]["role"] == "system"
    assert data["messages"][0]["content"] == data["prompt"]
    assert data["messages"][1]["role"] == "user"
    assert data["messages"][1]["content"] == data["user_message"]

    # Model parameters used by the conversational path are included.
    assert data["temperature"] is not None
    assert data["max_tokens"] is not None

    # Exactness: the endpoint uses the same builder as the real session path.
    service = LearningCompanionService(object(), object())
    expected_message = service.build_conversation_user_prompt(
        student_message=question,
        topic="general conversation",
        lang=service._get_user_language(admin_user.id, db=test_db_session),
    )
    assert data["user_message"] == expected_message

    # Without a sample question no user message is rendered.
    plain = client.post(
        "/api/learning-modes/preview",
        json={"prompt_instruction": instruction},
        headers=headers,
    ).json()
    assert plain["user_message"] is None
    assert plain["messages"] is None


@pytest.mark.usefixtures("setup_test_db")
def test_student_cannot_create_learning_mode(regular_user, user_token, client):
    """Non-staff users cannot create custom learning modes (403)."""
    response = client.post(
        "/api/learning-modes/",
        json={
            "name": "Sneaky Mode",
            "key": "sneaky",
            "prompt_instruction": "Do nothing.",
        },
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert response.status_code == 403


def test_update_learning_mode_full_field_roundtrip(
    admin_user, admin_token, test_db_session: Session, client
):
    """Updating every editable field at once persists all values."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    created = client.post(
        "/api/learning-modes/",
        json={
            "name": "Before",
            "key": "full_update_mode",
            "description": "old description",
            "prompt_instruction": "old instruction",
            "auto_ask_enabled": True,
        },
        headers=headers,
    )
    assert created.status_code == 200
    mode_id = created.json()["id"]

    updated = client.put(
        f"/api/learning-modes/{mode_id}",
        json={
            "name": "After",
            "description": "new description",
            "prompt_instruction": "new instruction",
            "auto_ask_enabled": False,
        },
        headers=headers,
    )
    assert updated.status_code == 200
    data = updated.json()
    assert data["name"] == "After"
    assert data["description"] == "new description"
    assert data["prompt_instruction"] == "new instruction"
    assert data["auto_ask_enabled"] is False


def test_update_learning_mode_returns_404_for_missing(
    admin_user, admin_token, client
):
    response = client.put(
        "/api/learning-modes/999999",
        json={"name": "Ghost"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 404


def test_teacher_cannot_edit_system_mode(
    test_db_session: Session, admin_user, admin_token, client
):
    """System modes (created_by=None) are editable only by admins."""
    system_mode = LearningMode(
        name="System Mode",
        key="system_edit_protected",
        prompt_instruction="System instructions.",
        created_by=None,
        is_custom=False,
    )
    test_db_session.add(system_mode)
    test_db_session.commit()
    test_db_session.refresh(system_mode)

    teacher = User(
        username="edit_blocked_teacher",
        display_name="Edit Blocked Teacher",
        user_type="teacher",
        password_hash=get_password_hash("TeacherPass123"),
        is_active=True,
    )
    test_db_session.add(teacher)
    test_db_session.commit()

    from src.aac_app.utils.jwt_utils import create_access_token

    teacher_token = create_access_token(
        data={
            "sub": teacher.username,
            "user_id": teacher.id,
            "user_type": teacher.user_type,
        }
    )
    response = client.put(
        f"/api/learning-modes/{system_mode.id}",
        json={"name": "Hijacked"},
        headers={"Authorization": f"Bearer {teacher_token}"},
    )
    assert response.status_code == 403


def test_delete_learning_mode_permissions_and_404(
    admin_user, admin_token, test_db_session: Session, client
):
    """Non-admin cannot delete a system mode; missing modes return 404."""
    system_mode = LearningMode(
        name="System Protected",
        key="system_delete_protected",
        prompt_instruction="Keep me.",
        created_by=None,
        is_custom=False,
    )
    test_db_session.add(system_mode)
    test_db_session.commit()
    test_db_session.refresh(system_mode)

    teacher = User(
        username="delete_blocked_teacher",
        display_name="Delete Blocked Teacher",
        user_type="teacher",
        password_hash=get_password_hash("TeacherPass123"),
        is_active=True,
    )
    test_db_session.add(teacher)
    test_db_session.commit()

    from src.aac_app.utils.jwt_utils import create_access_token

    teacher_token = create_access_token(
        data={
            "sub": teacher.username,
            "user_id": teacher.id,
            "user_type": teacher.user_type,
        }
    )
    headers = {"Authorization": f"Bearer {teacher_token}"}

    # Teacher cannot delete a system mode.
    forbidden = client.delete(f"/api/learning-modes/{system_mode.id}", headers=headers)
    assert forbidden.status_code == 403

    # Missing mode -> 404 for any authenticated user.
    missing = client.delete(
        "/api/learning-modes/999999",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert missing.status_code == 404

    # Admin can delete the system mode.
    deleted = client.delete(
        f"/api/learning-modes/{system_mode.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert deleted.status_code == 200
    assert deleted.json()["success"] is True
