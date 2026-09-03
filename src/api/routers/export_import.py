import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import null
from sqlalchemy.orm import Session, selectinload

from src import config
from src.aac_app.models import (
    Achievement,
    BoardAssignment,
    BoardSymbol,
    CommunicationBoard,
    LearningSession,
    Symbol,
    User,
    UserAchievement,
)
from src.api.deps import get_current_active_user, get_db, get_text
from src.api.routers.board_helpers import serialize_export_board

router = APIRouter()


def _normalize_checksum_number(value: Any) -> Any:
    """Return a JSON value with whole-number floats collapsed to integers.

    JavaScript and Python disagree about ``0.0`` vs ``0``: a browser's
    ``JSON.parse``/``JSON.stringify`` round-trip collapses ``0.0`` to ``0``,
    while Python preserves the float. Normalizing whole-number floats here keeps
    the signed checksum stable across a browser download/re-upload, so an export
    can always be re-imported through the UI.
    """
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {key: _normalize_checksum_number(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_checksum_number(item) for item in value]
    return value


def _canonical_export_bytes(payload: dict[str, Any]) -> bytes:
    """Serialize export data deterministically before signing or verifying."""
    return json.dumps(
        _normalize_checksum_number(payload),
        separators=(",", ":"),
        sort_keys=True,
        ensure_ascii=False,
    ).encode("utf-8")


def _export_integrity_key() -> bytes:
    """Return the server-only key used to authenticate export payloads."""
    secret = str(config.get("JWT_SECRET_KEY", "")).strip()
    if len(secret) < 32:
        raise RuntimeError("JWT_SECRET_KEY must be at least 32 characters for export integrity")
    return secret.encode("utf-8")


def compute_checksum(payload: dict[str, Any]) -> str:
    """Compute a keyed canonical HMAC for export authenticity and integrity."""
    return hmac.new(
        _export_integrity_key(),
        _canonical_export_bytes(payload),
        hashlib.sha256,
    ).hexdigest()


_MAX_IMPORT_BOARDS = 1_000
_MAX_IMPORT_ASSIGNED_BOARDS = 1_000
_MAX_IMPORT_SYMBOLS = 10_000
_MAX_IMPORT_ACHIEVEMENTS = 1_000
_MAX_IMPORT_HISTORY = 1_000
_MAX_IMPORT_BODY_BYTES = 10 * 1024 * 1024


async def _read_import_payload(
    request: Request,
    user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    """Decode an import body without materializing an unbounded request."""
    invalid_detail = get_text(user=user, key="errors.export.invalidPayload")
    too_large_detail = get_text(user=user, key="errors.export.payloadTooLarge")
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > _MAX_IMPORT_BODY_BYTES:
                raise HTTPException(status_code=413, detail=too_large_detail)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=invalid_detail) from exc

    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > _MAX_IMPORT_BODY_BYTES:
            raise HTTPException(status_code=413, detail=too_large_detail)
        body.extend(chunk)

    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail=invalid_detail) from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail=invalid_detail)
    return payload


