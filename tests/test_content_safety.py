"""Layered content-safety tests: deterministic filters, policy resolution,
and enforcement across prediction, autogen, learning chat, boards, and the
admin/teacher API surface."""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.aac_app.models import (
    ContentSafetyEvent,
    GuardianProfile,
    LearningSession,
    StudentTeacher,
    Symbol,
    User,
)
from src.aac_app.services.content_safety import (
    ContentPolicy,
    check_text,
    default_level_for_age,
    normalize_text,
    resolve_policy_for_user,
    save_global_policy,
)
from src.api.main import app
from tests.auth_helpers import create_test_token

client = TestClient(app)
pytestmark = pytest.mark.usefixtures("setup_test_db")


def _make_user(test_db_session, username, user_type, password="TestPassword123"):
    from src.aac_app.services.auth_service import get_password_hash

    user = User(
        username=username,
        email=f"{username}@test.com",
        password_hash=get_password_hash(password),
        user_type=user_type,
        is_active=True,
        display_name=username.title(),
    )
    test_db_session.add(user)
    test_db_session.commit()
    test_db_session.refresh(user)
    return user


def _headers(user) -> dict:
    return {
        "Authorization": f"Bearer {create_test_token(user.id, user.username, user.user_type)}"
    }


# --- deterministic filter ---------------------------------------------------


def test_normalize_text_folds_accents_and_case():
    # Inverted punctuation is kept; accents and case are folded, runs of
    # whitespace collapse to a single space.
    assert normalize_text("¡Hola, ¿Qué Tal?  CÉLULA!") == "¡hola, ¿que tal? celula!"
    assert normalize_text("") == ""
    assert normalize_text(None) == ""


def test_check_text_blocks_per_family_at_each_level():
    standard = ContentPolicy(level="standard")
    strict = ContentPolicy(level="strict")
    relaxed = ContentPolicy(level="relaxed")
    # Adult and self-harm are blocked at every level.
    assert check_text(standard, "quiero hablar de sexo").blocked
    assert check_text(relaxed, "me duele, quiero morir").blocked
    # Weapons/profanity only at standard/strict (not relaxed).
    assert check_text(standard, "hablemos de pistolas").blocked
    assert not check_text(relaxed, "hablemos de pistolas").blocked
    assert check_text(strict, "eres un idiota").blocked
    assert not check_text(standard, "eres un idiota").blocked


def test_check_text_never_blocks_everyday_aac_vocabulary():
    base = ContentPolicy(level="strict")
    for text in (
        "la célula", "célula animal", "quiero agua", "estropeado",
        "estoy triste porque perdí mi juguete", "la muerte de la célula",
        "me duele la barriga", "coger el autobús",
    ):
        assert check_text(base, text).allowed, text


def test_check_text_handles_plurals_and_family_audit():
    standard = ContentPolicy(level="standard")
    verdict = check_text(standard, "las bombas y pistolas")
    assert verdict.blocked
    assert "weapons" in verdict.matched_families
    assert any("weapons" in t or t in ("bomba", "pistola") for t in verdict.matched_terms)


def test_check_text_uses_custom_topics_and_trigger_words():
    policy = ContentPolicy(
        level="standard",
        forbidden_topics=("astronomía",),
        trigger_words=("guerra",),
    )
    assert check_text(policy, "me encanta la astronomia").blocked
    assert check_text(policy, "hay guerra").blocked
    assert check_text(policy, "me gustan las estrellas").allowed


def test_default_level_for_age():
    assert default_level_for_age(6) == "strict"
    assert default_level_for_age(10) == "standard"
    assert default_level_for_age(16) == "relaxed"
    assert default_level_for_age(None) == "standard"


def test_feature_locks():
    policy = ContentPolicy(feature_locks={"block_ai_chat": True})
    assert policy.feature_blocked("block_ai_chat")
    assert not policy.feature_blocked("block_board_ai")


# --- Layer 2: strict moderation sentinel ------------------------------------


def test_moderate_output_inactive_for_standard_level():
    from src.aac_app.services.content_safety import moderate_output

    async def generate(**kwargs):
        raise AssertionError("sentinel must not call the LLM off-strict")

    policy = ContentPolicy(level="standard", sentinel_moderation=True)
    verdict = asyncio.run(moderate_output(generate, policy, "hola"))
    assert verdict.allowed


def test_moderate_output_requires_sentinel_flag():
    from src.aac_app.services.content_safety import moderate_output

    async def generate(**kwargs):
        raise AssertionError("sentinel must not call the LLM without the flag")

    policy = ContentPolicy(level="strict", sentinel_moderation=False)
    verdict = asyncio.run(moderate_output(generate, policy, "hola"))
    assert verdict.allowed


def test_moderate_output_blocks_on_llm_verdict(test_db_session):
    from src.aac_app.services.content_safety import moderate_output

    async def generate(**kwargs):
        return "BLOCKED"

    policy = ContentPolicy(level="strict", sentinel_moderation=True)
    verdict = asyncio.run(
        moderate_output(generate, policy, "algo inapropiado", db=test_db_session)
    )
    assert verdict.blocked
    assert "sentinel" in verdict.matched_terms
    event = (
        test_db_session.query(ContentSafetyEvent)
        .filter(ContentSafetyEvent.surface == "sentinel")
        .first()
    )
    assert event is not None and event.verdict == "blocked"


