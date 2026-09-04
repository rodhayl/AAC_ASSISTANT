"""Measured query-count regressions for hot API endpoints.

The listener is test-only: production code never enables SQL echo or query
counting. Budgets include authentication and are intentionally asserted against
roster/board sizes large enough to expose per-row ORM work.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from src.aac_app.models import (
    BoardAssignment,
    BoardSymbol,
    CommunicationBoard,
    LearningSession,
    Symbol,
    SymbolUsageLog,
    User,
)
from src.api.main import app
from tests.auth_helpers import create_test_headers

client = TestClient(app)
pytestmark = pytest.mark.usefixtures("setup_test_db")


@contextmanager
def count_queries(engine):
    """Count SQL statements while a single request is executed."""
    count = 0

    def before_cursor_execute(
        _connection, _cursor, _statement, _parameters, _context, _executemany
    ):
        nonlocal count
        count += 1

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    try:
        yield lambda: count
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)


def _board_headers(user: User) -> dict[str, str]:
    return create_test_headers(user.id, user.username, user.user_type)


def test_board_list_query_budget_is_independent_of_board_count(
    test_db_session, test_db_engine, admin_user
):
    """GET /boards/ stays bounded when serializing many boards and symbols."""
    symbols = [
        Symbol(label=f"list_symbol_{index}", category="general", language="en")
        for index in range(3)
    ]
    test_db_session.add_all(symbols)
    test_db_session.flush()
    boards = [
        CommunicationBoard(
            user_id=admin_user.id,
            name=f"List board {index}",
            grid_rows=2,
            grid_cols=2,
        )
        for index in range(25)
    ]
    test_db_session.add_all(boards)
    test_db_session.flush()
    for board in boards:
        test_db_session.add_all(
            [
                BoardSymbol(
                    board_id=board.id,
                    symbol_id=symbols[0].id,
                    position_x=0,
                    position_y=0,
                ),
                BoardSymbol(
                    board_id=board.id,
                    symbol_id=symbols[1].id,
                    position_x=1,
                    position_y=0,
                ),
            ]
        )
    test_db_session.commit()

    with count_queries(test_db_engine) as query_count:
        response = client.get("/api/boards/?limit=100", headers=_board_headers(admin_user))

    assert response.status_code == 200, response.text
    assert len(response.json()) == 25
    assert query_count() <= 4, f"board list query budget exceeded: {query_count()}"


def test_board_detail_query_budget_is_independent_of_symbol_count(
    test_db_session, test_db_engine, admin_user
):
    """GET /boards/{id} uses eager loading rather than one query per symbol."""
    symbols = [
        Symbol(label=f"detail_symbol_{index}", category="general", language="en")
        for index in range(30)
    ]
    test_db_session.add_all(symbols)
    test_db_session.flush()
    board = CommunicationBoard(
        user_id=admin_user.id,
        name="Detail board",
        grid_rows=6,
        grid_cols=5,
    )
    test_db_session.add(board)
    test_db_session.flush()
    test_db_session.add_all(
        [
            BoardSymbol(
                board_id=board.id,
                symbol_id=symbol.id,
                position_x=index % 5,
                position_y=index // 5,
            )
            for index, symbol in enumerate(symbols)
        ]
    )
    test_db_session.commit()

    with count_queries(test_db_engine) as query_count:
        response = client.get(
            f"/api/boards/{board.id}?skip_translation=true",
            headers=_board_headers(admin_user),
        )

    assert response.status_code == 200, response.text
    assert len(response.json()["symbols"]) == 30
    assert query_count() <= 6, f"board detail query budget exceeded: {query_count()}"


def test_student_summary_query_budget_is_bulk_for_large_roster(
    test_db_session, test_db_engine, admin_user
):
    """Student summaries use one query each for students, assignments, boards."""
    students = [
        User(
            username=f"query_summary_student_{index}",
            display_name=f"Summary student {index}",
            user_type="student",
            password_hash="not-used-in-this-test",
            is_active=True,
        )
        for index in range(25)
    ]
    test_db_session.add_all(students)
    test_db_session.flush()
    boards = [
        CommunicationBoard(
            user_id=admin_user.id,
            name=f"Summary board {index}",
            grid_rows=2,
            grid_cols=2,
        )
        for index in range(25)
    ]
    test_db_session.add_all(boards)
    test_db_session.flush()
    test_db_session.add_all(
        [
            BoardAssignment(
                board_id=board.id,
                student_id=student.id,
                assigned_by=admin_user.id,
            )
            for student, board in zip(students, boards, strict=True)
        ]
    )
    test_db_session.commit()

    with count_queries(test_db_engine) as query_count:
        response = client.get(
            "/api/auth/users/student-summaries?limit=100",
            headers=_board_headers(admin_user),
        )

    assert response.status_code == 200, response.text
    assert len(response.json()) == 25
    assert query_count() <= 6, f"student summary query budget exceeded: {query_count()}"


def test_assigned_board_query_budget_is_eager_for_many_symbols(
    test_db_session, test_db_engine, admin_user
):
    """GET /boards/assigned does not issue a query per board or placement."""
    student = User(
        username="query_assigned_student",
        display_name="Assigned student",
        user_type="student",
        password_hash="not-used-in-this-test",
        is_active=True,
    )
    test_db_session.add(student)
    test_db_session.flush()
    symbols = [
        Symbol(label=f"assigned_symbol_{index}", category="general", language="en")
        for index in range(12)
    ]
    test_db_session.add_all(symbols)
    test_db_session.flush()
    boards = [
        CommunicationBoard(
            user_id=admin_user.id,
            name=f"Assigned board {index}",
            grid_rows=3,
            grid_cols=4,
        )
        for index in range(8)
    ]
    test_db_session.add_all(boards)
    test_db_session.flush()
    for board in boards:
        test_db_session.add(BoardAssignment(board_id=board.id, student_id=student.id))
        test_db_session.add_all(
            [
                BoardSymbol(
                    board_id=board.id,
                    symbol_id=symbol.id,
                    position_x=index % 4,
                    position_y=index // 4,
                )
                for index, symbol in enumerate(symbols[:4])
            ]
        )
    test_db_session.commit()

    with count_queries(test_db_engine) as query_count:
        response = client.get(
            "/api/boards/assigned",
            params={"student_id": student.id},
            headers=_board_headers(admin_user),
        )

    assert response.status_code == 200, response.text
    assert len(response.json()) == 8
    assert query_count() <= 4, f"assigned boards query budget exceeded: {query_count()}"


def test_next_symbol_query_budget_does_not_scale_with_transition_candidates(
    test_db_session, test_db_engine, regular_user
):
    """Canonical next-symbol suggestions batch symbol resolution.

    The repository has no ``/api/analytics/suggestions`` route; Smartbar uses
    ``POST /api/analytics/next-symbol``. Ten possible next labels make the
    former per-label lookup exceed this budget, while the batched lookup stays
    bounded.
    """
    clear_caches()
    session_rows = []
    symbols = [
        Symbol(label="I", category="pronoun", language="en"),
        Symbol(label="want", category="verb", language="en"),
    ] + [
        Symbol(label=f"transition_{index}", category="noun", language="en")
        for index in range(10)
    ]
    test_db_session.add_all(symbols)
    test_db_session.flush()
    for index, next_symbol in enumerate(symbols[2:]):
        learning_session = LearningSession(
            user_id=regular_user.id,
            topic_name=f"query topic {index}",
        )
        test_db_session.add(learning_session)
        test_db_session.flush()
        timestamp = datetime.now() + timedelta(seconds=index)
        session_rows.extend(
            [
                SymbolUsageLog(
                    user_id=regular_user.id,
                    session_id=learning_session.id,
                    symbol_id=symbols[0].id,
                    symbol_label="I",
                    symbol_category="pronoun",
                    position_in_utterance=0,
                    utterance_length=3,
                    timestamp=timestamp,
                ),
                SymbolUsageLog(
                    user_id=regular_user.id,
                    session_id=learning_session.id,
                    symbol_id=symbols[1].id,
                    symbol_label="want",
                    symbol_category="verb",
                    position_in_utterance=1,
                    utterance_length=3,
                    timestamp=timestamp + timedelta(milliseconds=1),
                ),
                SymbolUsageLog(
                    user_id=regular_user.id,
                    session_id=learning_session.id,
                    symbol_id=next_symbol.id,
                    symbol_label=next_symbol.label,
                    symbol_category="noun",
                    position_in_utterance=2,
                    utterance_length=3,
                    timestamp=timestamp + timedelta(milliseconds=2),
                ),
            ]
        )
    test_db_session.add_all(session_rows)
    test_db_session.commit()

    with count_queries(test_db_engine) as query_count:
        response = client.post(
            "/api/analytics/next-symbol",
            json={"current_symbols": "I,want", "limit": 10},
            headers=_board_headers(regular_user),
        )

    assert response.status_code == 200, response.text
    assert {item["label"] for item in response.json()} >= {
        f"transition_{index}" for index in range(10)
    }
    assert query_count() <= 14, f"next-symbol query budget exceeded: {query_count()}"


def clear_caches() -> None:
    """Clear process-local caches that would make this measurement order-dependent."""
    from src.aac_app.services.prediction_service import clear_prediction_cache
    from src.aac_app.services.symbol_analytics import clear_history_transition_cache
    from src.api.deps import clear_settings_cache

    clear_prediction_cache()
    clear_history_transition_cache()
    clear_settings_cache()
