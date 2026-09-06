import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from loguru import logger
from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session

from src import config
from src.aac_app.models import BoardSymbol, CommunicationBoard, Symbol, SymbolUsageLog, User
from src.aac_app.services.achievement_system import AchievementSystem
from src.aac_app.services.local_vector_store import vector_store_operation_lock
from src.aac_app.services.runtime_translation import normalize_language_code
from src.aac_app.services.symbol_image_backfill import schedule_symbol_image_download
from src.aac_app.services.vector_utils import delete_symbol as delete_symbol_embedding
from src.aac_app.services.vector_utils import index_symbol
from src.api import schemas
from src.api.deps import (
    get_board_or_404,
    get_current_active_user,
    get_current_staff_user,
    get_db,
    get_llm_provider,
    get_text,
    require_board_owner_or_admin,
    validate_board_position,
    validate_linked_board,
)
from src.api.file_uploads import read_image_upload, remove_owned_upload

router = APIRouter()


def _get_symbol_or_404(db: Session, symbol_id: int, current_user: User) -> Symbol:
    """Fetch a symbol by id or raise a translated 404."""
    symbol = db.query(Symbol).filter(Symbol.id == symbol_id).first()
    if not symbol:
        raise HTTPException(
            status_code=404,
            detail=get_text(user=current_user, key="errors.boards.symbolNotFound"),
        )
    return symbol


def _get_board_symbol_or_404(
    db: Session, board_id: int, symbol_id: int, current_user: User
) -> BoardSymbol:
    """Fetch a board's symbol association after ownership check, or 404."""
    board = get_board_or_404(db, board_id, current_user)
    require_board_owner_or_admin(board, current_user)
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
    return db_board_symbol


async def _save_symbol_image(file: UploadFile, current_user: User) -> str:
    """Persist an uploaded symbol image and return its public URL path."""
    uploads_dir = config.UPLOADS_DIR / "symbols"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    content, ext = await read_image_upload(
        file,
        invalid_type_detail=get_text(user=current_user, key="errors.boards.invalidFileType"),
        too_large_detail=get_text(user=current_user, key="errors.boards.fileTooLarge"),
        empty_detail=get_text(user=current_user, key="errors.boards.emptyFile"),
    )
    name = f"{uuid.uuid4().hex}{ext}"
    path = uploads_dir / name
    try:
        with path.open("wb") as f:
            f.write(content)
    except OSError:
        remove_owned_upload(f"/uploads/symbols/{name}", uploads_dir)
        raise
    return f"/uploads/symbols/{name}"


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


_LIKE_ESCAPE = "\\"


def _literal_like_pattern(search: str) -> str:
    """Escape LIKE wildcards so the user's text matches literally.

    Without escaping, a ``%`` in the search box matches everything and ``_``
    matches any character; ``\\`` neutralizes them and is passed to every
    ``.like(..., escape=...)`` using this pattern.
    """
    escaped = search.replace(_LIKE_ESCAPE, _LIKE_ESCAPE + _LIKE_ESCAPE)
    escaped = escaped.replace("%", _LIKE_ESCAPE + "%").replace("_", _LIKE_ESCAPE + "_")
    return f"%{escaped.lower()}%"


def _apply_symbol_search(query, search: str, db: Session):
    """Apply the existing keyword-plus-semantic symbol search to a query."""
    s = _literal_like_pattern(search)

    try:
        from src.api.deps import get_vector_store

        vs = None
        semantic_results = []
        if len(search) > 3:
            with vector_store_operation_lock:
                vs = get_vector_store()
                semantic_results = vs.search(search, k=20) if vs else []
        if vs and semantic_results:
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
                        func.lower(Symbol.label).like(
                            s, escape=_LIKE_ESCAPE
                        ),
                        func.lower(Symbol.description).like(
                            s, escape=_LIKE_ESCAPE
                        ),
                        func.lower(Symbol.keywords).like(
                            s, escape=_LIKE_ESCAPE
                        ),
                        Symbol.id.in_(semantic_ids),
                    )
                ).order_by(semantic_order)

        return query.filter(
            or_(
                func.lower(Symbol.label).like(s, escape=_LIKE_ESCAPE),
                func.lower(Symbol.description).like(s, escape=_LIKE_ESCAPE),
                func.lower(Symbol.keywords).like(s, escape=_LIKE_ESCAPE),
            )
        )
    except Exception as e:
        logger.warning(f"Semantic search failed: {e}")
        return query.filter(
            or_(
                func.lower(Symbol.label).like(s, escape=_LIKE_ESCAPE),
                func.lower(Symbol.description).like(s, escape=_LIKE_ESCAPE),
                func.lower(Symbol.keywords).like(s, escape=_LIKE_ESCAPE),
            )
        )