def test_moderate_output_passes_and_fails_open(test_db_session, monkeypatch):
    from src.aac_app.services.content_safety import moderate_output

    async def generate(**kwargs):
        return "ALLOWED"

    policy = ContentPolicy(level="strict", sentinel_moderation=True)
    verdict = asyncio.run(
        moderate_output(generate, policy, "texto normal", db=test_db_session)
    )
    assert verdict.allowed

    # Provider errors fail open: never block the child's chat.
    async def broken(**kwargs):
        raise RuntimeError("provider down")

    verdict = asyncio.run(
        moderate_output(broken, policy, "texto", db=test_db_session)
    )
    assert verdict.allowed


def test_moderate_output_respects_daily_cap(test_db_session, monkeypatch):
    import src.aac_app.services.content_safety as safety

    calls: list[str] = []

    async def generate(**kwargs):
        calls.append(kwargs.get("prompt", ""))
        return "ALLOWED"

    policy = ContentPolicy(level="strict", sentinel_moderation=True)
    monkeypatch.setattr(safety, "_sentinel_daily_cap", lambda: 1)
    first = asyncio.run(
        safety.moderate_output(generate, policy, "texto 1", db=test_db_session)
    )
    assert first.allowed and len(calls) == 1
    second = asyncio.run(
        safety.moderate_output(generate, policy, "texto 2", db=test_db_session)
    )
    assert second.allowed and len(calls) == 1  # no second LLM call


def test_learning_question_output_gate_blocks_blocked_question(
    test_db_session, regular_user, mock_llm_provider, mock_speech_provider
):
    """A generated question whose text/choices trip the deterministic filter
    is replaced by a safe neutral question and logged."""
    from src.aac_app.services.learning.service import LearningCompanionService

    # Profanity is strict-only; use a trigger word so standard suffices.
    test_db_session.add(
        GuardianProfile(
            user_id=regular_user.id,
            template_name="default",
            safety_constraints={"trigger_words": ["guerra"]},
            is_active=True,
            created_by=regular_user.id,
        )
    )
    session = LearningSession(
        user_id=regular_user.id,
        topic_name="frutas",
        purpose="",
        status="active",
        conversation_history=[],
        comprehension_score=0.0,
    )
    test_db_session.add(session)
    test_db_session.commit()

    async def generate(**kwargs):
        prompt = kwargs.get("prompt", "")
        if "Generate a " in prompt and "level question" in prompt:
            return (
                '{"question": "¿Qué es la guerra?", '
                '"choices": ["Conflicto", "Manzana", "Agua"], "correct": 0}'
            )
        return '{"response": "ok"}'

    mock_llm_provider.generate = AsyncMock(side_effect=generate)
    service = LearningCompanionService(mock_llm_provider, mock_speech_provider)

    result = asyncio.run(
        service.ask_question(session_id=session.id, db=test_db_session)
    )
    assert result["success"] is True
    assert "guerra" not in result["question_text"]
    # The safe fallback question (Spanish user locale).
    assert "saludar" in result["question_text"]
    assert "Hola" in result["choices"]
    event = (
        test_db_session.query(ContentSafetyEvent)
        .filter(ContentSafetyEvent.user_id == regular_user.id)
        .filter(ContentSafetyEvent.surface == "chat")
        .first()
    )
    assert event is not None and event.verdict == "redirected"


def test_learning_summary_output_gate_replaces_blocked_summary(
    test_db_session, regular_user, mock_llm_provider, mock_speech_provider
):
    """An end-of-session summary that trips the filter is replaced by a
    neutral fallback and logged."""
    from src.aac_app.services.learning.service import LearningCompanionService

    test_db_session.add(
        GuardianProfile(
            user_id=regular_user.id,
            template_name="default",
            safety_constraints={"trigger_words": ["guerra"]},
            is_active=True,
            created_by=regular_user.id,
        )
    )
    session = LearningSession(
        user_id=regular_user.id,
        topic_name="frutas",
        purpose="",
        status="active",
        conversation_history=[],
        comprehension_score=0.5,
        questions_answered=2,
        correct_answers=1,
    )
    test_db_session.add(session)
    test_db_session.commit()

    async def generate(**kwargs):
        prompt = kwargs.get("prompt", "")
        if "summary" in prompt.lower():
            return "¡Has aprendido mucho sobre la guerra!"
        return "ok"

    mock_llm_provider.generate = AsyncMock(side_effect=generate)
    service = LearningCompanionService(mock_llm_provider, mock_speech_provider)

    result = asyncio.run(
        service.end_learning_session(session_id=session.id, db=test_db_session)
    )
    assert result["success"] is True
    assert "guerra" not in result["summary"]
    assert "Buen trabajo" in result["summary"] or "Great work" in result["summary"]
    event = (
        test_db_session.query(ContentSafetyEvent)
        .filter(ContentSafetyEvent.user_id == regular_user.id)
        .filter(ContentSafetyEvent.verdict == "redirected")
        .first()
    )
    assert event is not None


