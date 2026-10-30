import json
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.aac_app.models.database import (
    Achievement,
    BoardAssignment,
    BoardSymbol,
    CommunicationBoard,
    LearningSession,
    User,
    UserAchievement,
)
from src.api.dependencies import get_current_active_user, get_db, get_text

router = APIRouter()


def compute_checksum(payload: Dict[str, Any]) -> str:
    """Compute SHA-256 checksum for export data integrity verification."""
    from hashlib import sha256

    raw = json.dumps(payload, separators=(",", ":"))
    return sha256(raw.encode("utf-8")).hexdigest()


def serialize_board(board: CommunicationBoard) -> Dict[str, Any]:
    """Serialize a board with its symbols for export."""
    symbols_data = []
    for bs in board.symbols:
        symbol_data = {
            "id": bs.id,
            "symbol_id": bs.symbol_id,
            "position_x": bs.position_x,
            "position_y": bs.position_y,
            "size": bs.size,
            "is_visible": bs.is_visible,
            "custom_text": bs.custom_text,
            "symbol": (
                {
                    "id": bs.symbol.id,
                    "label": bs.symbol.label,
                    "description": bs.symbol.description,
                    "category": bs.symbol.category,
                    "image_path": bs.symbol.image_path,
                    "keywords": bs.symbol.keywords,
                    "language": bs.symbol.language,
                }
                if bs.symbol
                else None
            ),
        }
        symbols_data.append(symbol_data)

    return {
        "id": board.id,
        "name": board.name,
        "description": board.description,
        "category": board.category,
        "is_public": board.is_public,
        "is_template": board.is_template,
        "grid_rows": board.grid_rows,
        "grid_cols": board.grid_cols,
        "symbols": symbols_data,
        "created_at": board.created_at.isoformat() if board.created_at else None,
        "updated_at": board.updated_at.isoformat() if board.updated_at else None,
    }


def _import_boards(db: Session, user: User, boards_data: List[Dict[str, Any]]):
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
    db: Session, user: User, achievements_data: List[Dict[str, Any]]
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
    db: Session, user: User, history_data: List[Dict[str, Any]]
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
    boards = (
        db.query(CommunicationBoard).filter(CommunicationBoard.user_id == user.id).all()
    )
    boards_data = [serialize_board(b) for b in boards]

    # Fetch assigned boards (if student)
    assigned_boards_data = []
    if user.user_type == "student":
        assignments = (
            db.query(BoardAssignment)
            .filter(BoardAssignment.student_id == user.id)
            .all()
        )
        for assignment in assignments:
            board = (
                db.query(CommunicationBoard)
                .filter(CommunicationBoard.id == assignment.board_id)
                .first()
            )
            if board:
                assigned_boards_data.append(serialize_board(board))

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
            "exported_at": datetime.now(timezone.utc).isoformat(),
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
    data: Dict[str, Any],
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