@router.get("/symbols", response_model=list[schemas.SymbolResponse])
def get_symbols(
    skip: int = Query(0, ge=0, le=100_000),
    limit: int = Query(100, ge=1, le=1000),
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
        normalized_language = normalize_language_code(language)
        if normalized_language:
            query = query.filter(Symbol.language == normalized_language)
    if search:
        query = _apply_symbol_search(query, search, db)
    if keywords:
        query = query.filter(
            func.lower(Symbol.keywords).like(
                _literal_like_pattern(keywords), escape=_LIKE_ESCAPE
            )
        )
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
    current_user: User = Depends(get_current_staff_user),
):
    """Create a new symbol"""
    symbol_data = symbol.model_dump()
    symbol_data["label"] = symbol_data["label"].strip()
    if not symbol_data["label"]:
        raise HTTPException(
            status_code=400,
            detail=get_text(user=current_user, key="errors.validation"),
        )
    # Normalize to a base code so it matches the exact-match language filter.
    symbol_data["language"] = normalize_language_code(symbol_data.get("language")) or "en"
    db_symbol = Symbol(**symbol_data)
    db.add(db_symbol)
    db.commit()
    db.refresh(db_symbol)
    index_symbol(db_symbol)
    if not db_symbol.image_path:
        schedule_symbol_image_download([db_symbol.id])
    return db_symbol


