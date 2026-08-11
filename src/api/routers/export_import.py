import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from src.aac_app.models import (
    Achievement,
    BoardAssignment,
    BoardSymbol,
    CommunicationBoard,
    LearningSession,
    User,
    UserAchievement,
)
from src.api.deps import get_current_active_user, get_db, get_text
from src.api.routers.board_helpers import serialize_export_board

router = APIRouter()


def compute_checksum(payload: dict[str, Any]) -> str:
    """Compute a canonical SHA-256 checksum for export data integrity."""
    from hashlib import sha256

    raw = json.dumps(
        payload,
        separators=(",", ":"),
        sort_keys=True,
        ensure_ascii=False,
    )
    return sha256(raw.encode("utf-8")).hexdigest()


def _compute_legacy_checksum(payload: dict[str, Any]) -> str:
    """Compute the pre-canonical checksum for backward-compatible imports."""
    from hashlib import sha256

    raw = json.dumps(payload, separators=(",", ":"))
    return sha256(raw.encode("utf-8")).hexdigest()


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
                is_visible=bool(symbol_data.get("is_visible")),
                custom_text=symbol_data.get("custom_text"),
            )
        )
    return board


def _import_boards(
    db: Session, user: User, boards_data: list[dict[str, Any]]
) -> dict[int, CommunicationBoard]:
    """Import owned boards and return source-ID to new-board mappings."""
    imported: dict[int, CommunicationBoard] = {}
    for board_data in boards_data:
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
            board = (
                db.query(CommunicationBoard)
                .filter(
                    CommunicationBoard.id == source_id,
                    CommunicationBoard.user_id == user.id,
                    CommunicationBoard.name == board_data.get("name"),
                )
                .first()
            )
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
    db: Session, user: User, achievements_data: list[dict[str, Any]]
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

        if not existing_ua:
            ua = UserAchievement(user_id=user.id, achievement_id=ach.id, earned_at=None)
            db.add(ua)


def _import_learning_history(
    db: Session, user: User, history_data: list[dict[str, Any]]
):
    """Helper to import learning history."""
    for h in history_data:
        try:
            ls = LearningSession(
                user_id=user.id,
                topic_name=h.get("topic_name") or h.get("topic") or "Unknown",
                purpose=h.get("purpose"),
                status=h.get("status") or "completed",
                comprehension_score=float(h.get("comprehension_score") or 0.0),
                questions_asked=int(h.get("questions_asked") or 0),
                questions_answered=int(h.get("questions_answered") or 0),
                correct_answers=int(h.get("correct_answers") or 0),
                started_at=(
                    datetime.fromisoformat(h.get("started_at"))
                    if h.get("started_at")
                    else None
                ),
                ended_at=(
                    datetime.fromisoformat(h.get("ended_at"))
                    if h.get("ended_at")
                    else None
                ),
            )
            db.add(ls)
        except (AttributeError, TypeError, ValueError, OverflowError) as exc:
            # Do not silently discard user data. Raising aborts the request and
            # lets get_db roll back every staged board, achievement, and history
            # row from this import.
            raise HTTPException(
                status_code=400,
                detail="Invalid learning history record in import",
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

    # Compute checksum
    checksum = compute_checksum(base)

    # Add checksum and schema version to meta
    export_data = {
        **base,
        "meta": {
            **base["meta"],
            "checksum_sha256": checksum,
            "schema_version": "1",
        },
    }

    return export_data


@router.post("/api/data/import")
def import_data(
    data: dict[str, Any],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    meta = data.get("meta") or {}
    expected = meta.get("checksum_sha256")

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
    legacy_actual = _compute_legacy_checksum(base)
    if not expected or expected not in {actual, legacy_actual}:
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

    # Import data using helpers
    imported_boards = _import_boards(db, user, base["boards"])
    _import_assigned_boards(
        db,
        user,
        base["assignedBoards"],
        imported_boards,
    )
    _import_achievements(db, user, base["achievements"])
    _import_learning_history(db, user, base["learningHistory"])
    # Keep the entire import atomic: commit once after every section has been
    # validated and staged. This must happen before the response is sent (the
    # dependency teardown otherwise commits after the client sees the 200).
    db.commit()

    return {"ok": True}