def _validate_import_payload(
    data: dict[str, Any],
    user: User,
) -> dict[str, Any]:
    """Validate import shapes and bound work before staging database rows."""
    invalid_detail = get_text(user=user, key="errors.export.invalidPayload")
    too_large_detail = get_text(user=user, key="errors.export.payloadTooLarge")
    meta = data.get("meta")
    if not isinstance(meta, dict):
        raise HTTPException(status_code=400, detail=invalid_detail)
    if not isinstance(meta.get("username"), str) or not meta["username"].strip():
        raise HTTPException(status_code=400, detail=invalid_detail)
    if meta.get("exported_at") is not None and not isinstance(
        meta.get("exported_at"), str
    ):
        raise HTTPException(status_code=400, detail=invalid_detail)
    if meta.get("schema_version") is not None and not isinstance(
        meta.get("schema_version"), str
    ):
        raise HTTPException(status_code=400, detail=invalid_detail)

    def collection(key: str, limit: int) -> list[dict[str, Any]]:
        raw = data.get(key)
        value = [] if raw is None else raw
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            raise HTTPException(status_code=400, detail=invalid_detail)
        if len(value) > limit:
            raise HTTPException(status_code=413, detail=too_large_detail)
        return value

    boards = collection("boards", _MAX_IMPORT_BOARDS)
    assigned_boards = collection("assignedBoards", _MAX_IMPORT_ASSIGNED_BOARDS)
    achievements = collection("achievements", _MAX_IMPORT_ACHIEVEMENTS)
    history = collection("learningHistory", _MAX_IMPORT_HISTORY)

    def optional_text(value: Any, maximum: int) -> bool:
        return value is None or (isinstance(value, str) and len(value) <= maximum)

    symbol_count = 0
    for board in [*boards, *assigned_boards]:
        if (
            not isinstance(board.get("name"), str)
            or not board["name"].strip()
            or len(board["name"]) > 100
        ):
            raise HTTPException(status_code=400, detail=invalid_detail)
        for key in ("is_public", "is_template"):
            value = board.get(key)
            if value is not None and not isinstance(value, bool):
                raise HTTPException(status_code=400, detail=invalid_detail)
        if not optional_text(board.get("description"), 10000) or not optional_text(
            board.get("category"), 50
        ):
            raise HTTPException(status_code=400, detail=invalid_detail)
        for key in ("grid_rows", "grid_cols"):
            value = board.get(key)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 100
            ):
                raise HTTPException(status_code=400, detail=invalid_detail)

        raw_symbols = board.get("symbols")
        symbols = [] if raw_symbols is None else raw_symbols
        if not isinstance(symbols, list) or any(not isinstance(item, dict) for item in symbols):
            raise HTTPException(status_code=400, detail=invalid_detail)
        symbol_count += len(symbols)
        for symbol in symbols:
            nested = symbol.get("symbol")
            if nested is not None and not isinstance(nested, dict):
                raise HTTPException(status_code=400, detail=invalid_detail)
            if nested is not None and not optional_text(nested.get("audio_path"), 500):
                raise HTTPException(status_code=400, detail=invalid_detail)
            symbol_id = _export_symbol_id(symbol)
            if symbol_id is None or type(symbol_id) is not int or symbol_id < 1:
                # A mismatched top-level/nested ID must not be silently
                # discarded and then restored using whichever value happens to
                # be present in the payload.
                raise HTTPException(status_code=400, detail=invalid_detail)
            for key in ("position_x", "position_y"):
                value = symbol.get(key)
                if value is not None and (
                    isinstance(value, bool) or not isinstance(value, int) or value < 0
                ):
                    raise HTTPException(status_code=400, detail=invalid_detail)
            size = symbol.get("size")
            if size is not None and (
                isinstance(size, bool) or not isinstance(size, int) or not 1 <= size <= 100
            ):
                raise HTTPException(status_code=400, detail=invalid_detail)
            if not optional_text(symbol.get("custom_text"), 100):
                raise HTTPException(status_code=400, detail=invalid_detail)
            if not optional_text(symbol.get("color"), 20):
                raise HTTPException(status_code=400, detail=invalid_detail)
            if symbol.get("is_visible") is not None and not isinstance(
                symbol.get("is_visible"), bool
            ):
                raise HTTPException(status_code=400, detail=invalid_detail)
            linked_board_id = symbol.get("linked_board_id")
            if linked_board_id is not None and (
                isinstance(linked_board_id, bool) or not isinstance(linked_board_id, int)
            ):
                raise HTTPException(status_code=400, detail=invalid_detail)

    if symbol_count > _MAX_IMPORT_SYMBOLS:
        raise HTTPException(status_code=413, detail=too_large_detail)

    for achievement in achievements:
        if (
            not isinstance(achievement.get("name"), str)
            or not achievement["name"].strip()
            or len(achievement["name"]) > 100
        ):
            raise HTTPException(status_code=400, detail=invalid_detail)
        if not optional_text(achievement.get("description"), 10000) or not optional_text(
            achievement.get("category"), 50
        ):
            raise HTTPException(status_code=400, detail=invalid_detail)
        for key, maximum in (("icon", 50),):
            if not optional_text(achievement.get(key), maximum):
                raise HTTPException(status_code=400, detail=invalid_detail)
        points = achievement.get("points")
        if points is not None and (
            isinstance(points, bool) or not isinstance(points, int) or points < 0
        ):
            raise HTTPException(status_code=400, detail=invalid_detail)

    for record in history:
        for key, maximum in (("topic_name", 200), ("topic", 200), ("purpose", 10000), ("status", 50)):
            if not optional_text(record.get(key), maximum):
                raise HTTPException(status_code=400, detail=invalid_detail)
        for key in (
            "comprehension_score",
            "questions_asked",
            "questions_answered",
            "correct_answers",
        ):
            value = record.get(key)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, (int, float))
            ):
                raise HTTPException(status_code=400, detail=invalid_detail)
            if value is not None and value < 0:
                raise HTTPException(status_code=400, detail=invalid_detail)
            if key == "comprehension_score" and value is not None and not 0 <= value <= 1:
                raise HTTPException(status_code=400, detail=invalid_detail)
            if key != "comprehension_score" and value is not None and type(value) is not int:
                raise HTTPException(status_code=400, detail=invalid_detail)
        for key in ("started_at", "ended_at"):
            value = record.get(key)
            if value is not None and not isinstance(value, str):
                raise HTTPException(status_code=400, detail=invalid_detail)

    return meta