@router.put("/symbols/reorder")
def reorder_symbols(
    updates: list[schemas.SymbolReorderUpdate],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_staff_user),
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
        if not updates:
            return {"ok": True, "updated": 0}

        update_by_id = {update.id: update.order_index for update in updates}
        symbols = db.query(Symbol).filter(Symbol.id.in_(update_by_id)).all()
        for symbol in symbols:
            symbol.order_index = update_by_id[symbol.id]

        db.commit()
        return {"ok": True, "updated": len(symbols)}
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to reorder symbols: {e}")
        raise HTTPException(
            status_code=500,
            detail=get_text(
                user=current_user, key="errors.boards.reorderFailed"
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
    current_user: User = Depends(get_current_staff_user),
):
    """Upload a new symbol image"""
    language = normalize_language_code(language) or "en"
    label = label.strip()
    if not label:
        raise HTTPException(
            status_code=400,
            detail=get_text(user=current_user, key="errors.validation"),
        )
    public_path = await _save_symbol_image(file, current_user)
    uploads_dir = config.UPLOADS_DIR / "symbols"
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
    try:
        db.commit()
    except Exception:
        db.rollback()
        remove_owned_upload(public_path, uploads_dir)
        raise
    try:
        db.refresh(db_symbol)
    except Exception as exc:
        logger.warning("Symbol image persisted but refresh failed: {}", exc)
    try:
        index_symbol(db_symbol)
    except Exception as exc:
        logger.warning("Symbol image saved but indexing failed: {}", exc)
    return db_symbol


@router.post("/symbols/generate-svg", response_model=schemas.SymbolResponse)
def generate_svg_symbol(
    label: str = Form(...),
    description: str = Form(None),
    category: str = Form("general"),
    keywords: str = Form(None),
    language: str = Form("en"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_staff_user),
):
    """Generate a pictogram for a label the catalog does not contain.

    The LLM emits a strict JSON *shape spec* (never raw SVG), which is
    validated and rendered with drawsvg — so the only tags/attributes ever
    written are ones we control. The rendered SVG is stored under the symbol
    uploads directory and a normal symbol row is created.
    """
    language = normalize_language_code(language) or "en"
    label = label.strip()
    if not label:
        raise HTTPException(
            status_code=400,
            detail=get_text(user=current_user, key="errors.validation"),
        )

    provider = get_llm_provider()
    generate_sync = getattr(provider, "generate_sync", None)
    if not callable(generate_sync):
        raise HTTPException(status_code=503, detail="LLM provider has no sync generation")

    from src.aac_app.services.svg_symbol_generator import (
        ShapeSpecError,
        generate_svg_text,
    )

    try:
        svg_text = generate_svg_text(label, language, generate_sync)
    except ShapeSpecError as exc:
        logger.error(f"LLM SVG generation failed for {label!r}: {exc}")
        raise HTTPException(
            status_code=422,
            detail="Model did not return a valid shape spec; try again",
        ) from exc
    except Exception as exc:
        logger.error(f"LLM SVG generation failed for {label!r}: {exc}")
        raise HTTPException(
            status_code=502, detail="Failed to generate symbol image"
        ) from exc

    try:
        from src.aac_app.services.svg_symbol_generator import (
            write_generated_symbol_image,
        )

        public_path = write_generated_symbol_image(svg_text, config.UPLOADS_DIR / "symbols")
    except OSError:
        raise HTTPException(status_code=500, detail="Failed to store symbol image")

    uploads_dir = config.UPLOADS_DIR / "symbols"

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
    try:
        db.commit()
    except Exception:
        db.rollback()
        remove_owned_upload(public_path, uploads_dir)
        raise HTTPException(status_code=500, detail="Failed to create symbol")
    try:
        db.refresh(db_symbol)
    except Exception as exc:
        logger.warning("Generated symbol persisted but refresh failed: {}", exc)
    try:
        index_symbol(db_symbol)
    except Exception as exc:
        logger.warning("Generated symbol saved but indexing failed: {}", exc)
    return db_symbol


@router.put("/symbols/{symbol_id}", response_model=schemas.SymbolResponse)
def update_symbol(
    symbol_id: int,
    payload: schemas.SymbolUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_staff_user),
):
    db_symbol = _get_symbol_or_404(db, symbol_id, current_user)
    symbol_data = payload.model_dump(exclude_unset=True)
    if "label" in symbol_data:
        symbol_data["label"] = symbol_data["label"].strip()
        if not symbol_data["label"]:
            raise HTTPException(
                status_code=400,
                detail=get_text(user=current_user, key="errors.validation"),
            )
    if "language" in symbol_data:
        symbol_data["language"] = normalize_language_code(symbol_data["language"])
    for key, value in symbol_data.items():
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
    current_user: User = Depends(get_current_staff_user),
):
    db_symbol = _get_symbol_or_404(db, symbol_id, current_user)
    public_path = await _save_symbol_image(file, current_user)
    uploads_dir = config.UPLOADS_DIR / "symbols"
    old_image_path = db_symbol.image_path
    db_symbol.image_path = public_path
    try:
        db.commit()
    except Exception:
        db.rollback()
        remove_owned_upload(public_path, uploads_dir)
        raise
    try:
        db.refresh(db_symbol)
    except Exception as exc:
        logger.warning("Symbol image persisted but refresh failed: {}", exc)
    remove_owned_upload(old_image_path, uploads_dir)
    use_count = db.query(BoardSymbol).filter(BoardSymbol.symbol_id == symbol_id).count()
    db_symbol.is_in_use = use_count > 0
    return db_symbol


