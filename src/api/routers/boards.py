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
    require_board_view_access,
    validate_grid_resize,
)
from src.api.routers.board_helpers import SUPPORTED_AI_PROVIDERS, serialize_board

router = APIRouter()


@router.get("")
@router.get("/")
def get_boards(
    skip: int = Query(0, ge=0, le=100_000),
    limit: int = Query(100, ge=1, le=1000),
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
        logger.exception("Error fetching boards: {}", e)
        raise HTTPException(
            status_code=500,
            detail=get_text(user=current_user, key="errors.unknown"),
        ) from e


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

    # Keep board detail access consistent with board-scoped analytics,
    # learning, and collaboration: rostered teachers may view their students'
    # private boards, while students still require an explicit assignment.
    require_board_view_access(board, current_user, db)

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

    # A smaller grid must not strand existing symbols outside the rendered
    # editor. Reject the resize atomically so users do not lose access to
    # placements by changing layout settings.
    update_data = board_update.model_dump(exclude_unset=True)
    if "grid_rows" in update_data or "grid_cols" in update_data:
        validate_grid_resize(
            db_board,
            update_data.get("grid_rows", db_board.grid_rows or 4),
            update_data.get("grid_cols", db_board.grid_cols or 5),
            current_user,
        )

    # Mirror create_board's AI validation so an update cannot persist an
    # unsupported provider (e.g. the global primary set to lmstudio) that
    # _resolve_provider_for_board would silently treat as ollama. The check
    # runs even when AI is being disabled: an invalid value must be rejected,
    # not silently overwritten with None.
    merged_ai_enabled = update_data.get("ai_enabled", db_board.ai_enabled)
    merged_ai_provider = update_data.get("ai_provider", db_board.ai_provider)
    merged_ai_model = update_data.get("ai_model", db_board.ai_model)
    if merged_ai_provider is not None and merged_ai_provider not in SUPPORTED_AI_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=get_text(
                user=current_user, key="errors.boards.aiProviderInvalid"
            ),
        )

    if merged_ai_enabled and (not merged_ai_provider or not merged_ai_model):
        raise HTTPException(
            status_code=400,
            detail=get_text(
                user=current_user, key="errors.boards.aiProviderRequired"
            ),
        )
    if not merged_ai_enabled:
        # Disabling AI must also remove stale provider/model selections. Keeping
        # them makes a later re-enable silently revive an old configuration and
        # leaves the persisted board state inconsistent with the UI.
        update_data["ai_provider"] = None
        update_data["ai_model"] = None

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

    # Remove association rows explicitly before deleting the board. This keeps
    # the endpoint safe on databases where ORM cascade settings differ.
    db.query(BoardSymbol).filter(BoardSymbol.board_id == board_id).delete()
    db.query(BoardAssignment).filter(BoardAssignment.board_id == board_id).delete()
    # Other boards may link to this board through a symbol; clear those
    # nullable references before deleting the target board.
    db.query(BoardSymbol).filter(BoardSymbol.linked_board_id == board_id).update(
        {BoardSymbol.linked_board_id: None}, synchronize_session=False
    )

    db.delete(db_board)
    db.commit()
    return {"ok": True}
