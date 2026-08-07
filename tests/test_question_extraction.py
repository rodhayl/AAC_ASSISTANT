"""Unit tests for extract_json_object (LLM question-parse tolerance)."""

from src.aac_app.services.learning.questions import extract_json_object


def test_direct_json():
    raw = '{"question": "Q", "choices": ["A", "B", "C"], "correct": 0}'
    assert extract_json_object(raw) == {
        "question": "Q",
        "choices": ["A", "B", "C"],
        "correct": 0,
    }


def test_markdown_code_fence_json():
    raw = '```json\n{"question": "Q", "choices": ["A", "B", "C"], "correct": 1}\n```'
    parsed = extract_json_object(raw)
    assert parsed["question"] == "Q"
    assert parsed["correct"] == 1


def test_markdown_code_fence_without_language_tag():
    raw = '```\n{"question": "Q", "choices": ["A", "B", "C"], "correct": 2}\n```'
    assert extract_json_object(raw)["correct"] == 2


def test_prose_surrounding_json():
    raw = (
        'Claro! Aquí tienes:\n{"question": "Q", "choices": ["A", "B", "C"], "correct": 0}\n'
        "Espero que te sirva."
    )
    parsed = extract_json_object(raw)
    assert parsed["question"] == "Q"
    assert parsed["choices"] == ["A", "B", "C"]


def test_greeting_only_returns_none():
    assert extract_json_object("¡Hola! Es un gusto saludarte.") is None


def test_empty_and_none():
    assert extract_json_object("") is None
    assert extract_json_object(None) is None


def test_incidental_prose_braces_before_json_are_skipped():
    raw = 'Mira {esto} y ahora: {"question": "Q", "choices": ["A", "B", "C"], "correct": 2}'
    parsed = extract_json_object(raw)
    assert parsed["question"] == "Q"
    assert parsed["correct"] == 2


def test_brace_inside_string_not_mistaken_for_object_boundary():
    raw = '{"question": "Que {dice} la vaca?", "choices": ["Moo", "Meow"], "correct": 0}'
    parsed = extract_json_object(raw)
    assert parsed["question"] == "Que {dice} la vaca?"
    assert len(parsed["choices"]) == 2
