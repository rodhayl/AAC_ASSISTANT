import os
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from loguru import logger
from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session

from src.aac_app.models import BoardSymbol, CommunicationBoard, Symbol, SymbolUsageLog, User
from src.aac_app.services.achievement_system import AchievementSystem
from src.aac_app.services.vector_utils import delete_symbol as delete_symbol_embedding
from src.aac_app.services.vector_utils import index_symbol
from src.api import schemas
from src.api.deps import get_current_active_user, get_db, get_text

router = APIRouter()


@router.get("/symbols/categories", response_model=list[str])
def get_symbol_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Return the distinct symbol categories without loading symbol records."""
    categories = (
        db.query(Symbol.category)
        .filter(Symbol.category.is_not(None))
        .distinct()
        .order_by(Symbol.category)
        .all()
    )
    return [category for (category,) in categories]


def _apply_symbol_search(query, search: str, db: Session):
    """Apply the existing keyword-plus-semantic symbol search to a query."""
    s = f"%{search.lower()}%"

    try:
        from src.api.deps import get_vector_store

        vs = get_vector_store()
        if vs and len(search) > 3:
            semantic_results = vs.search(search, k=20)
            semantic_ids = [
                item["id"]
                for item in semantic_results
                if item.get("type") == "symbol" and "id" in item
            ]

            if semantic_ids:
                logger.info(f"Semantic search found {len(semantic_ids)} symbols for '{search}'")
                semantic_order = case(
                    {symbol_id: index for index, symbol_id in enumerate(semantic_ids)},
                    value=Symbol.id,
                    else_=len(semantic_ids),
                )
                return query.filter(
                    or_(
                        func.lower(Symbol.label).like(s),
                        func.lower(Symbol.description).like(s),
                        func.lower(Symbol.keywords).like(s),
                        Symbol.id.in_(semantic_ids),
                    )
                ).order_by(semantic_order)

        return query.filter(
            or_(
                func.lower(Symbol.label).like(s),
                func.lower(Symbol.description).like(s),
                func.lower(Symbol.keywords).like(s),
            )
        )
    except Exception as e:
        logger.warning(f"Semantic search failed: {e}")
        return query.filter(
            or_(
                func.lower(Symbol.label).like(s),
                func.lower(Symbol.description).like(s),
                func.lower(Symbol.keywords).like(s),
            )
        )


@router.get("/symbols", response_model=list[schemas.SymbolResponse])
def get_symbols(
    skip: int = 0,
    limit: int = 100,
    category: str = None,
    search: str = None,
    keywords: str = None,
    language: str = None,
    usage: str | None = Query(None, pattern="^(in_use|unused)$"),
    sort: str = Query("default", pattern="^(default|newest|oldest|alpha)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get symbols with optional filters, ordered by order_index ASC"""
    from sqlalchemy import func

    usage_subq = (
        db.query(
            BoardSymbol.symbol_id.label("sid"),
            func.count(BoardSymbol.id).label("use_count"),
        )
        .group_by(BoardSymbol.symbol_id)
        .subquery()
    )

    query = db.query(Symbol, usage_subq.c.use_count)
    query = query.outerjoin(usage_subq, usage_subq.c.sid == Symbol.id)
    if category:
        query = query.filter(Symbol.category == category)
    if language:
        query = query.filter(Symbol.language == language)
    if search:
        query = _apply_symbol_search(query, search, db)
    if keywords:
        kw = f"%{keywords.lower()}%"
        query = query.filter(func.lower(Symbol.keywords).like(kw))
    if usage == "in_use":
        query = query.filter(
            (usage_subq.c.use_count.is_not(None)) & (usage_subq.c.use_count > 0)
        )
    if usage == "unused":
        query = query.filter(
            (usage_subq.c.use_count.is_(None)) | (usage_subq.c.use_count == 0)
        )

    # Sorting logic
    if sort != "default":
        if sort == "newest":
            query = query.order_by(Symbol.id.desc())
        elif sort == "oldest":
            query = query.order_by(Symbol.id.asc())
        elif sort == "alpha":
            query = query.order_by(Symbol.label.asc())
    elif category and category.lower() == "core":
        logger.info("Sorting by core category logic")
        # Sort by user usage frequency (SymbolUsageLog)
        freq_subq = (
            db.query(
                SymbolUsageLog.symbol_id.label("sid"),
                func.count(SymbolUsageLog.id).label("freq_count"),
            )
            .filter(SymbolUsageLog.user_id == current_user.id)
            .group_by(SymbolUsageLog.symbol_id)
            .subquery()
        )

        query = query.outerjoin(freq_subq, freq_subq.c.sid == Symbol.id)
        # Sort by frequency desc (nulls last), then label asc
        query = query.order_by(
            freq_subq.c.freq_count.desc().nullslast(), Symbol.label.asc()
        )
    else:
        query = query.order_by(Symbol.order_index, Symbol.id)

    results = query.offset(skip).limit(limit).all()
    symbols: list[Symbol] = []
    for sym, use_count in results:
        sym.is_in_use = bool(use_count and use_count > 0)
        symbols.append(sym)
    return symbols