def _validate_import_symbol_references(
    db: Session,
    payload: dict[str, Any],
    invalid_detail: str,
) -> None:
    """Reject signed exports that reference symbols absent from this database."""
    symbol_ids = {
        _export_symbol_id(symbol)
        for board in [*(payload.get("boards") or []), *(payload.get("assignedBoards") or [])]
        for symbol in (board.get("symbols") or [])
    }
    if None in symbol_ids:
        raise HTTPException(status_code=400, detail=invalid_detail)
    if not symbol_ids:
        return
    existing_ids = {
        symbol_id
        for (symbol_id,) in db.query(Symbol.id).filter(Symbol.id.in_(symbol_ids)).all()
    }
    if existing_ids != symbol_ids:
        raise HTTPException(status_code=400, detail=invalid_detail)


def _export_symbol_id(symbol_data: dict[str, Any]) -> int | None:
    """Read one consistent symbol ID from either supported export shape."""
    nested = symbol_data.get("symbol") or {}
    top_level_id = symbol_data.get("symbol_id")
    nested_id = nested.get("id")
    if top_level_id is not None and nested_id is not None and top_level_id != nested_id:
        return None
    symbol_id = top_level_id if top_level_id is not None else nested_id
    return symbol_id if type(symbol_id) is int else None


def _board_content_matches(
    board: CommunicationBoard,
    board_data: dict[str, Any],
) -> bool:
    """Return whether an owned board has the same exported content."""
    expected_symbols = sorted(
        [
            (
                _export_symbol_id(symbol),
                symbol.get("position_x") or 0,
                symbol.get("position_y") or 0,
                symbol.get("size") or 1,
                (
                    True
                    if symbol.get("is_visible") is None
                    else bool(symbol["is_visible"])
                ),
                symbol.get("custom_text"),
                symbol.get("color"),
            )
            for symbol in board_data.get("symbols") or []
        ],
        key=repr,
    )
    actual_symbols = sorted(
        [
            (
                symbol.symbol_id,
                symbol.position_x or 0,
                symbol.position_y or 0,
                symbol.size or 1,
                bool(symbol.is_visible),
                symbol.custom_text,
                symbol.color,
            )
            for symbol in board.symbols or []
        ],
        key=repr,
    )
    return (
        board.description == board_data.get("description")
        and board.category == (board_data.get("category") or "general")
        and bool(board.is_public) == bool(board_data.get("is_public"))
        and bool(board.is_template) == bool(board_data.get("is_template"))
        and (board.grid_rows or 4) == (board_data.get("grid_rows") or 4)
        and (board.grid_cols or 5) == (board_data.get("grid_cols") or 5)
        and actual_symbols == expected_symbols
    )


def _find_matching_owned_board(
    db: Session,
    user: User,
    board_data: dict[str, Any],
) -> CommunicationBoard | None:
    """Find an exact same-content board to make repeated imports idempotent.

    This deliberately merges only exact-content retries. Distinct boards with
    the same name but different settings or placements remain separate.
    """
    name = board_data.get("name")
    if not isinstance(name, str):
        return None
    candidates = (
        db.query(CommunicationBoard)
        .options(selectinload(CommunicationBoard.symbols))
        .filter(
            CommunicationBoard.user_id == user.id,
            CommunicationBoard.name == name,
        )
        .all()
    )
    return next(
        (board for board in candidates if _board_content_matches(board, board_data)),
        None,
    )


