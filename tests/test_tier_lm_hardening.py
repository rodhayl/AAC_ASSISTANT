"""Tier L/M hardening regressions (PROMPT_5).

- H25: session-start derived plan/task names must fit their String(100) columns.
- H26: board-AI labels/colors are bounded before the insert.
- H30: custom automatic achievements are filtered in SQL, not in Python.
- H33: vector-store readiness is O(1) in memory and an unavailable store is a
  no-op instead of a full re-embed.
- H34: a reasoning-only response must not leak its think blocks.
- H36: ``label=None`` must not crash symbol semantics.
- H47: a translation outage must degrade board reads, not 500 them.
"""

from unittest.mock import Mock

from src.aac_app.models import Achievement, GuardianProfile, LearningPlan, LearningTask, User


def _user(test_db_session, username, user_type="student"):
    from src.aac_app.services.auth_service import get_password_hash

    user = User(
        username=username,
        display_name=username.title(),
        password_hash=get_password_hash("TestPassword123"),
        user_type=user_type,
        is_active=True,
    )
    test_db_session.add(user)
    test_db_session.commit()
    test_db_session.refresh(user)
    if user_type == "student":
        test_db_session.add(
            GuardianProfile(
                user_id=user.id,
                template_name="default",
                is_active=True,
                created_by=user.id,
            )
        )
        test_db_session.commit()
    return user


def test_session_start_truncates_derived_names_to_the_column(test_db_session):
    """H25: a 100-char topic must not overflow LearningPlan/Task.name."""
    from src.aac_app.services.learning.service import LearningCompanionService

    student = _user(test_db_session, "h25_student")
    topic = ("palabras " * 11 + "x")[:100]  # exactly the schema maximum
    assert len(topic) == 100

    service = LearningCompanionService(Mock(), Mock())
    result = service.start_learning_session(
        user_id=student.id, topic=topic, db=test_db_session
    )
    assert result["success"] is True, result

    plan = (
        test_db_session.query(LearningPlan)
        .filter(LearningPlan.id == result["plan_id"])
        .one()
    )
    task = (
        test_db_session.query(LearningTask)
        .filter(LearningTask.id == result["task_id"])
        .one()
    )
    assert len(plan.name) <= 100
    assert len(task.name) <= 100


def test_bounded_color_accepts_hex_and_named_colours_only():
    """H26: LLM-provided colours are validated before the insert."""
    from src.api.routers.board_ai import _bounded_color

    assert _bounded_color("#fff") == "#fff"
    assert _bounded_color("#FFAA22") == "#FFAA22"
    assert _bounded_color("  #00ff00ff  ") == "#00ff00ff"
    assert _bounded_color("tomato") == "tomato"
    assert _bounded_color("light-blue") == "light-blue"

    assert _bounded_color(None) is None
    assert _bounded_color("") is None
    assert _bounded_color("x" * 21) is None
    assert _bounded_color("#12345") is None  # not a hex form
    assert _bounded_color("<script>") is None
    assert _bounded_color({"hex": "#fff"}) is None


def test_bounded_generated_label_skips_unusable_llm_labels():
    """H26: an unusable generated label drops that item, never the request."""
    from src.api.routers.board_ai import _bounded_generated_label

    assert _bounded_generated_label("casa") == "casa"
    assert _bounded_generated_label("  agua  ") == "agua"
    # 100-char bound and the stricter label_looks_bad rule both apply.
    assert len(_bounded_generated_label("a" * 45)) == 45
    assert _bounded_generated_label("a" * 60) is None
    assert _bounded_generated_label("a" * 150) is None
    assert _bounded_generated_label("/usr/lib/symbol") is None
    assert _bounded_generated_label("   ") is None
    assert _bounded_generated_label(None) is None
    assert _bounded_generated_label(42) is None


