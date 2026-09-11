"""Regression coverage for the F13/F14 fixes.

F13 — export/import must preserve board navigation:
* ``linked_board_id`` is remapped among authorized imported boards in a
  second pass (including assigned boards), never left dangling to unrelated
  local boards, and included in retry matching.
* cyclic/missing/external references must not break the import or create
  links to boards the importer does not own.

F14 — safety-event retention and clearing must not reset the strict
moderation daily cost meter: today's ``surface="sentinel"`` rows survive
both the automatic 10k pruning and the admin delete-all endpoint.
"""

import pytest

from src.aac_app.models import CommunicationBoard, ContentSafetyEvent, Symbol, User
from src.aac_app.services import content_safety as safety
from src.api.routers.export_import import _import_boards

pytestmark = pytest.mark.usefixtures("setup_test_db")


def _make_user(test_db_session, username: str) -> User:
    from src.aac_app.services.auth_service import get_password_hash

    user = User(
        username=username,
        email=f"{username}@example.com",
        password_hash=get_password_hash("StrongPass123"),
        user_type="student",
        is_active=True,
        display_name=username.title(),
    )
    test_db_session.add(user)
    test_db_session.commit()
    test_db_session.refresh(user)
    return user


def _make_symbol(test_db_session, label: str) -> Symbol:
    symbol = Symbol(label=label, description=label, category="test", keywords=label)
    test_db_session.add(symbol)
    test_db_session.commit()
    test_db_session.refresh(symbol)
    return symbol


def _board_payload(source_id: int, name: str, symbols: list[dict]) -> dict:
    return {
        "id": source_id,
        "name": name,
        "description": "d",
        "category": "general",
        "is_public": False,
        "is_template": False,
        "grid_rows": 2,
        "grid_cols": 2,
        "symbols": symbols,
    }


def _placement_payload(symbol_id: int, linked: int | None = None) -> dict:
    return {
        "symbol_id": symbol_id,
        "position_x": 0,
        "position_y": 0,
        "size": 1,
        "is_visible": True,
        "custom_text": None,
        "color": None,
        "linked_board_id": linked,
    }


class TestLinkedBoardRemap:
    def test_links_remapped_among_imported_boards(
        self, test_db_session, test_password
    ):
        """A/B linked boards keep their navigation after import."""
        user = _make_user(test_db_session, "remap_user")
        symbol = _make_symbol(test_db_session, "remap_symbol")

        boards_data = [
            _board_payload(101, "Alpha", [_placement_payload(symbol.id, linked=102)]),
            _board_payload(102, "Beta", [_placement_payload(symbol.id, linked=101)]),
        ]

        imported = _import_boards(test_db_session, user, boards_data)
        test_db_session.commit()

        alpha = imported[101]
        beta = imported[102]
        test_db_session.refresh(alpha)
        test_db_session.refresh(beta)
        alpha_placement = next(p for b in (alpha,) for p in b.symbols)
        beta_placement = next(p for b in (beta,) for p in b.symbols)

        assert alpha_placement.linked_board_id == beta.id
        assert beta_placement.linked_board_id == alpha.id
        # Cycles resolved correctly; no link points at a pre-existing board id.
        assert alpha_placement.linked_board_id != 102
        assert beta_placement.linked_board_id != 101

    def test_missing_and_external_references_stay_cleared(
        self, test_db_session
    ):
        """Links to boards absent from the import must not be restored."""
        user = _make_user(test_db_session, "ext_user")
        symbol = _make_symbol(test_db_session, "ext_symbol")

        boards_data = [
            _board_payload(201, "Orphan", [_placement_payload(symbol.id, linked=999)]),
        ]

        imported = _import_boards(test_db_session, user, boards_data)
        test_db_session.commit()

        board = imported[201]
        test_db_session.refresh(board)
        placement = board.symbols[0]
        assert placement.linked_board_id is None

    def test_retry_import_matches_including_links(self, test_db_session):
        """Re-importing the same navigation finds the existing boards instead of cloning."""
        user = _make_user(test_db_session, "retry_user")
        symbol = _make_symbol(test_db_session, "retry_symbol")

        boards_data = [
            _board_payload(301, "First", [_placement_payload(symbol.id, linked=302)]),
            _board_payload(302, "Second", [_placement_payload(symbol.id, linked=301)]),
        ]

        first = _import_boards(test_db_session, user, boards_data)
        test_db_session.commit()
        count_before = test_db_session.query(CommunicationBoard).count()

        second = _import_boards(test_db_session, user, boards_data)
        test_db_session.commit()
        count_after = test_db_session.query(CommunicationBoard).count()

        assert count_after == count_before, "retry must merge into existing boards"
        assert second[301].id == first[301].id
        assert second[302].id == first[302].id

    def test_links_do_not_grant_access_to_unowned_boards(self, test_db_session):
        """A forged link to a local board the importer does not own stays cleared."""
        owner = _make_user(test_db_session, "owner_user")
        importer = _make_user(test_db_session, "attacker_user")
        symbol = _make_symbol(test_db_session, "link_symbol")

        # A board owned by someone else that the importer cannot reference.
        foreign = CommunicationBoard(
            name="Foreign", user_id=owner.id, is_public=False, grid_rows=2, grid_cols=2
        )
        test_db_session.add(foreign)
        test_db_session.commit()
        test_db_session.refresh(foreign)

        boards_data = [
            _board_payload(
                401,
                "Hostile",
                [_placement_payload(symbol.id, linked=foreign.id)],
            ),
        ]

        imported = _import_boards(test_db_session, importer, boards_data)
        test_db_session.commit()

        board = imported[401]
        test_db_session.refresh(board)
        assert board.symbols[0].linked_board_id is None