def test_learning_response_sentinel_blocks_flagged_output(
    test_db_session, regular_user, mock_llm_provider, mock_speech_provider
):
    from src.aac_app.services.learning.service import LearningCompanionService

    def strict_profile():
        test_db_session.add(
            GuardianProfile(
                user_id=regular_user.id,
                template_name="default",
                safety_constraints={
                    "content_filter_level": "strict",
                    "sentinel_moderation": True,
                },
                is_active=True,
                created_by=regular_user.id,
            )
        )

    strict_profile()
    session = LearningSession(
        user_id=regular_user.id,
        topic_name="frutas",
        purpose="",
        status="active",
        conversation_history=[],
        comprehension_score=0.0,
    )
    test_db_session.add(session)
    test_db_session.commit()

    # The conversational response passes the deterministic filter but the
    # sentinel flags it; the deflection replaces the message.
    async def generate(**kwargs):
        prompt = kwargs.get("prompt", "")
        if "moderate" in prompt.lower() or "allowed or blocked" in prompt.lower():
            return "BLOCKED"
        return '{"response": "Vamos a hablar de animales"}'

    mock_llm_provider.generate = AsyncMock(side_effect=generate)
    service = LearningCompanionService(mock_llm_provider, mock_speech_provider)

    result = asyncio.run(
        service.process_response(
            session_id=session.id,
            student_response="quiero aprender de animales",
            db=test_db_session,
        )
    )
    assert result["success"] is True
    assert "Vamos a hablar de animales" not in result["feedback_message"]
    assert "otra cosa" in result["feedback_message"]
    sentinel_events = (
        test_db_session.query(ContentSafetyEvent)
        .filter(ContentSafetyEvent.surface == "sentinel")
        .all()
    )
    assert len(sentinel_events) == 1 and sentinel_events[0].verdict == "blocked"


# --- policy resolution ------------------------------------------------------


def test_resolve_policy_merges_guardian_profile_overrides(test_db_session):
    student = _make_user(test_db_session, "safety_student1", "student")
    profile = GuardianProfile(
        user_id=student.id,
        template_name="default",
        safety_constraints={
            "content_filter_level": "strict",
            "trigger_words": ["violencia"],
            "block_ai_chat": True,
        },
        is_active=True,
        created_by=student.id,
    )
    test_db_session.add(profile)
    test_db_session.commit()

    policy = resolve_policy_for_user(student.id, db=test_db_session)
    assert policy.level == "strict"
    assert "violencia" in policy.trigger_words
    assert policy.feature_blocked("block_ai_chat")
    # No guardian profile → global defaults.
    assert resolve_policy_for_user(None).level == "standard"


def test_resolve_policy_ignores_inactive_guardian_profile(test_db_session):
    """Soft-deleted profile settings must not remain an active policy source."""
    import src.aac_app.services.content_safety as safety

    student = _make_user(test_db_session, "safety_inactive_profile", "student")
    test_db_session.add(
        GuardianProfile(
            user_id=student.id,
            template_name="default",
            safety_constraints={
                "content_filter_level": "strict",
                "trigger_words": ["private-trigger"],
                "block_ai_chat": True,
            },
            is_active=False,
            created_by=student.id,
        )
    )
    test_db_session.commit()
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        safety, "load_global_policy", lambda: ContentPolicy(level="relaxed")
    )
    try:
        policy = safety.resolve_policy_for_user(student.id, db=test_db_session)
        assert policy.level == "relaxed"
        assert "private-trigger" not in policy.trigger_words
        assert not policy.feature_blocked("block_ai_chat")
    finally:
        monkeypatch.undo()


def test_resolve_policy_applies_age_floor_when_no_level_set(test_db_session):
    """A young student without a teacher-set level gets the age-based strict
    floor even when the admin global level is relaxed."""
    import src.aac_app.services.content_safety as safety

    student = _make_user(test_db_session, "safety_age1", "student")
    test_db_session.add(
        GuardianProfile(
            user_id=student.id,
            template_name="default",
            age=6,
            safety_constraints={},
            is_active=True,
            created_by=student.id,
        )
    )
    test_db_session.commit()
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        safety, "load_global_policy", lambda: ContentPolicy(level="relaxed")
    )
    try:
        policy = safety.resolve_policy_for_user(student.id, db=test_db_session)
        assert policy.level == "strict"  # age 6 → strict, tighter than relaxed
    finally:
        monkeypatch.undo()


