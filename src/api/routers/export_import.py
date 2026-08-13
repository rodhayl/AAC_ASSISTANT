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

# Compatibility name retained for scripts that imported the old module helper.
serialize_board = serialize_export_board

router = APIRouter()


def compute_checksum(payload: dict[str, Any]) -> str:
    """Compute SHA-256 checksum for export data integrity verification."""
    from hashlib import sha256

    raw = json.dumps(payload, separators=(",", ":"))
    return sha256(raw.encode("utf-8")).hexdigest()


def _import_boards(db: Session, user: User, boards_data: list[dict[str, Any]]):
    """Helper to import boards."""
    for b in boards_data:
        board = CommunicationBoard(
            user_id=user.id,
            name=b.get("name"),
            description=b.get("description"),
            category=b.get("category") or "general",
            is_public=bool(b.get("is_public")),
            is_template=bool(b.get("is_template")),
            grid_rows=b.get("grid_rows") or 4,
            grid_cols=b.get("grid_cols") or 5,
        )
        db.add(board)
        db.flush()
        for s in b.get("symbols") or []:
            bs = BoardSymbol(
                board_id=board.id,
                symbol_id=(s.get("symbol", {}) or {}).get("id") or s.get("symbol_id"),
                position_x=s.get("position_x") or 0,
                position_y=s.get("position_y") or 0,
                size=s.get("size") or 1,
                is_visible=bool(s.get("is_visible")),
                custom_text=s.get("custom_text"),
            )
            db.add(bs)


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
        except Exception:
            continue


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
    if not expected or expected != actual:
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
    _import_boards(db, user, base["boards"])
    _import_achievements(db, user, base["achievements"])
    db.commit()

    _import_learning_history(db, user, base["learningHistory"])
    db.commit()

    return {"ok": True}
