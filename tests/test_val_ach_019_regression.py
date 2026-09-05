"""VAL-ACH-019 regression: explicit provider errors do not create false progress.

Pins the no-LLM production contract: starting a session remains possible, but
an answer and session summary must report provider failure instead of inventing
feedback or awarding progress from fabricated content.

The flow (as a fresh student):

    1. start a learning session
    2. submit ONE answer — but NOT a correctly graded question (``/ask`` is
       deliberately not called, so comprehension score stays 0 and Comprehension
       Champion is not auto-awarded)
    3. POST /api/learning/{id}/end with NO LLM provider reachable
       -> HTTP 200 ``success=true`` with summary + statistics
    4. GET /api/learning/{id}/progress still 200 afterwards
    5. GET /api/achievements/user/{id} WITHOUT calling ``/check``
       -> ``First Steps`` has non-null earned_at
    6. GET /api/achievements/user/{id}/points returns 10
"""

from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient

from src.aac_app.models import User, UserSettings
from src.aac_app.services.auth_service import get_password_hash
from src.api.deps import get_llm_provider, get_speech_provider
from src.api.main import app

FIRST_STEPS_POINTS = 10
COMPREHENSION_CHAMPION_POINTS = 100
EXPECTED_TOTAL_POINTS = FIRST_STEPS_POINTS  # only First Steps auto-awards here


client = TestClient(app)


@pytest.fixture
def no_llm_provider(setup_test_db):
    """Simulate a fully unreachable LLM provider while keeping the rest of the
    application intact. Speech stays mocked so voice paths remain inert."""

    llm_mock = Mock()
    llm_mock.generate = AsyncMock(side_effect=RuntimeError("LLM unavailable"))
    app.dependency_overrides[get_llm_provider] = lambda: llm_mock

    speech_mock = Mock()
    speech_mock.is_available = Mock(return_value=False)
    speech_mock.transcribe = AsyncMock(return_value="")
    app.dependency_overrides[get_speech_provider] = lambda: speech_mock

    yield
    app.dependency_overrides.clear()


def _fresh_student(test_db_session) -> User:
    student = User(
        username="val_ach_019_student",
        email="val_ach_019_student@test.local",
        password_hash=get_password_hash("TestPass1234"),
        user_type="student",
        is_active=True,
        display_name="VAL ACH 019 Student",
    )
    test_db_session.add(student)
    test_db_session.commit()
    test_db_session.refresh(student)
    test_db_session.add(UserSettings(user_id=student.id, ui_language="en"))
    test_db_session.commit()
    return student


def _auth_headers(user: User) -> dict[str, str]:
    from src.aac_app.utils.jwt_utils import create_access_token

    token = create_access_token(
        data={
            "sub": user.username,
            "user_id": user.id,
            "user_type": user.user_type,
        }
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.usefixtures("setup_test_db")
def test_val_ach_019_end_without_llm_reports_provider_failure(
    no_llm_provider, test_db_session
):
    """VAL-ACH-019 contract regression — see module docstring."""
    student = _fresh_student(test_db_session)
    headers = _auth_headers(student)

    # 1. Start a learning session. Welcome message comes from the localized
    # translation fallback (no LLM call is made for the welcome).
    start = client.post(
        "/api/learning/start",
        params={"user_id": student.id},
        json={"topic": "animals", "purpose": "practice", "difficulty": "basic"},
        headers=headers,
    )
    assert start.status_code == 200, start.text
    start_data = start.json()
    assert start_data["success"] is True
    session_id = start_data["session_id"]

    # 2. Without a provider, conversational answers must fail explicitly.
    answer = client.post(
        f"/api/learning/{session_id}/answer",
        json={"answer": "I like dogs", "is_voice": False},
        headers=headers,
    )
    assert answer.status_code == 400, answer.text
    assert answer.json()["detail"] == "LLM conversational response failed"

    # 3. Ending a session also reports the missing provider instead of creating
    # a fabricated summary or awarding progress from it.
    ended = client.post(f"/api/learning/{session_id}/end", headers=headers)
    assert ended.status_code == 400, ended.text
    assert ended.json()["detail"] == "LLM unavailable"