def _create_imported_board(
    db: Session,
    user: User,
    board_data: dict[str, Any],
) -> CommunicationBoard:
    """Create one imported board and its symbol placements."""
    board = CommunicationBoard(
        user_id=user.id,
        name=board_data.get("name"),
        description=board_data.get("description"),
        category=board_data.get("category") or "general",
        is_public=bool(board_data.get("is_public")),
        is_template=bool(board_data.get("is_template")),
        grid_rows=board_data.get("grid_rows") or 4,
        grid_cols=board_data.get("grid_cols") or 5,
    )
    db.add(board)
    db.flush()
    for symbol_data in board_data.get("symbols") or []:
        db.add(
            BoardSymbol(
                board_id=board.id,
                symbol_id=(symbol_data.get("symbol", {}) or {}).get("id")
                or symbol_data.get("symbol_id"),
                position_x=symbol_data.get("position_x") or 0,
                position_y=symbol_data.get("position_y") or 0,
                size=symbol_data.get("size") or 1,
                # Match the ORM default when importing older exports that
                # omitted this optional placement field.
                is_visible=(
                    True
                    if symbol_data.get("is_visible") is None
                    else bool(symbol_data["is_visible"])
                ),
                custom_text=symbol_data.get("custom_text"),
                color=symbol_data.get("color"),
                # linked_board_id is intentionally NOT restored: export IDs are
                # not remapped to the imported boards, so a copied reference
                # would point at an unrelated local board.
                linked_board_id=None,
            )
        )
    return board


def _import_boards(
    db: Session, user: User, boards_data: list[dict[str, Any]]
) -> dict[int, CommunicationBoard]:
    """Import owned boards and return source-ID to new-board mappings."""
    imported: dict[int, CommunicationBoard] = {}
    for board_data in boards_data:
        board = _find_matching_owned_board(db, user, board_data)
        if board is None:
            board = _create_imported_board(db, user, board_data)
        source_id = board_data.get("id")
        if isinstance(source_id, int):
            imported[source_id] = board
    return imported


def _import_assigned_boards(
    db: Session,
    user: User,
    assigned_boards_data: list[dict[str, Any]],
    imported_boards: dict[int, CommunicationBoard],
) -> None:
    """Restore assigned boards without trusting unrelated ID collisions."""
    for board_data in assigned_boards_data:
        source_id = board_data.get("id")
        board = imported_boards.get(source_id) if isinstance(source_id, int) else None
        if board is None and isinstance(source_id, int):
            # Never grant access to an existing board owned by another user
            # based only on an uploaded ID/name pair. IDs in exports are not
            # authenticators; unrelated boards must be cloned instead.
            candidate = (
                db.query(CommunicationBoard)
                .filter(
                    CommunicationBoard.id == source_id,
                    CommunicationBoard.user_id == user.id,
                    CommunicationBoard.name == board_data.get("name"),
                )
                .first()
            )
            if candidate is not None and _board_content_matches(candidate, board_data):
                board = candidate
        if board is None:
            board = _find_matching_owned_board(db, user, board_data)
        if board is None:
            board = _create_imported_board(db, user, board_data)

        exists = (
            db.query(BoardAssignment)
            .filter(
                BoardAssignment.board_id == board.id,
                BoardAssignment.student_id == user.id,
            )
            .first()
        )
        if exists is None:
            db.add(
                BoardAssignment(
                    board_id=board.id,
                    student_id=user.id,
                    assigned_by=user.id,
                )
            )


def _import_achievements(
    db: Session,
    user: User,
    achievements_data: list[dict[str, Any]],
    invalid_timestamp_detail: str,
):
    """Helper to import achievements."""
    for a in achievements_data:
        name = a.get("name")
        ach = db.query(Achievement).filter(Achievement.name == name).first()
        if not ach:
            ach = Achievement(
                name=name,
                description=a.get("description") or "",
                category=a.get("category") or "general",
                criteria_type="imported",
                criteria_value=0,
                points=int(a.get("points") or 0),
                icon=a.get("icon") or "🏆",
            )
            db.add(ach)
            db.flush()

        existing_ua = (
            db.query(UserAchievement)
            .filter(
                UserAchievement.user_id == user.id,
                UserAchievement.achievement_id == ach.id,
            )
            .first()
        )

        earned_at_value = a.get("earned_at")
        if earned_at_value is not None and not isinstance(earned_at_value, str):
            raise HTTPException(
                status_code=400,
                detail=invalid_timestamp_detail,
            )
        try:
            earned_at = (
                datetime.fromisoformat(earned_at_value)
                if earned_at_value is not None
                else None
            )
        except (TypeError, ValueError, OverflowError) as exc:
            raise HTTPException(
                status_code=400,
                detail=invalid_timestamp_detail,
            ) from exc

        if not existing_ua:
            db.add(
                UserAchievement(
                    user_id=user.id,
                    achievement_id=ach.id,
                    earned_at=earned_at if earned_at is not None else null(),
                )
            )
        elif existing_ua.earned_at is None and earned_at is not None:
            # Preserve a timestamp supplied by an authenticated export when a
            # legacy local row was created without one; never overwrite a
            # timestamp that is already present.
            existing_ua.earned_at = earned_at


