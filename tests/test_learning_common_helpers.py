"""Unit tests for shared learning prompt/response helpers (common.py)."""

from src.aac_app.services.learning.common import (
    AACPromptProfile,
    _strip_reasoning,
    difficulty_for_score,
    next_action_for,
)

# ---------------------------------------------------------------------------
# _strip_reasoning
# ---------------------------------------------------------------------------


def test_strip_reasoning_empty_and_none():
    assert _strip_reasoning("") == ""
    assert _strip_reasoning(None) is None


def test_strip_reasoning_removes_thinking_fence():
    raw = "```thinking\nlet me reason about this\n```\nFinal answer: apples"
    assert _strip_reasoning(raw) == "apples"


def test_strip_reasoning_removes_reasoning_fence_case_insensitive():
    raw = "```Reasoning\nstep one\nstep two\n```\nanswer: blue"
    assert _strip_reasoning(raw) == "blue"


def test_strip_reasoning_removes_think_tags():
    raw = "<think>inner chain of thought</think>The sky is blue."
    assert _strip_reasoning(raw) == "The sky is blue."


def test_strip_reasoning_extracts_after_answer_marker():
    raw = "Some prose.\nfinal answer: oranges\nmore prose"
    assert _strip_reasoning(raw) == "oranges\nmore prose"


def test_strip_reasoning_uses_last_marker():
    raw = "response: first\nanswer: second"
    assert _strip_reasoning(raw) == "second"


def test_strip_reasoning_returns_original_when_stripped_empty():
    raw = "<think>only thinking</think>"
    assert _strip_reasoning(raw) == raw


# ---------------------------------------------------------------------------
# AACPromptProfile
# ---------------------------------------------------------------------------


def _semantic(intent: str = "statement") -> dict:
    return {"intent": intent, "confidence": 0.9, "semantic_roles": []}


def _expansion(expanded: str = "I want juice", confidence: float = 0.9) -> dict:
    return {
        "expanded_text": expanded,
        "confidence": confidence,
        "transformations": ["add-subject", "add-article"],
    }


def test_build_prompt_includes_expansion_and_transformations():
    profile = AACPromptProfile()
    prompt = profile.build_prompt(
        student_message="I juice",
        semantic_analysis=_semantic("request"),
        expansion_result=_expansion(),
        topic="snacks",
    )

    assert "I juice" in prompt
    assert "Expanded interpretation: I want juice" in prompt
    assert "Grammar improvements: add-subject, add-article" in prompt
    assert "Detected intent: REQUEST" in prompt
    assert "Topic of discussion: snacks" in prompt
    assert "making a request" in prompt


def test_build_prompt_skips_expansion_when_confidence_low():
    profile = AACPromptProfile()
    prompt = profile.build_prompt(
        student_message="I juice",
        semantic_analysis=_semantic("question"),
        expansion_result=_expansion(confidence=0.4),
        topic="snacks",
    )

    assert "Expanded interpretation" not in prompt
    assert "Detected intent: QUESTION" in prompt
    assert "asking a question" in prompt


def test_build_prompt_skips_expansion_when_unchanged():
    profile = AACPromptProfile()
    prompt = profile.build_prompt(
        student_message="I want juice",
        semantic_analysis=_semantic(),
        expansion_result=_expansion(expanded="I want juice"),
        topic="snacks",
    )

    assert "Expanded interpretation" not in prompt


def test_build_prompt_prepends_recent_context():
    profile = AACPromptProfile()
    prompt = profile.build_prompt(
        student_message="hello",
        semantic_analysis=_semantic("greeting"),
        expansion_result=_expansion(),
        topic="animals",
        recent_context="Student: hi\nTutor: hello!",
    )

    assert "Previous conversation:" in prompt
    assert "Student: hi" in prompt
    assert "greeting you" in prompt


def test_build_prompt_unknown_intent_omits_guidance():
    profile = AACPromptProfile()
    prompt = profile.build_prompt(
        student_message="stuff",
        semantic_analysis=_semantic("unknown_intent"),
        expansion_result=_expansion(),
        topic="things",
    )

    assert "Detected intent: UNKNOWN_INTENT" in prompt
    assert "friendly, encouraging response" in prompt


def test_get_params_returns_tuned_limits():
    profile = AACPromptProfile()
    params = profile.get_params()
    assert params == {"max_tokens": 150, "temperature": 0.6}


# ---------------------------------------------------------------------------
# Comprehension policy (shared by questions.py and responses.py)
# ---------------------------------------------------------------------------


def test_difficulty_for_score_bands():
    assert difficulty_for_score(0.0) == "basic"
    assert difficulty_for_score(0.39) == "basic"
    assert difficulty_for_score(0.4) == "intermediate"
    assert difficulty_for_score(0.69) == "intermediate"
    assert difficulty_for_score(0.7) == "advanced"
    assert difficulty_for_score(1.0) == "advanced"


def test_next_action_for_progress():
    assert (
        next_action_for(comprehension_score=0.9, questions_answered=5)
        == "ready_for_activity"
    )
    assert (
        next_action_for(comprehension_score=0.9, questions_answered=4)
        == "continue_questions"
    )
    assert (
        next_action_for(comprehension_score=0.2, questions_answered=3)
        == "review_needed"
    )
    assert (
        next_action_for(comprehension_score=0.2, questions_answered=2)
        == "continue_questions"
    )
    assert (
        next_action_for(comprehension_score=0.6, questions_answered=10)
        == "continue_questions"
    )