@router.delete("/symbols/{symbol_id}")
def delete_symbol(
    symbol_id: int,
    force: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_staff_user),
):
    symbol = _get_symbol_or_404(db, symbol_id, current_user)
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
    image_path = symbol.image_path
    db.delete(symbol)
    db.commit()
    remove_owned_upload(image_path, config.UPLOADS_DIR / "symbols")
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
    board = get_board_or_404(db, board_id, current_user)
    require_board_owner_or_admin(board, current_user)

    # Check symbol exists (raises a translated 404 otherwise).
    _get_symbol_or_404(db, symbol_data.symbol_id, current_user)
    validate_board_position(
        board,
        symbol_data.position_x,
        symbol_data.position_y,
        current_user,
    )
    validate_linked_board(
        db, board_id, symbol_data.linked_board_id, current_user
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
    except Exception as exc:
        # The symbol is already committed and returned; progress is a
        # best-effort update that must not fail the request.
        logger.warning("Vocabulary progress update failed: {}", exc)
    return db_board_symbol


def _update_single_symbol(
    db_board_symbol: BoardSymbol,
    update: dict,
    *,
    db: Session,
    current_user: User,
) -> bool:
    """Apply updates to a single board symbol after validating link targets."""
    changed = False
    if "symbol_id" in update:
        new_symbol_id = update["symbol_id"]
        if type(new_symbol_id) is not int:
            raise HTTPException(
                status_code=400,
                detail=get_text(user=current_user, key="errors.boards.symbolNotFound"),
            )
        _get_symbol_or_404(db, new_symbol_id, current_user)
        db_board_symbol.symbol_id = new_symbol_id
        changed = True
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
    if "color" in update:
        db_board_symbol.color = update["color"]
        changed = True
    if "custom_text" in update:
        db_board_symbol.custom_text = update["custom_text"]
        changed = True
    if "linked_board_id" in update:
        validate_linked_board(
            db,
            db_board_symbol.board_id,
            update["linked_board_id"],
            current_user,
        )
        db_board_symbol.linked_board_id = update["linked_board_id"]
        changed = True

    board = db.get(CommunicationBoard, db_board_symbol.board_id)
    if board is not None and changed:
        validate_board_position(
            board,
            db_board_symbol.position_x or 0,
            db_board_symbol.position_y or 0,
            current_user,
        )

    return changed


@router.put("/{board_id}/symbols/batch")
def batch_update_board_symbols(
    board_id: int,
    updates: list[schemas.BoardSymbolBatchUpdate],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Batch update multiple symbol positions"""
    board = get_board_or_404(db, board_id, current_user)
    require_board_owner_or_admin(board, current_user)

    updated_count = 0
    for update_model in updates:
        update = update_model.model_dump(exclude_unset=True)
        symbol_id = update.pop("id", None)
        if not symbol_id:
            continue

        db_board_symbol = (
            db.query(BoardSymbol)
            .filter(BoardSymbol.board_id == board_id, BoardSymbol.id == symbol_id)
            .first()
        )

        if db_board_symbol and _update_single_symbol(
            db_board_symbol,
            update,
            db=db,
            current_user=current_user,
        ):
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
    db_board_symbol = _get_board_symbol_or_404(db, board_id, symbol_id, current_user)
    board = db.get(CommunicationBoard, board_id)
    if board is not None:
        validate_board_position(
            board,
            symbol_data.position_x if symbol_data.position_x is not None else db_board_symbol.position_x or 0,
            symbol_data.position_y if symbol_data.position_y is not None else db_board_symbol.position_y or 0,
            current_user,
        )
    updates = symbol_data.model_dump(exclude_unset=True)
    if "symbol_id" in updates:
        new_symbol_id = updates.pop("symbol_id")
        if new_symbol_id is None:
            raise HTTPException(
                status_code=400,
                detail=get_text(user=current_user, key="errors.boards.symbolNotFound"),
            )
        _get_symbol_or_404(db, new_symbol_id, current_user)
        db_board_symbol.symbol_id = new_symbol_id

    validate_linked_board(
        db, board_id, symbol_data.linked_board_id, current_user
    )

    for key, value in updates.items():
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
    db_board_symbol = _get_board_symbol_or_404(db, board_id, symbol_id, current_user)

    db.delete(db_board_symbol)
    db.commit()
    return {"ok": True}