def _import_learning_history(
    db: Session, user: User, history_data: list[dict[str, Any]]
):
    """Import learning history without duplicating an exact prior record.

    Legacy records without a durable source ID use all exported scalar fields
    as their retry identity; an exact duplicate is intentionally merged.
    """
    for h in history_data:
        try:
            topic_name = h.get("topic_name") or h.get("topic") or "Unknown"
            started_at = (
                datetime.fromisoformat(h.get("started_at"))
                if h.get("started_at")
                else None
            )
            ended_at = (
                datetime.fromisoformat(h.get("ended_at"))
                if h.get("ended_at")
                else None
            )
            values = {
                "topic_name": topic_name,
                "purpose": h.get("purpose"),
                "status": h.get("status") or "completed",
                "comprehension_score": float(h.get("comprehension_score") or 0.0),
                "questions_asked": int(h.get("questions_asked") or 0),
                "questions_answered": int(h.get("questions_answered") or 0),
                "correct_answers": int(h.get("correct_answers") or 0),
                "started_at": started_at,
                "ended_at": ended_at,
            }
            # Match every exported scalar, including NULL timestamps. This
            # makes retries of legacy records deterministic without adding a
            # migration solely for an import receipt column.
            existing = (
                db.query(LearningSession)
                .filter(
                    LearningSession.user_id == user.id,
                    LearningSession.topic_name == topic_name,
                    LearningSession.started_at == started_at,
                    LearningSession.ended_at == ended_at,
                    LearningSession.purpose == values["purpose"],
                    LearningSession.status == values["status"],
                    LearningSession.comprehension_score == values["comprehension_score"],
                    LearningSession.questions_asked == values["questions_asked"],
                    LearningSession.questions_answered == values["questions_answered"],
                    LearningSession.correct_answers == values["correct_answers"],
                )
                .first()
            )
            if existing is not None:
                continue
            db.add(LearningSession(user_id=user.id, **values))
        except (AttributeError, TypeError, ValueError, OverflowError) as exc:
            # Do not silently discard user data. Raising aborts the request and
            # lets get_db roll back every staged board, achievement, and history
            # row from this import.
            raise HTTPException(
                status_code=400,
                detail=get_text(
                    user=user, key="errors.export.invalidLearningRecord"
                ),
            ) from exc


