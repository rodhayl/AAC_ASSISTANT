"""Tier H limits, bounds and commit ordering (PROMPT_5).

- H8: heavy non-LLM endpoints (full export, catalog listing, ARASAAC egress)
  had no limiter while the auth routes did; ARASAAC searches are also cached.
- H10: guardian prompt-adjacent fields must stay bounded (already covered by
  E4 — these tests pin the contract so it cannot regress).
- H11: adding a symbol to a board commits the vocabulary achievement progress
  before responding, like the achievements check route.
"""

import asyncio
import os
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from src.aac_app.models import UserProgress
from src.api import schemas
from tests.auth_helpers import create_test_headers


@contextmanager
def _production_limiter():
    """Run with TESTING=0 so ``conditional_limiter`` is live."""
    with patch.dict(os.environ, {"TESTING": "0"}):
        yield


def test_heavy_endpoints_carry_a_rate_limiter():
    """H8: the full export, the catalog listing and the ARASAAC egress routes."""
    from src.api.routers import arasaac, export_import, symbols

    handlers = (
        (export_import, "export_data"),
        (symbols, "get_symbols"),
        (arasaac, "search_arasaac"),
        (arasaac, "import_arasaac_symbol"),
    )
    unlimited = [
        f"{module.__name__}.{name}"
        for module, name in handlers
        if not getattr(getattr(module, name), "__rate_limited__", False)
    ]
    assert unlimited == [], f"unlimited heavy endpoints: {unlimited}"


@pytest.mark.usefixtures("setup_test_db")
def test_export_burst_is_throttled(client, admin_user):
    """H8: the export budget (10/hour) cuts a burst off with 429."""
    headers = create_test_headers(admin_user.id, admin_user.username, "admin")

    statuses = []
    with _production_limiter():
        for _ in range(11):
            statuses.append(
                client.get(
                    "/api/data/export",
                    params={"username": "no_such_export_user"},
                    headers=headers,
                ).status_code
            )

    assert statuses[:10] == [404] * 10, statuses
    assert statuses[10] == 429, statuses


def test_repeated_arasaac_search_uses_the_short_lived_cache():
    """H8: identical (query, locale) searches do not repeat the upstream call."""
    from src.aac_app.services.arasaac import (
        ArasaacService,
        clear_search_cache,
    )

    calls: list[str] = []

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return [{"_id": 7, "keywords": [{"keyword": "pan"}], "desc": "bread"}]

    class FakeClient:
        async def get(self, url):
            calls.append(url)
            return FakeResponse()

        async def aclose(self):
            pass

    clear_search_cache()
    service = ArasaacService()
    service.client = FakeClient()
    try:
        first = asyncio.run(service.search_symbols("pan", "es"))
        second = asyncio.run(service.search_symbols("pan", "es"))
        third = asyncio.run(service.search_symbols("pan", "en"))
    finally:
        asyncio.run(service.close())
        clear_search_cache()

    assert len(calls) == 2, calls  # es hit upstream once, en once
    assert first == second == third

    # A caller mutating its result must not poison later cache hits.
    first[0]["label"] = "mutated"
    assert asyncio.run(service.search_symbols("pan", "es"))[0]["label"] == "pan"


def test_guardian_prompt_adjacent_fields_are_bounded():
    """H10: every prompt/DB-fed guardian field keeps its cap."""
    with pytest.raises(ValidationError):
        schemas.GuardianProfileFields(private_notes="x" * 10_001)
    with pytest.raises(ValidationError):
        schemas.GuardianProfileFields(custom_instructions="x" * 10_001)
    with pytest.raises(ValidationError):
        schemas.GuardianProfileUpdate(change_reason="x" * 501)
    with pytest.raises(ValidationError):
        schemas.MedicalContextSchema(notes="x" * 10_001)

    # Nested list items and list counts are bounded too.
    with pytest.raises(ValidationError):
        schemas.MedicalContextSchema(diagnoses=["x" * 201])
    with pytest.raises(ValidationError):
        schemas.MedicalContextSchema(diagnoses=["ok"] * 51)
    with pytest.raises(ValidationError):
        schemas.SafetyConstraintsSchema(forbidden_topics=["x" * 201])
    with pytest.raises(ValidationError):
        schemas.CompanionPersonaSchema(personality=["x" * 201])

    # Boundary values pass.
    assert schemas.GuardianProfileFields(private_notes="x" * 10_000)


@pytest.mark.usefixtures("setup_test_db")
def test_add_symbol_to_board_commits_vocabulary_progress_before_responding(
    client, test_db_session, admin_user
):
    """H11: the vocabulary award is durable by the time the response lands.

    Guard, not a discriminator: the request-scoped dependency commits at
    teardown, so this also passes before the fix — it pins the explicit
    commit that removes the race for an immediate client re-read.
    """
    from src.aac_app.models import BoardSymbol, CommunicationBoard, Symbol

    board = CommunicationBoard(user_id=admin_user.id, name="H11 board")
    symbol = Symbol(label="h11 symbol", category="test", language="en")
    test_db_session.add_all([board, symbol])
    test_db_session.commit()
    test_db_session.refresh(board)
    test_db_session.refresh(symbol)

    headers = create_test_headers(admin_user.id, admin_user.username, "admin")
    response = client.post(
        f"/api/boards/{board.id}/symbols",
        json={"symbol_id": symbol.id, "position_x": 0, "position_y": 0},
        headers=headers,
    )
    assert response.status_code in (200, 201), response.text

    test_db_session.expire_all()
    assert (
        test_db_session.query(BoardSymbol)
        .filter(BoardSymbol.board_id == board.id, BoardSymbol.symbol_id == symbol.id)
        .count()
        == 1
    )
    progress = (
        test_db_session.query(UserProgress)
        .filter(
            UserProgress.user_id == admin_user.id,
            UserProgress.metric_type == "vocabulary_size",
        )
        .first()
    )
    assert progress is not None
    assert progress.metric_value >= 1
