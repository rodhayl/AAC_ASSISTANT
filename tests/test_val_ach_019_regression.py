"""VAL-ACH-019 regression: end a learning session without an LLM and auto-award First Steps.

Pins the no-LLM graceful-degradation path so that the auto-award of "First Steps"
on session end (without any explicit ``/check`` call) and the 200-with-summary
session-end behavior stay green. The claiming feature
``backend-learning-service-split-bugfixes`` finished the underlying work but the
contract assertion was never marked passed; this dedicated test enforces the
contract so the assertion cannot silently regress.

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
def test_val_ach_019_end_without_llm_returns_200_and_auto_awards_first_steps(
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

    # 2. Submit ONE conversational answer WITHOUT calling /ask first.
    #    Conversational answers do not increment questions_answered, so the
    #    comprehension score stays at 0 and the Comprehension Champion
    #    auto-award path (avg >= 0.8, 100 pts) cannot trigger.
    answer = client.post(
        f"/api/learning/{session_id}/answer",
        json={"answer": "I like dogs", "is_voice": False},
        headers=headers,
    )
    assert answer.status_code == 200, answer.text
    assert answer.json()["comprehension_score"] == 0.0

    # 3. End the session — POST must return 200 with success=true, summary,
    #    and a populated statistics block, even though no LLM provider is
    #    reachable. The end response shape MUST NOT change.
    ended = client.post(f"/api/learning/{session_id}/end", headers=headers)
    assert ended.status_code == 200, ended.text
    ended_data = ended.json()

    assert ended_data["success"] is True
    summary = ended_data.get("summary")
    assert summary, "summary must be populated on session end without an LLM"
    assert " " in summary, "summary must be human-readable localized text, not a raw key"

    stats = ended_data.get("statistics")
    assert stats is not None, "end response must include a statistics block"
    assert "questions_asked" in stats
    assert "questions_answered" in stats
    assert "correct_answers" in stats
    assert "comprehension_score" in stats
    assert stats["questions_answered"] == 0
    assert stats["correct_answers"] == 0
    assert stats["comprehension_score"] == 0.0

    # 4. /progress still returns 200 after /end.
    progress = client.get(f"/api/learning/{session_id}/progress", headers=headers)
    assert progress.status_code == 200, progress.text
    progress_data = progress.json()
    assert progress_data["success"] is True
    assert progress_data["status"] == "completed"

    # 5. Achievements list — WITHOUT any prior /check call — must show First
    #    Steps with a non-null earned_at (the end-of-session path auto-awards).
    achievements = client.get(
        f"/api/achievements/user/{student.id}", headers=headers
    )
    assert achievements.status_code == 200, achievements.text
    names_to_entry = {a["name"]: a for a in achievements.json()}

    assert "First Steps" in names_to_entry, names_to_entry
    first_steps = names_to_entry["First Steps"]
    assert first_steps["earned_at"] is not None
    assert first_steps["points"] == FIRST_STEPS_POINTS

    # Comprehension Champion must NOT be auto-awarded on this flow
    # (average comprehension is 0, well below the 0.8 threshold).
    cc_entry = names_to_entry.get("Comprehension Champion")
    if cc_entry is not None:  # it may legitimately be in the catalog
        assert cc_entry["earned_at"] is None, (
            "Comprehension Champion must not auto-award when avg comprehension < 0.8"
        )

    # 6. Points endpoint returns 10 (only First Steps).
    #    If Comprehension Champion were also auto-awarded (somehow), this would
    #    read 110, which the contract explicitly forbids in this flow.
    points = client.get(
        f"/api/achievements/user/{student.id}/points", headers=headers
    )
    assert points.status_code == 200, points.text
    assert points.json() == EXPECTED_TOTAL_POINTS, (
        "Expected 10 points (only First Steps). If Comprehension Champion was "
        f"auto-awarded, this would read {FIRST_STEPS_POINTS + COMPREHENSION_CHAMPION_POINTS}."
    )