@router.get("/api/data/export")
def export_data(
    username: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Server-side export endpoint that mirrors client-side export format.
    Generates a JSON export with checksum for integrity verification.

    Args:
        username: Username to export data for
        db: Database session

    Returns:
        JSON export with boards, achievements, learning history, and SHA-256 checksum
    """
    # Permission check
    if current_user.username != username and current_user.user_type != "admin":
        raise HTTPException(
            status_code=403,
            detail=get_text(user=current_user, key="errors.export.unauthorizedExport"),
        )

    # Find user
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(
            status_code=404,
            detail=get_text(user=current_user, key="errors.userNotFound"),
        )

    # Fetch user's boards
    board_options = selectinload(CommunicationBoard.symbols).selectinload(BoardSymbol.symbol)
    boards = (
        db.query(CommunicationBoard)
        .options(board_options)
        .filter(CommunicationBoard.user_id == user.id)
        .all()
    )
    boards_data = [serialize_export_board(board) for board in boards]

    # Fetch assigned boards in one query instead of one board query per
    # assignment. This matters for students with large assigned-board lists.
    assigned_boards_data = []
    if user.user_type == "student":
        assigned_boards = (
            db.query(CommunicationBoard)
            .join(BoardAssignment, BoardAssignment.board_id == CommunicationBoard.id)
            .options(board_options)
            .filter(BoardAssignment.student_id == user.id)
            .distinct()
            .order_by(CommunicationBoard.id)
            .all()
        )
        assigned_boards_data = [serialize_export_board(board) for board in assigned_boards]

    # Fetch achievements
    user_achievements = (
        db.query(UserAchievement).filter(UserAchievement.user_id == user.id).all()
    )
    achievements_data = []
    total_points = 0
    for ua in user_achievements:
        ach = ua.achievement
        if ach:
            achievements_data.append(
                {
                    "id": ach.id,
                    "name": ach.name,
                    "description": ach.description,
                    "icon": ach.icon,
                    "category": ach.category,
                    "points": ach.points,
                    "earned_at": ua.earned_at.isoformat() if ua.earned_at else None,
                }
            )
            total_points += ach.points or 0

    # Fetch learning history
    learning_sessions = (
        db.query(LearningSession)
        .filter(LearningSession.user_id == user.id)
        .order_by(LearningSession.started_at.desc())
        .limit(100)
        .all()
    )

    learning_history_data = []
    for session in learning_sessions:
        learning_history_data.append(
            {
                "id": session.id,
                "topic_name": session.topic_name,
                "topic": session.topic_name,  # Alias for compatibility
                "purpose": session.purpose,
                "status": session.status,
                "comprehension_score": session.comprehension_score,
                "questions_asked": session.questions_asked,
                "questions_answered": session.questions_answered,
                "correct_answers": session.correct_answers,
                "started_at": (
                    session.started_at.isoformat() if session.started_at else None
                ),
                "ended_at": session.ended_at.isoformat() if session.ended_at else None,
            }
        )

    # Build base payload for checksum
    base = {
        "meta": {
            "exported_at": datetime.now(UTC).isoformat(),
            "username": user.username,
        },
        "boards": boards_data,
        "assignedBoards": assigned_boards_data,
        "achievements": achievements_data,
        "totalPoints": total_points,
        "learningHistory": learning_history_data,
    }

    # Sign the canonical payload so clients cannot forge achievements, points,
    # or other imported records by recomputing an unkeyed public hash.
    checksum = compute_checksum(base)

    # Add checksum and schema version to meta
    export_data = {
        **base,
        "meta": {
            **base["meta"],
            "checksum_sha256": checksum,
            "schema_version": "2",
        },
    }

    return export_data


@router.post(
    "/api/data/import",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "additionalProperties": True,
                    }
                }
            },
        }
    },
)
def import_data(
    data: dict[str, Any] = Depends(_read_import_payload),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    meta = _validate_import_payload(data, current_user)
    expected = meta.get("checksum_sha256")
    schema_version = meta.get("schema_version")
    if schema_version == "1":
        raise HTTPException(
            status_code=400,
            detail=get_text(
                user=current_user,
                key="errors.export.legacyChecksumUnsupported",
            ),
        )
    if schema_version != "2":
        raise HTTPException(
            status_code=400,
            detail=get_text(
                user=current_user,
                key="errors.export.unsupportedSchemaVersion",
            ),
        )

    # Checksum validation
    base = {
        "meta": {
            "exported_at": meta.get("exported_at"),
            "username": meta.get("username"),
        },
        "boards": data.get("boards") or [],
        "assignedBoards": data.get("assignedBoards") or [],
        "achievements": data.get("achievements") or [],
        "totalPoints": data.get("totalPoints") or 0,
        "learningHistory": data.get("learningHistory") or [],
    }
    actual = compute_checksum(base)
    if not isinstance(expected, str) or not hmac.compare_digest(expected, actual):
        raise HTTPException(
            status_code=400,
            detail=get_text(user=current_user, key="errors.export.checksumMismatch"),
        )

    username = meta.get("username")

    # Permission check
    if current_user.username != username and current_user.user_type != "admin":
        raise HTTPException(
            status_code=403,
            detail=get_text(user=current_user, key="errors.export.unauthorizedImport"),
        )

    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(
            status_code=404,
            detail=get_text(user=current_user, key="errors.userNotFound"),
        )

    # Validate foreign-key references before staging any import rows.
    _validate_import_symbol_references(
        db,
        base,
        get_text(user=current_user, key="errors.export.invalidPayload"),
    )

    # Import data using helpers.
    imported_boards = _import_boards(db, user, base["boards"])
    _import_assigned_boards(
        db,
        user,
        base["assignedBoards"],
        imported_boards,
    )
    _import_achievements(
        db,
        user,
        base["achievements"],
        get_text(
            user=current_user,
            key="errors.export.invalidAchievementTimestamp",
        ),
    )
    _import_learning_history(db, user, base["learningHistory"])
    # Keep the entire import atomic: commit once after every section has been
    # validated and staged. This must happen before the response is sent (the
    # dependency teardown otherwise commits after the client sees the 200).
    db.commit()

    return {"ok": True}
