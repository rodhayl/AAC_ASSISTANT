from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from src.aac_app.models import BoardAssignment, BoardSymbol, CommunicationBoard, User
from src.aac_app.services.runtime_translation import normalize_language_code
from src.aac_app.services.translation_service import get_translation_service
from src.api import schemas
from src.api.deps import (
    get_board_or_404,
    get_current_active_user,
    get_db,
    get_text,
    require_board_owner_or_admin,
)
from src.api.routers.board_helpers import serialize_board

router = APIRouter()


@router.get("")
@router.get("/")
def get_boards(
    skip: int = 0,
    limit: int = 100,
    user_id: int | None = None,
    name: str | None = None,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Get boards with RBAC:
    - Admin: Can view all boards, or filter by user_id
    - User: Can view own boards, public boards, or filter by specific user_id if that user's boards are public
    """
    try:
        query = db.query(CommunicationBoard)

        # Filter by name if provided
        if name:
            query = query.filter(CommunicationBoard.name.ilike(f"%{name}%"))

        # Eager load symbols
        query = query.options(
            selectinload(CommunicationBoard.symbols).joinedload(BoardSymbol.symbol)
        )

        if current_user.user_type == "admin":
            # Admin can see everything
            if user_id:
                query = query.filter(CommunicationBoard.user_id == user_id)
        else:
            # Regular user
            if user_id:
                if user_id == current_user.id:
                    # Own boards
                    query = query.filter(CommunicationBoard.user_id == current_user.id)
                else:
                    # Other user's boards -> MUST be public
                    query = query.filter(
                        CommunicationBoard.user_id == user_id,
                        CommunicationBoard.is_public.is_(True),
                    )
            else:
                # No user_id specified -> My boards OR Public boards
                query = query.filter(
                    or_(
                        CommunicationBoard.user_id == current_user.id,
                        CommunicationBoard.is_public.is_(True),
                    )
                )

        boards = query.offset(skip).limit(limit).all()

        result = [serialize_board(board) for board in boards]

        return result
    except Exception as e:
        logger.error(f"Error fetching boards: {e}")
        logger.exception("Traceback:")
        # Fallback empty list to avoid UI crash; error logged by FastAPI
        return []


@router.get("/{board_id}", response_model=schemas.BoardResponse)
def get_board(
    board_id: int,
    skip_translation: bool = Query(
        False, description="Skip per-symbol translation for faster loads"
    ),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Get specific board details"""
    board = (
        db.query(CommunicationBoard)
        .options(
            selectinload(CommunicationBoard.symbols).selectinload(BoardSymbol.symbol)
        )
        .filter(CommunicationBoard.id == board_id)
        .first()
    )
    if not board:
        raise HTTPException(
            status_code=404,
            detail=get_text(user=current_user, key="errors.boards.boardNotFound"),
        )

    # Permission check
    if (
        current_user.user_type != "admin"
        and board.user_id != current_user.id
        and not board.is_public
    ):
        # Check if assigned?
        assignment = (
            db.query(BoardAssignment)
            .filter(
                BoardAssignment.board_id == board_id,
                BoardAssignment.student_id == current_user.id,
            )
            .first()
        )
        if not assignment:
            raise HTTPException(
                status_code=403,
                detail=get_text(
                    user=current_user, key="errors.boards.unauthorizedViewBoard"
                ),
            )

    target_lang = None
    if not skip_translation:
        # Resolve target language
        ts = get_translation_service()
        target_lang = normalize_language_code(ts.resolve_language(current_user))

        # If target lang is same as board locale (or 'en'), skip translation optimization
        board_locale = normalize_language_code(getattr(board, "locale", "en"))
        if target_lang == board_locale or target_lang == "en" and board_locale is None:
            target_lang = None

    return serialize_board(board, target_lang=target_lang)


@router.put("/{board_id}", response_model=schemas.BoardResponse)
def update_board(
    board_id: int,
    board_update: schemas.BoardUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Update a board"""
    db_board = get_board_or_404(db, board_id, current_user)
    require_board_owner_or_admin(db_board, current_user)

    # Update fields
    update_data = board_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_board, key, value)

    db.commit()
    db.refresh(db_board)
    return serialize_board(db_board)


@router.delete("/{board_id}")
def delete_board(
    board_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Delete a board"""
    db_board = get_board_or_404(db, board_id, current_user)
    require_board_owner_or_admin(db_board, current_user)

    # Delete associated symbols (cascade should handle this but let's be safe if needed,
    # but currently BoardSymbol is the link. Cascade delete on DB level usually handles it if configured)
    # SQLAlchemy relationship cascade="all, delete" might be needed on model.
    # Let's assume manual cleanup of association table if not.
    db.query(BoardSymbol).filter(BoardSymbol.board_id == board_id).delete()

    db.delete(db_board)
    db.commit()
    return {"ok": True}