class TestSentinelCostMeterPreservation:
    def test_retention_never_prunes_todays_sentinel_rows(self, test_db_session, monkeypatch):
        """The 10k retention pass must skip today's sentinel rows (cost meter)."""
        today_start = safety._today_start()
        # Today's sentinel rows (the cost meter)...
        for _ in range(3):
            test_db_session.add(
                ContentSafetyEvent(
                    user_id=None,
                    surface="sentinel",
                    direction="output",
                    verdict="passed",
                    matched=[],
                    detail=None,
                )
            )
        # ...plus old prunable rows.
        from datetime import timedelta

        for _ in range(3):
            event = ContentSafetyEvent(
                user_id=None,
                surface="chat",
                direction="input",
                verdict="blocked",
                matched=[],
                detail="old",
            )
            test_db_session.add(event)
        test_db_session.commit()
        # Backdate the "old" rows so they are prunable while sentinel rows stay.
        test_db_session.query(ContentSafetyEvent).filter(
            ContentSafetyEvent.surface == "chat"
        ).update(
            {ContentSafetyEvent.created_at: today_start - timedelta(days=10)},
            synchronize_session=False,
        )
        test_db_session.commit()

        # Exercise the real pruning helper with a tiny cap: 6 rows, cap 2.
        # Only the 3 old chat rows are prunable; today's sentinel rows (the
        # cost meter) are protected even though they alone exceed the cap.
        safety._prune_events(test_db_session, max_events=2)
        test_db_session.commit()

        remaining = test_db_session.query(ContentSafetyEvent).all()
        assert len(remaining) == 3
        assert all(event.surface == "sentinel" for event in remaining)
        # The strict-moderation daily cost meter is intact.
        assert safety._count_sentinel_today(test_db_session) == 3

    def test_count_sentinel_today_only_counts_today(self, test_db_session):
        """The cost meter counts only today's sentinel rows."""
        from datetime import timedelta

        today_start = safety._today_start()
        old = ContentSafetyEvent(
            user_id=None, surface="sentinel", direction="output", verdict="passed"
        )
        today = ContentSafetyEvent(
            user_id=None, surface="sentinel", direction="output", verdict="passed"
        )
        test_db_session.add_all([old, today])
        test_db_session.commit()
        test_db_session.query(ContentSafetyEvent).filter(
            ContentSafetyEvent.id == old.id
        ).update(
            {ContentSafetyEvent.created_at: today_start - timedelta(days=2)},
            synchronize_session=False,
        )
        test_db_session.commit()

        assert safety._count_sentinel_today(db=test_db_session) == 1

    def test_clear_endpoint_preserves_todays_sentinel_rows(self, test_db_session):
        """DELETE /events keeps today's sentinel rows (cost meter intact)."""
        from datetime import timedelta

        from fastapi.testclient import TestClient

        from src.api.main import app
        from tests.auth_helpers import create_test_token

        today_start = safety._today_start()
        old_chat = ContentSafetyEvent(
            user_id=None, surface="chat", direction="input", verdict="blocked"
        )
        old_sentinel = ContentSafetyEvent(
            user_id=None, surface="sentinel", direction="output", verdict="passed"
        )
        today_sentinel = ContentSafetyEvent(
            user_id=None, surface="sentinel", direction="output", verdict="passed"
        )
        test_db_session.add_all([old_chat, old_sentinel, today_sentinel])
        test_db_session.commit()
        test_db_session.query(ContentSafetyEvent).filter(
            ContentSafetyEvent.id.in_([old_chat.id, old_sentinel.id])
        ).update(
            {ContentSafetyEvent.created_at: today_start - timedelta(days=5)},
            synchronize_session=False,
        )
        test_db_session.commit()

        admin = _make_user(test_db_session, "clear_admin")
        admin.user_type = "admin"
        test_db_session.commit()

        client = TestClient(app)
        response = client.delete(
            "/api/settings/content-safety/events",
            headers={
                "Authorization": f"Bearer {create_test_token(admin.id, admin.username, 'admin')}"
            },
        )
        assert response.status_code == 204, response.text

        remaining = test_db_session.query(ContentSafetyEvent).all()
        surfaces = {event.surface for event in remaining}
        assert surfaces == {"sentinel"}
        assert remaining[0].created_at >= today_start