def test_resolve_policy_teacher_level_wins_over_age_floor(test_db_session):
    """An explicit teacher-set level overrides the age-based default."""
    import src.aac_app.services.content_safety as safety

    student = _make_user(test_db_session, "safety_age2", "student")
    test_db_session.add(
        GuardianProfile(
            user_id=student.id,
            template_name="default",
            age=6,
            safety_constraints={"content_filter_level": "relaxed"},
            is_active=True,
            created_by=student.id,
        )
    )
    test_db_session.commit()
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        safety, "load_global_policy", lambda: ContentPolicy(level="relaxed")
    )
    try:
        policy = safety.resolve_policy_for_user(student.id, db=test_db_session)
        assert policy.level == "relaxed"  # explicit teacher choice respected
    finally:
        monkeypatch.undo()


def test_save_global_policy_roundtrip(test_db_session):
    policy = save_global_policy(
        {
            "level": "strict",
            "forbidden_topics": ["astronomía"],
            "trigger_words": ["guerra"],
            "feature_locks": {"block_board_ai": True, "block_ai_chat": False},
            "sentinel_moderation": True,
            "max_response_length": 30,
            "locked_fields": ["block_ai_chat"],
        }
    )
    assert policy.level == "strict"
    assert policy.feature_blocked("block_board_ai")
    assert not policy.feature_blocked("block_ai_chat")
    assert policy.max_response_length == 30


def test_save_global_policy_invalidates_settings_cache(test_db_session):
    """Regression: saving the global policy must invalidate the process-local
    settings cache, otherwise every read (including the admin PUT response
    itself) returns the stale first-read value and saves appear to no-op."""
    import src.aac_app.services.content_safety as safety_mod
    from src.api.deps.settings import clear_settings_cache, get_setting_value

    clear_settings_cache()
    try:
        # Prime the cache with the current (default) value, then save over it.
        assert safety_mod.load_global_policy().level == "standard"
        save_global_policy(
            {
                "level": "strict",
                "forbidden_topics": ["guerra", "violencia"],
                "trigger_words": ["matar"],
                "feature_locks": {},
                "sentinel_moderation": True,
                "max_response_length": None,
                "locked_fields": [],
            }
        )
        # The cached getter (used by load_global_policy / the GET endpoint)
        # must now see the fresh value without an explicit cache clear.
        assert get_setting_value(safety_mod.GLOBAL_POLICY_KEY, "") != ""
        assert safety_mod.load_global_policy().level == "strict"
        assert safety_mod.load_global_policy().forbidden_topics == ("guerra", "violencia")
        assert safety_mod.load_global_policy().trigger_words == ("matar",)
    finally:
        clear_settings_cache()


# --- Layer 0: prompt guardrails from the resolved policy --------------------


def test_system_prompt_inherits_admin_global_terms(
    test_db_session, regular_user, monkeypatch
):
    """A student with no guardian profile must still get the admin global
    forbidden topics and trigger words in the system prompt (Layer 0)."""
    import src.aac_app.services.content_safety as safety
    from src.aac_app.services.guardian_profile_service import (
        GuardianProfileService,
    )

    monkeypatch.setattr(
        safety,
        "load_global_policy",
        lambda: ContentPolicy(
            level="strict",
            forbidden_topics=("astronomía",),
            trigger_words=("guerra",),
        ),
    )
    service = GuardianProfileService()
    prompt = service.build_system_prompt(regular_user.id, db=test_db_session)
    assert "astronomía" in prompt
    assert "guerra" in prompt
    assert "strict" in prompt.lower() or "G-rated" in prompt


def test_system_prompt_merges_teacher_terms_into_global(
    test_db_session, regular_user, monkeypatch
):
    """Teacher per-student terms and admin global terms both reach the prompt."""
    import src.aac_app.services.content_safety as safety
    from src.aac_app.services.guardian_profile_service import (
        GuardianProfileService,
    )

    monkeypatch.setattr(
        safety,
        "load_global_policy",
        lambda: ContentPolicy(level="standard", forbidden_topics=("astronomía",)),
    )
    test_db_session.add(
        GuardianProfile(
            user_id=regular_user.id,
            template_name="default",
            safety_constraints={"trigger_words": ["violencia"]},
            is_active=True,
            created_by=regular_user.id,
        )
    )
    test_db_session.commit()
    service = GuardianProfileService()
    prompt = service.build_system_prompt(regular_user.id, db=test_db_session)
    assert "astronomía" in prompt  # admin global
    assert "violencia" in prompt  # teacher per-student


# --- prediction integration ------------------------------------------------


def test_session_start_blocks_forbidden_topic(
    test_db_session, regular_user, monkeypatch
):
    """A session on a topic the student's policy forbids never starts."""
    from src.aac_app.services.learning.service import LearningCompanionService

    test_db_session.add(
        GuardianProfile(
            user_id=regular_user.id,
            template_name="default",
            safety_constraints={"forbidden_topics": ["astronomía"]},
            is_active=True,
            created_by=regular_user.id,
        )
    )
    test_db_session.commit()
    service = LearningCompanionService(Mock(), Mock())

    result = service.start_learning_session(
        user_id=regular_user.id,
        topic="astronomía para niños",
        db=test_db_session,
    )
    assert result["success"] is False
    assert result.get("safety_blocked") is True
    event = (
        test_db_session.query(ContentSafetyEvent)
        .filter(ContentSafetyEvent.user_id == regular_user.id)
        .first()
    )
    assert event is not None and event.surface == "topic" and event.verdict == "blocked"