@router.post("/symbols", response_model=schemas.SymbolResponse)
def create_symbol(
    symbol: schemas.SymbolCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create a new symbol"""
    db_symbol = Symbol(**symbol.model_dump())
    db.add(db_symbol)
    db.commit()
    db.refresh(db_symbol)
    index_symbol(db_symbol)
    return db_symbol


@router.put("/symbols/reorder")
def reorder_symbols(
    updates: list[schemas.SymbolReorderUpdate],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Batch update symbol order_index for global library ordering.
    IMPORTANT: This route MUST come before /symbols/{symbol_id} to avoid path conflicts.

    Args:
        updates: List of symbol ID and new order_index pairs
        db: Database session

    Returns:
        Success status with count of successfully updated symbols
    """
    try:
        updated_count = 0
        for update in updates:
            symbol = db.query(Symbol).filter(Symbol.id == update.id).first()
            if symbol:
                symbol.order_index = update.order_index
                updated_count += 1

        db.commit()
        return {"ok": True, "updated": updated_count}
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to reorder symbols: {e}")
        raise HTTPException(
            status_code=500,
            detail=get_text(
                user=current_user, key="errors.boards.reorderFailed", error=str(e)
            ),
        )


@router.post("/symbols/upload", response_model=schemas.SymbolResponse)
async def upload_symbol(
    label: str = Form(...),
    description: str = Form(None),
    category: str = Form("general"),
    keywords: str = Form(None),
    language: str = Form("en"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Upload a new symbol image"""
    base_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..")
    )
    uploads_dir = os.path.join(base_dir, "uploads", "symbols")
    os.makedirs(uploads_dir, exist_ok=True)
    ext = os.path.splitext(file.filename or "")[1].lower() or ".png"
    name = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(uploads_dir, name)
    # Read file content for validation
    content = file.file.read()
    # Basic validation: type and size
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(
            status_code=400,
            detail=get_text(user=current_user, key="errors.boards.invalidFileType"),
        )
    max_bytes = 5 * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=400,
            detail=get_text(user=current_user, key="errors.boards.fileTooLarge"),
        )
    with open(path, "wb") as f:
        f.write(content)
    public_path = f"/uploads/symbols/{name}"
    db_symbol = Symbol(
        label=label,
        description=description,
        category=category,
        image_path=public_path,
        audio_path=None,
        keywords=keywords,
        language=language,
        is_builtin=False,
    )
    db.add(db_symbol)
    db.commit()
    db.refresh(db_symbol)
    index_symbol(db_symbol)
    return db_symbol


@router.put("/symbols/{symbol_id}", response_model=schemas.SymbolResponse)
def update_symbol(
    symbol_id: int,
    payload: schemas.SymbolUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    db_symbol = db.query(Symbol).filter(Symbol.id == symbol_id).first()
    if not db_symbol:
        raise HTTPException(
            status_code=404,
            detail=get_text(user=current_user, key="errors.boards.symbolNotFound"),
        )
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(db_symbol, key, value)
    db.commit()
    db.refresh(db_symbol)
    index_symbol(db_symbol)
    # Attach usage flag
    use_count = db.query(BoardSymbol).filter(BoardSymbol.symbol_id == symbol_id).count()
    db_symbol.is_in_use = use_count > 0
    return db_symbol


@router.post("/symbols/{symbol_id}/image", response_model=schemas.SymbolResponse)
async def update_symbol_image(
    symbol_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    db_symbol = db.query(Symbol).filter(Symbol.id == symbol_id).first()
    if not db_symbol:
        raise HTTPException(
            status_code=404,
            detail=get_text(user=current_user, key="errors.boards.symbolNotFound"),
        )
    base_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..")
    )
    uploads_dir = os.path.join(base_dir, "uploads", "symbols")
    os.makedirs(uploads_dir, exist_ok=True)
    ext = os.path.splitext(file.filename or "")[1].lower() or ".png"
    name = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(uploads_dir, name)
    content = file.file.read()
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(
            status_code=400,
            detail=get_text(user=current_user, key="errors.boards.invalidFileType"),
        )
    max_bytes = 5 * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=400,
            detail=get_text(user=current_user, key="errors.boards.fileTooLarge"),
        )
    with open(path, "wb") as f:
        f.write(content)
    public_path = f"/uploads/symbols/{name}"
    db_symbol.image_path = public_path
    db.commit()
    db.refresh(db_symbol)
    use_count = db.query(BoardSymbol).filter(BoardSymbol.symbol_id == symbol_id).count()
    db_symbol.is_in_use = use_count > 0
    return db_symbol


@router.delete("/symbols/{symbol_id}")
def delete_symbol(
    symbol_id: int,
    force: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    symbol = db.query(Symbol).filter(Symbol.id == symbol_id).first()
    if not symbol:
        raise HTTPException(
            status_code=404,
            detail=get_text(user=current_user, key="errors.boards.symbolNotFound"),
        )
    in_use = (
        db.query(BoardSymbol).filter(BoardSymbol.symbol_id == symbol_id).count() > 0
    )
    if in_use and not force:
        raise HTTPException(
            status_code=400,
            detail=get_text(user=current_user, key="errors.boards.symbolInUse"),
        )
    if in_use:
        db.query(BoardSymbol).filter(BoardSymbol.symbol_id == symbol_id).delete()
    db.delete(symbol)
    db.commit()
    delete_symbol_embedding(symbol_id)
    return {"ok": True, "deleted": symbol_id}


@router.post("/{board_id}/symbols", response_model=schemas.BoardSymbolResponse)
def add_symbol_to_board(
    board_id: int,
    symbol_data: schemas.BoardSymbolCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Add a symbol to a board"""
    # Check board
    board = (
        db.query(CommunicationBoard).filter(CommunicationBoard.id == board_id).first()
    )
    if not board:
        raise HTTPException(
            status_code=404,
            detail=get_text(user=current_user, key="errors.boards.boardNotFound"),
        )

    # Permission check
    if current_user.user_type != "admin" and board.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail=get_text(
                user=current_user, key="errors.boards.unauthorizedModifyBoard"
            ),
        )

    # Check symbol
    symbol = db.query(Symbol).filter(Symbol.id == symbol_data.symbol_id).first()
    if not symbol:
        raise HTTPException(
            status_code=404,
            detail=get_text(user=current_user, key="errors.boards.symbolNotFound"),
        )

    db_board_symbol = BoardSymbol(board_id=board_id, **symbol_data.model_dump())
    db.add(db_board_symbol)
    db.commit()
    db.refresh(db_board_symbol)
    # Update vocabulary_size progress for board owner
    try:
        user_id = board.user_id
        # Count distinct symbols across user's boards
        from sqlalchemy import distinct

        boards = (
            db.query(CommunicationBoard.id)
            .filter(CommunicationBoard.user_id == user_id)
            .subquery()
        )
        count = (
            db.query(distinct(BoardSymbol.symbol_id))
            .join(boards, BoardSymbol.board_id == boards.c.id)
            .count()
        )
        AchievementSystem().update_progress(
            user_id, "vocabulary_size", float(count), db=db
        )
        AchievementSystem().check_achievements(user_id, db=db)
    except Exception:
        pass
    return db_board_symbol


def _update_single_symbol(db_board_symbol: BoardSymbol, update: dict) -> bool:
    """Apply updates to a single board symbol."""
    changed = False
    if "position_x" in update:
        db_board_symbol.position_x = update["position_x"]
        changed = True
    if "position_y" in update:
        db_board_symbol.position_y = update["position_y"]
        changed = True
    if "size" in update:
        db_board_symbol.size = update["size"]
        changed = True
    if "is_visible" in update:
        db_board_symbol.is_visible = update["is_visible"]
        changed = True
    if "custom_text" in update:
        db_board_symbol.custom_text = update["custom_text"]
        changed = True
    if "linked_board_id" in update:
        db_board_symbol.linked_board_id = update["linked_board_id"]
        changed = True
    return changed


@router.put("/{board_id}/symbols/batch")
def batch_update_board_symbols(
    board_id: int,
    updates: list[dict],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Batch update multiple symbol positions"""
    # Verify board exists
    board = (
        db.query(CommunicationBoard).filter(CommunicationBoard.id == board_id).first()
    )
    if not board:
        raise HTTPException(
            status_code=404,
            detail=get_text(user=current_user, key="errors.boards.boardNotFound"),
        )

    # Permission check
    if current_user.user_type != "admin" and board.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail=get_text(
                user=current_user, key="errors.boards.unauthorizedModifyBoard"
            ),
        )

    updated_count = 0
    for update in updates:
        symbol_id = update.get("id")
        if not symbol_id:
            continue

        db_board_symbol = (
            db.query(BoardSymbol)
            .filter(BoardSymbol.board_id == board_id, BoardSymbol.id == symbol_id)
            .first()
        )

        if db_board_symbol and _update_single_symbol(db_board_symbol, update):
            updated_count += 1

    db.commit()
    return {"ok": True, "updated": updated_count}


@router.put(
    "/{board_id}/symbols/{symbol_id}", response_model=schemas.BoardSymbolResponse
)
def update_board_symbol(
    board_id: int,
    symbol_id: int,
    symbol_data: schemas.BoardSymbolUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Update a symbol's position or properties on a board"""
    # Verify board permission first (optimization: check board ownership before symbol query)
    board = (
        db.query(CommunicationBoard).filter(CommunicationBoard.id == board_id).first()
    )
    if not board:
        raise HTTPException(
            status_code=404,
            detail=get_text(user=current_user, key="errors.boards.boardNotFound"),
        )

    if current_user.user_type != "admin" and board.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail=get_text(
                user=current_user, key="errors.boards.unauthorizedModifyBoard"
            ),
        )

    db_board_symbol = (
        db.query(BoardSymbol)
        .filter(BoardSymbol.board_id == board_id, BoardSymbol.id == symbol_id)
        .first()
    )

    if not db_board_symbol:
        raise HTTPException(
            status_code=404,
            detail=get_text(
                user=current_user, key="errors.boards.symbolNotFoundOnBoard"
            ),
        )

    for key, value in symbol_data.model_dump(exclude_unset=True).items():
        setattr(db_board_symbol, key, value)

    db.commit()
    db.refresh(db_board_symbol)
    return db_board_symbol


@router.delete("/{board_id}/symbols/{symbol_id}")
def remove_symbol_from_board(
    board_id: int,
    symbol_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Remove a symbol from a board"""
    # Verify board permission
    board = (
        db.query(CommunicationBoard).filter(CommunicationBoard.id == board_id).first()
    )
    if not board:
        raise HTTPException(
            status_code=404,
            detail=get_text(user=current_user, key="errors.boards.boardNotFound"),
        )

    if current_user.user_type != "admin" and board.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail=get_text(
                user=current_user, key="errors.boards.unauthorizedModifyBoard"
            ),
        )

    db_board_symbol = (
        db.query(BoardSymbol)
        .filter(BoardSymbol.board_id == board_id, BoardSymbol.id == symbol_id)
        .first()
    )

    if not db_board_symbol:
        raise HTTPException(
            status_code=404,
            detail=get_text(
                user=current_user, key="errors.boards.symbolNotFoundOnBoard"
            ),
        )

    db.delete(db_board_symbol)
    db.commit()
    return {"ok": True}