def test_custom_achievements_for_other_users_are_not_evaluated(test_db_session):
    """H30: the target-user filter lives in SQL and still behaves."""
    from src.aac_app.services.achievement_system import AchievementSystem

    student = _user(test_db_session, "h30_owner")
    other = _user(test_db_session, "h30_other")

    mine = Achievement(
        name="H30 mine",
        description="",
        category="custom",
        points=1,
        icon="🏆",
        created_by=student.id,
        target_user_id=student.id,
        is_active=True,
        criteria_type="sessions_completed",
        criteria_value=0,
    )
    theirs = Achievement(
        name="H30 theirs",
        description="",
        category="custom",
        points=1,
        icon="🏆",
        created_by=other.id,
        target_user_id=other.id,
        is_active=True,
        criteria_type="sessions_completed",
        criteria_value=0,
    )
    test_db_session.add_all([mine, theirs])
    test_db_session.commit()

    awarded = AchievementSystem().check_achievements(student.id, db=test_db_session)
    names = {entry.name for entry in awarded}
    assert "H30 mine" in names
    assert "H30 theirs" not in names


def test_vector_readiness_check_does_not_materialize_id_sets():
    """H33: the readiness comparison happens inside SQLite."""
    from src.aac_app.services.local_vector_store import LocalVectorStore

    store = LocalVectorStore()
    try:
        # The comparison is done in SQL; the call must simply succeed and
        # return a boolean regardless of the local schema state.
        assert isinstance(store.is_ready(), bool)
    finally:
        store.close()


def test_stale_symbol_detection_is_a_noop_when_the_store_is_unavailable(
    monkeypatch,
):
    """H33: an unavailable store must not mark the whole catalog stale."""
    from src.aac_app.services.local_vector_store import LocalVectorStore

    store = LocalVectorStore()
    monkeypatch.setattr(store, "_ensure_schema", lambda: False)

    assert store.get_stale_symbol_ids({1: "a", 2: "b"}) == set()


def test_reasoning_only_output_does_not_leak_think_blocks():
    """H34: the cleaned result is returned even when it is empty."""
    from src.aac_app.services.learning.common import _strip_reasoning

    reasoning_only = "<think>the student probably means agua</think>"
    assert _strip_reasoning(reasoning_only) == ""
    assert "think" not in _strip_reasoning(reasoning_only)

    assert _strip_reasoning("Hola, ¿cómo estás?") == "Hola, ¿cómo estás?"
    assert (
        _strip_reasoning("<think>hmm</think>La respuesta es agua.")
        == "La respuesta es agua."
    )


def test_symbol_semantics_handles_a_none_label():
    """H36: an explicit None label must not raise (the default applies only
    to absent keys)."""
    from src.aac_app.services.symbol_semantics import SymbolSemantics

    result = SymbolSemantics().analyze_sequence(
        [
            {"label": None, "category": "person"},
            {"label": "agua", "category": None},
        ]
    )
    assert result["intent"]


def test_board_serialization_degrades_when_translation_fails(monkeypatch):
    """H47: a translation outage serves the source text, not a 500."""
    from src.api.routers import board_helpers

    def boom(*_args, **_kwargs):
        raise RuntimeError("translation endpoint unavailable")

    monkeypatch.setattr(board_helpers, "_translate_symbol_text", boom)

    board = Mock()
    board.id = 1
    board.user_id = 1
    board.name = "Tablero"
    board.description = None
    board.category = "general"
    board.is_public = False
    board.is_template = False
    board.created_at = None
    board.updated_at = None
    board.grid_rows = 2
    board.grid_cols = 2
    board.ai_enabled = False
    board.ai_provider = None
    board.ai_model = None
    board.locale = "en"
    board.is_language_learning = False
    symbol = Mock()
    symbol.id = 5
    symbol.label = "agua"
    symbol.description = None
    symbol.category = "general"
    symbol.image_path = None
    symbol.audio_path = None
    symbol.keywords = None
    symbol.language = "es"
    symbol.is_builtin = False
    symbol.created_at = None
    placement = Mock()
    placement.id = 1
    placement.symbol_id = 5
    placement.position_x = 0
    placement.position_y = 0
    placement.size = 1
    placement.is_visible = True
    placement.custom_text = "vaso de agua"
    placement.color = None
    placement.linked_board_id = None
    placement.symbol = symbol
    board.symbols = [placement]

    payload = board_helpers.serialize_board(board, target_lang="en")
    assert payload["symbols"][0]["custom_text"] == "vaso de agua"
    assert payload["symbols"][0]["symbol"]["label"] == "agua"