def test_session_start_honors_custom_topic_lock(
    test_db_session, regular_user
):
    """The teacher/admin feature lock on custom topics blocks session start."""
    from src.aac_app.services.learning.service import LearningCompanionService

    test_db_session.add(
        GuardianProfile(
            user_id=regular_user.id,
            template_name="default",
            safety_constraints={"block_custom_topics": True},
            is_active=True,
            created_by=regular_user.id,
        )
    )
    test_db_session.commit()
    service = LearningCompanionService(Mock(), Mock())

    result = service.start_learning_session(
        user_id=regular_user.id,
        topic="los animales",
        db=test_db_session,
    )
    assert result["success"] is False
    assert result.get("safety_blocked") is True
    event = (
        test_db_session.query(ContentSafetyEvent)
        .filter(ContentSafetyEvent.user_id == regular_user.id)
        .first()
    )
    assert event is not None
    assert "block_custom_topics" in (event.detail or "")


def test_predict_next_drops_blocked_topic(
    test_db_session, regular_user, monkeypatch
):
    from src.aac_app.services.prediction_service import PredictionService

    service = PredictionService()
    monkeypatch.setitem(service._models, "es", {"bigrams": {}})
    analytics = Mock()
    analytics.suggest_next_symbol.return_value = []
    monkeypatch.setattr(service, "analytics_service", analytics)
    fetcher = Mock(side_effect=AssertionError("fetcher must not run for blocked topic"))
    policy = ContentPolicy(level="standard", forbidden_topics=("astronomía",))

    suggestions = service.predict_next(
        user_id=regular_user.id,
        current_symbols=[],
        limit=5,
        language="es",
        offset=0,
        topic="astronomía para niños",
        topic_word_fetcher=fetcher,
        content_policy=policy,
        db=test_db_session,
    )
    # The blocked topic produces no topic tier and no generated words.
    assert not any(s["source"] == "topic" for s in suggestions)
    assert not any(s.get("is_text_only") for s in suggestions)
    fetcher.assert_not_called()
    event = (
        test_db_session.query(ContentSafetyEvent)
        .filter(ContentSafetyEvent.user_id == regular_user.id)
        .first()
    )
    assert event is not None
    assert event.surface == "topic"
    assert event.verdict == "redirected"


def test_predict_next_filters_topic_words_by_policy(
    test_db_session, regular_user, monkeypatch
):
    from src.aac_app.services.prediction_service import PredictionService

    service = PredictionService()
    monkeypatch.setitem(service._models, "es", {"bigrams": {}})
    analytics = Mock()
    analytics.suggest_next_symbol.return_value = []
    monkeypatch.setattr(service, "analytics_service", analytics)
    scheduled: list[str] = []
    monkeypatch.setattr(
        "src.aac_app.services.symbol_svg_autogen.ensure_symbol_generated",
        lambda *a, **k: scheduled.append(a[0] or k.get("context", "")),
    )
    policy = ContentPolicy(level="standard", trigger_words=("violencia",))
    fetched_words = ["estrella", "violencia", "paz", "pistola"]
    from unittest.mock import Mock as _Mock

    fetcher = _Mock(return_value=fetched_words)

    import src.aac_app.services.prediction_service as ps_module

    try:
        suggestions = service.predict_next(
            user_id=regular_user.id,
            current_symbols=[],
            limit=10,
            language="es",
            offset=0,
            topic="planetas",
            topic_word_fetcher=fetcher,
            content_policy=policy,
            db=test_db_session,
        )
    finally:
        ps_module._topics_word_cache.clear()

    labels = [s["label"] for s in suggestions]
    assert "estrella" in labels
    assert "violencia" not in labels
    assert "pistola" not in labels
    events = (
        test_db_session.query(ContentSafetyEvent)
        .filter(ContentSafetyEvent.user_id == regular_user.id)
        .all()
    )
    blocked_words = [e for e in events if e.surface == "words"]
    assert len(blocked_words) == 2


def test_schedule_svg_generation_skips_blocked_labels(
    test_db_session, regular_user, monkeypatch
):
    from src.aac_app.services.prediction_service import _PredictionContext

    policy = ContentPolicy(level="standard", trigger_words=("pistola",))
    service = _PredictionContext(
        user_id=regular_user.id,
        current_symbols=[],
        language="es",
        offset=0,
        base_limit=10,
        limit=10,
        board_id=None,
        db=test_db_session,
        analytics_service=Mock(),
        load_model=lambda lang: {"bigrams": {}},
        content_policy=policy,
    )
    spawned: list = []

    class _FakeThread:
        def __init__(self, *a, **k):
            self.args = a
            self.kwargs = k
            spawned.append(self)

    monkeypatch.setattr(
        "src.aac_app.services.symbol_svg_autogen.ensure_symbol_generated",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(service, "_is_svg_generation_enabled", lambda: True)
    with patch("threading.Thread", _FakeThread):
        service._schedule_svg_generation("pistola de juguete")
    assert spawned == []
    event = (
        test_db_session.query(ContentSafetyEvent)
        .filter(ContentSafetyEvent.user_id == regular_user.id)
        .first()
    )
    assert event is not None and event.surface == "pictogram"


# --- autogen server gate ----------------------------------------------------


def test_autogen_background_blocks_label_via_global_policy(
    test_db_session, monkeypatch
):
    import src.aac_app.services.content_safety as safety
    from src.aac_app.services import symbol_svg_autogen as autogen

    monkeypatch.setattr(
        safety, "load_global_policy", lambda: ContentPolicy(level="standard", trigger_words=("pistola",))
    )
    calls: list[str] = []

    class _RecordingProvider:
        def generate_sync(self, prompt, **kwargs) -> str:
            calls.append(prompt)
            return '{"background":"#fff","shapes":[{"kind":"circle","cx":0,"cy":0,"r":10,"fill":"#FFD166"}]}'

    autogen.set_llm_provider_factory(lambda: _RecordingProvider())
    key = autogen._PendingKey("pistolas", "es")
    with (
        patch.object(autogen, "_has_catalog_symbol", return_value=False),
        patch.object(autogen, "_count_generated_today", return_value=0),
    ):
        autogen._generate_in_background(key, "pistolas", "es")

    assert calls == []  # blocked before any LLM spend
    with autogen._lock:
        assert key not in autogen._in_flight
    event = (
        test_db_session.query(ContentSafetyEvent)
        .filter(ContentSafetyEvent.surface == "pictogram")
        .first()
    )
    assert event is not None


# --- board label admission gate --------------------------------------------


def test_get_or_create_symbol_rejects_blocked_new_labels(
    test_db_session, monkeypatch
):
    import src.aac_app.services.content_safety as safety
    from src.api.routers.board_ai import get_or_create_symbol

    monkeypatch.setattr(
        safety, "load_global_policy", lambda: ContentPolicy(level="standard", trigger_words=("cuchillo",))
    )
    with pytest.raises(HTTPException) as excinfo:
        get_or_create_symbol(test_db_session, "un cuchillo", "cuchillo", user=None)
    assert excinfo.value.status_code == 400

    # Curated labels pass through untouched.
    monkeypatch.setattr(
        safety, "load_global_policy", lambda: ContentPolicy(level="standard")
    )
    symbol, created = get_or_create_symbol(
        test_db_session, "cookie", "cookie", user=None
    )
    assert created and symbol.label == "cookie"


# --- learning chat gates ---------------------------------------------------


def test_learning_response_redirects_blocked_input(
    test_db_session, regular_user, mock_llm_provider, mock_speech_provider
):
    from src.aac_app.services.learning.service import LearningCompanionService

    service = LearningCompanionService(mock_llm_provider, mock_speech_provider)
    session = LearningSession(
        user_id=regular_user.id,
        topic_name="frutas",
        purpose="",
        status="active",
        conversation_history=[],
        comprehension_score=0.0,
    )
    test_db_session.add(session)
    test_db_session.commit()
    mock_llm_provider.generate = AsyncMock()

    result = asyncio.run(
        service.process_response(
            session_id=session.id,
            student_response="quiero hablar de sexo",
            db=test_db_session,
        )
    )
    assert result["success"] is True
    # Friendly deflection in the user's locale; never the raw refusal.
    assert "otra cosa" in result["feedback_message"]
    mock_llm_provider.generate.assert_not_called()
    event = (
        test_db_session.query(ContentSafetyEvent)
        .filter(ContentSafetyEvent.user_id == regular_user.id)
        .first()
    )
    assert event is not None and event.direction == "input" and event.verdict == "redirected"


def test_learning_response_replaces_blocked_output(
    test_db_session, regular_user, mock_llm_provider, mock_speech_provider
):
    from src.aac_app.services.learning.service import LearningCompanionService

    async def generate(**kwargs):
        prompt = kwargs.get("prompt", "")
        if "inappropriate for a child" in prompt:
            # Constrained retry produces a safe rewrite.
            return '{"response": "Vamos a hablar de algo divertido"}'
        return '{"response": "Esto es una mierda, claro que sí"}'

    mock_llm_provider.generate = AsyncMock(side_effect=generate)
    service = LearningCompanionService(mock_llm_provider, mock_speech_provider)
    session = LearningSession(
        user_id=regular_user.id,
        topic_name="frutas",
        purpose="",
        status="active",
        conversation_history=[],
        comprehension_score=0.0,
    )
    # Profanity is only filtered at the strict level — the student needs a
    # strict guardian profile (the production path teachers configure).
    test_db_session.add(
        GuardianProfile(
            user_id=regular_user.id,
            template_name="default",
            safety_constraints={"content_filter_level": "strict"},
            is_active=True,
            created_by=regular_user.id,
        )
    )
    test_db_session.add(session)
    test_db_session.commit()

    result = asyncio.run(
        service.process_response(
            session_id=session.id,
            student_response="me siento muy bien hoy",
            db=test_db_session,
        )
    )
    assert result["success"] is True
    assert "mierda" not in result["feedback_message"]
    # The constrained retry rewrite is kept (not the raw deflection).
    assert "divertido" in result["feedback_message"]
    event = (
        test_db_session.query(ContentSafetyEvent)
        .filter(ContentSafetyEvent.user_id == regular_user.id)
        .first()
    )
    assert event is not None and event.direction == "output"


# --- admin API --------------------------------------------------------------


def test_admin_global_policy_api(test_db_session):
    admin = _make_user(test_db_session, "safety_admin1", "admin")
    teacher = _make_user(test_db_session, "safety_teacher1", "teacher")
    student = _make_user(test_db_session, "safety_student2", "student")

    # Non-admins are forbidden.
    for user in (student, teacher):
        resp = client.get("/api/settings/content-safety", headers=_headers(user))
        assert resp.status_code == 403

    payload = {
        "level": "strict",
        "forbidden_topics": ["astronomía"],
        "trigger_words": ["guerra"],
        "feature_locks": {"block_ai_chat": False, "block_board_ai": True},
        "sentinel_moderation": True,
        "max_response_length": 40,
        "locked_fields": ["block_ai_chat"],
    }
    put = client.put(
        "/api/settings/content-safety", headers=_headers(admin), json=payload
    )
    assert put.status_code == 200, put.text
    body = put.json()
    assert body["level"] == "strict"
    assert body["feature_locks"]["block_board_ai"] is True
    assert body["locked_fields"] == ["block_ai_chat"]

    got = client.get("/api/settings/content-safety", headers=_headers(admin)).json()
    assert got["trigger_words"] == ["guerra"]
    # cleanup
    client.put(
        "/api/settings/content-safety",
        headers=_headers(admin),
        json={
            "level": "standard",
            "forbidden_topics": [],
            "trigger_words": [],
            "feature_locks": {},
            "sentinel_moderation": False,
            "locked_fields": [],
        },
    )


def test_teacher_cannot_override_locked_field(test_db_session):
    admin = _make_user(test_db_session, "safety_admin2", "admin")
    teacher = _make_user(test_db_session, "safety_teacher2", "teacher")
    student = _make_user(test_db_session, "safety_student3", "student")
    test_db_session.add(StudentTeacher(teacher_id=teacher.id, student_id=student.id))
    test_db_session.commit()

    client.put(
        "/api/settings/content-safety",
        headers=_headers(admin),
        json={
            "level": "standard",
            "forbidden_topics": [],
            "trigger_words": [],
            "feature_locks": {},
            "sentinel_moderation": False,
            "locked_fields": ["block_ai_chat"],
        },
    )
    try:
        resp = client.post(
            f"/api/guardian-profiles/students/{student.id}",
            headers=_headers(teacher),
            json={
                "template_name": "default",
                "safety_constraints": {"block_ai_chat": True, "block_board_ai": True},
            },
        )
        assert resp.status_code == 403
        assert "block_ai_chat" in resp.json()["detail"]
    finally:
        client.put(
            "/api/settings/content-safety",
            headers=_headers(admin),
            json={
                "level": "standard",
                "forbidden_topics": [],
                "trigger_words": [],
                "feature_locks": {},
                "sentinel_moderation": False,
                "locked_fields": [],
            },
        )


def test_admin_events_and_clear(test_db_session):
    admin = _make_user(test_db_session, "safety_admin3", "admin")
    event = ContentSafetyEvent(
        user_id=None,
        surface="pictogram",
        direction="output",
        verdict="blocked",
        matched=["weapons*"],
        detail="autogen label: pistola",
    )
    test_db_session.add(event)
    test_db_session.commit()

    listed = client.get(
        "/api/settings/content-safety/events", headers=_headers(admin)
    ).json()
    assert any(e["surface"] == "pictogram" for e in listed)

    cleared = client.delete(
        "/api/settings/content-safety/events", headers=_headers(admin)
    )
    assert cleared.status_code == 204
    assert test_db_session.query(ContentSafetyEvent).count() == 0


def test_board_ai_autogen_filters_blocked_labels(
    test_db_session, admin_user, admin_token, setup_test_db
):
    """AI auto-generated board labels blocked by the policy are never placed
    on the board: the create-board auto-generation loop drops them."""
    import src.aac_app.services.content_safety as safety
    from src.aac_app.models import BoardSymbol, CommunicationBoard

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        safety, "load_global_policy", lambda: ContentPolicy(level="standard")
    )
    from unittest.mock import AsyncMock
    from unittest.mock import patch as _patch

    items = [
        {"label": "casa", "symbol_key": "casa"},
        {"label": "pistola", "symbol_key": "pistola"},
    ]
    fake_provider = Mock()
    try:
        with (
            _patch(
                "src.api.routers.board_ai._resolve_provider_for_board",
                return_value=fake_provider,
            ),
            _patch(
                "src.api.routers.board_ai.BoardGenerationService.generate_board_items",
                new=AsyncMock(return_value=items),
            ),
        ):
            response = client.post(
                "/api/boards/",
                params={"user_id": admin_user.id},
                headers={"Authorization": f"Bearer {admin_token}"},
                json={
                    "name": "Gated AI Board",
                    "ai_enabled": True,
                    "ai_provider": "groq",
                    "ai_model": "@primary",
                    "grid_rows": 2,
                    "grid_cols": 2,
                },
            )
        assert response.status_code == 200, response.text
        board = (
            test_db_session.query(CommunicationBoard)
            .filter(CommunicationBoard.name == "Gated AI Board")
            .first()
        )
        assert board is not None
        placed = (
            test_db_session.query(BoardSymbol)
            .filter(BoardSymbol.board_id == board.id)
            .all()
        )
        labels = [bs.symbol.label for bs in placed]
        assert "casa" in labels
        assert "pistola" not in labels
    finally:
        monkeypatch.undo()


def test_report_message_endpoint_logs_event(test_db_session):
    from src.aac_app.models import LearningSession

    student = _make_user(test_db_session, "safety_student6", "student")
    session = LearningSession(
        user_id=student.id,
        topic_name="frutas",
        purpose="",
        status="active",
        conversation_history=[],
        comprehension_score=0.0,
    )
    test_db_session.add(session)
    test_db_session.commit()

    resp = client.post(
        f"/api/learning/{session.id}/report",
        headers=_headers(student),
    )
    assert resp.status_code == 200
    event = (
        test_db_session.query(ContentSafetyEvent)
        .filter(ContentSafetyEvent.user_id == student.id)
        .first()
    )
    assert event is not None
    assert event.surface == "chat" and event.verdict == "reported"

    # Another student cannot report someone else's session.
    other = _make_user(test_db_session, "safety_student7", "student")
    denied = client.post(
        f"/api/learning/{session.id}/report", headers=_headers(other)
    )
    assert denied.status_code == 403


def test_schedule_svg_generation_respects_autogen_lock(
    test_db_session, regular_user, monkeypatch
):
    from src.aac_app.services.prediction_service import _PredictionContext

    policy = ContentPolicy(feature_locks={"block_autogen_pictograms": True})
    service = _PredictionContext(
        user_id=regular_user.id,
        current_symbols=[],
        language="es",
        offset=0,
        base_limit=10,
        limit=10,
        board_id=None,
        db=test_db_session,
        analytics_service=Mock(),
        load_model=lambda lang: {"bigrams": {}},
        content_policy=policy,
    )
    spawned: list = []

    class _FakeThread:
        def __init__(self, *a, **k):
            self.args = a
            self.kwargs = k
            spawned.append(self)

    monkeypatch.setattr(service, "_is_svg_generation_enabled", lambda: True)
    monkeypatch.setattr(
        "src.aac_app.services.symbol_svg_autogen.ensure_symbol_generated",
        lambda *a, **k: None,
    )
    with patch("threading.Thread", _FakeThread):
        service._schedule_svg_generation("estrella")
    assert spawned == []  # the feature lock blocks spawning
    event = (
        test_db_session.query(ContentSafetyEvent)
        .filter(ContentSafetyEvent.user_id == regular_user.id)
        .first()
    )
    assert event is not None
    assert event.surface == "pictogram"
    assert "block_autogen_pictograms" in (event.detail or "")


def test_purge_ai_symbols_endpoint(test_db_session):
    admin = _make_user(test_db_session, "safety_admin4", "admin")
    autogen = Symbol(
        label="nebulosa",
        description="Auto-generated pictogram for the missing symbol 'nebulosa'.",
        category="general",
        image_path="/uploads/symbols/nonexistent.png",
        language="es",
        is_builtin=False,
    )
    curated = Symbol(label="casa", category="home", language="es", is_builtin=True)
    test_db_session.add_all([autogen, curated])
    test_db_session.commit()

    resp = client.delete(
        "/api/settings/content-safety/ai-symbols", headers=_headers(admin)
    )
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 1
    assert test_db_session.query(Symbol).filter(Symbol.id == curated.id).count() == 1
    assert (
        test_db_session.query(Symbol)
        .filter(Symbol.label == "nebulosa")
        .count()
        == 0
    )


def test_teacher_lists_student_safety_events(test_db_session):
    teacher = _make_user(test_db_session, "safety_teacher5", "teacher")
    student = _make_user(test_db_session, "safety_student5", "student")
    test_db_session.add(StudentTeacher(teacher_id=teacher.id, student_id=student.id))
    test_db_session.add(
        ContentSafetyEvent(
            user_id=student.id,
            surface="chat",
            direction="input",
            verdict="redirected",
            matched=["sexo"],
        )
    )
    test_db_session.commit()

    resp = client.get(
        f"/api/guardian-profiles/students/{student.id}/safety-events",
        headers=_headers(teacher),
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    # A student cannot read their own safety log.
    denied = client.get(
        f"/api/guardian-profiles/students/{student.id}/safety-events",
        headers=_headers(student),
    )
    assert denied.status_code == 403
