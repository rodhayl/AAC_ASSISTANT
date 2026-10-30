import os
import uuid
from functools import lru_cache
from typing import List, Optional, Union

from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)
from loguru import logger
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload, selectinload

from src import config
from src.aac_app.models.database import (
    BoardAssignment,
    BoardSymbol,
    CommunicationBoard,
    Symbol,
    SymbolUsageLog,
    User,
)
from src.aac_app.providers.ollama_provider import OllamaProvider
from src.aac_app.providers.openrouter_provider import OpenRouterProvider
from src.aac_app.services.achievement_system import AchievementSystem
from src.aac_app.services.board_generation_service import BoardGenerationService
from src.aac_app.services.translation_service import get_translation_service
from src.api import schemas
from src.api.dependencies import (
    get_current_active_user,
    get_db,
    get_setting_value,
    get_text,
)

router = APIRouter()

try:
    from deep_translator import GoogleTranslator as _GoogleTranslator
except Exception:  # pragma: no cover - optional dependency
    _GoogleTranslator = None

_translation_dependency_warning_emitted = False


@lru_cache(maxsize=16)
def _build_symbol_translator(target_lang: str):
    if _GoogleTranslator is None:
        return None
    return _GoogleTranslator(source="auto", target=target_lang)


def _translate_symbol_text(text: Optional[str], target_lang: Optional[str]) -> Optional[str]:
    """Best-effort symbol translation that safely degrades when dependency is absent."""
    global _translation_dependency_warning_emitted
    if not text or not target_lang:
        return text

    translator = _build_symbol_translator(target_lang)
    if translator is None:
        if not _translation_dependency_warning_emitted:
            logger.warning(
                "deep-translator not installed; returning original symbol text without runtime translation."
            )
            _translation_dependency_warning_emitted = True
        return text

    try:
        return translator.translate(text)
    except Exception as e:
        logger.warning(f"Translation failed: {e}")
        return text


def _fallback_board_suggestions(
    db: Session, *, board: CommunicationBoard, item_count: int
) -> List[dict]:
    """
    Best-effort, offline-friendly suggestions that do not depend on an external LLM.

    Used in non-production environments when an AI provider is unavailable.
    """
    existing_symbol_ids = {bs.symbol_id for bs in (board.symbols or [])}

    query = db.query(Symbol).filter(Symbol.label.isnot(None))
    if existing_symbol_ids:
        query = query.filter(~Symbol.id.in_(existing_symbol_ids))

    cat = (board.category or "").strip()
    apply_cat_filter = bool(cat) and cat.lower() not in {"general"}
    if apply_cat_filter:
        query = query.filter(
            or_(
                Symbol.category.ilike(f"%{cat}%"),
                Symbol.category.ilike("%general%"),
            )
        )

    # SQLite-friendly randomness; good enough for a fallback.
    candidates = query.order_by(func.random()).limit(max(item_count * 5, 25)).all()
    if not candidates and apply_cat_filter:
        # Category filters can be too strict for our built-in symbol sets; retry unfiltered.
        query = db.query(Symbol).filter(Symbol.label.isnot(None))
        if existing_symbol_ids:
            query = query.filter(~Symbol.id.in_(existing_symbol_ids))
        candidates = query.order_by(func.random()).limit(max(item_count * 5, 25)).all()

    seen: set[str] = set()
    items: List[dict] = []
    for sym in candidates:
        label = (sym.label or "").strip()
        if not label:
            continue
        norm = label.lower()
        if norm in seen:
            continue
        seen.add(norm)

        keyword = (sym.keywords or "").split(",")[0].strip() if sym.keywords else ""
        if not keyword:
            keyword = norm.replace(" ", "_")

        items.append({"label": label, "symbol_key": keyword, "color": "#E8F5E9"})
        if len(items) >= item_count:
            break

    return items


def serialize_symbol(
    bs: BoardSymbol, target_lang: str = None, is_language_learning: bool = False
):
    sym = getattr(bs, "symbol", None)

    # Translate if needed
    custom_text = bs.custom_text
    symbol_label = sym.label if sym else None

    if target_lang and not is_language_learning:
        custom_text = _translate_symbol_text(custom_text, target_lang)
        symbol_label = _translate_symbol_text(symbol_label, target_lang)

    return {
        "id": bs.id,
        "symbol_id": bs.symbol_id,
        "position_x": bs.position_x,
        "position_y": bs.position_y,
        "size": bs.size,
        "is_visible": bs.is_visible,
        "custom_text": custom_text,
        "color": bs.color,
        "linked_board_id": bs.linked_board_id,
        "symbol": (
            {
                "id": sym.id,
                "label": symbol_label,
                "description": sym.description,
                "category": sym.category,
                "image_path": sym.image_path,
                "audio_path": sym.audio_path,
                "keywords": sym.keywords,
                "language": sym.language,
                "is_builtin": sym.is_builtin,
                "created_at": sym.created_at,
            }
            if sym is not None
            else None
        ),
    }


def get_playable_count(board: CommunicationBoard) -> int:
    """
    Count symbols that are visible AND have either custom_text or a symbol label.
    This is used by the frontend to determine if a board has enough content to be playable.
    """
    count = 0
    for bs in board.symbols or []:
        if not bs.is_visible:
            continue
        has_text = bool(bs.custom_text)
        if not has_text and (b_sym := getattr(bs, "symbol", None)):
            has_text = bool(getattr(b_sym, "label", None))
        if has_text:
            count += 1
    return count


def serialize_board(b: CommunicationBoard, target_lang: str = None):
    is_learning = getattr(b, "is_language_learning", False)
    return {
        "id": b.id,
        "user_id": b.user_id,
        "name": b.name,
        "description": b.description,
        "category": b.category,
        "is_public": b.is_public,
        "is_template": b.is_template,
        "created_at": b.created_at,
        "updated_at": b.updated_at,
        "grid_rows": b.grid_rows,
        "grid_cols": b.grid_cols,
        "ai_enabled": b.ai_enabled,
        "ai_provider": b.ai_provider,
        "ai_model": b.ai_model,
        "locale": getattr(b, "locale", "en"),
        "is_language_learning": is_learning,
        "playable_symbols_count": get_playable_count(b),
        "symbols": [
            serialize_symbol(bs, target_lang, is_learning) for bs in (b.symbols or [])
        ],
    }


# --- Symbols (must come BEFORE /{board_id} to avoid route conflicts) ---


@router.post("/symbols", response_model=schemas.SymbolResponse)
def create_symbol(
    symbol: schemas.SymbolCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create a new symbol in the library"""
    try:
        db_symbol = Symbol(**symbol.model_dump(), is_builtin=False)
        db.add(db_symbol)
        db.commit()
        db.refresh(db_symbol)
        
        # Index in vector store if possible
        try:
            from src.aac_app.services.vector_utils import index_symbol
            index_symbol(db_symbol)
        except Exception as e:
            logger.warning(f"Failed to index new symbol: {e}")
            
        return db_symbol
    except Exception as e:
        logger.error(f"Failed to create symbol: {e}")
        raise HTTPException(status_code=500, detail="Failed to create symbol")


@router.get("/symbols", response_model=List[schemas.SymbolResponse])
def get_symbols(
    skip: int = 0,
    limit: int = 100,
    category: str = None,
    search: str = None,
    keywords: str = None,
    language: str = None,
    usage: Optional[str] = Query(None, pattern="^(in_use|unused)$"),
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
        s = f"%{search.lower()}%"
        from sqlalchemy import or_

        # Semantic Search via Vector Store (if available)
        try:
            from src.api.dependencies import get_vector_store
            vs = get_vector_store()
            # If search term has spaces or is > 3 chars, try semantic search
            if vs and len(search) > 3:
                semantic_results = vs.search(search, k=20)
                # Extract symbol IDs from semantic results
                semantic_ids = [
                    item["id"] 
                    for item in semantic_results 
                    if item.get("type") == "symbol" and "id" in item
                ]
                
                if semantic_ids:
                    logger.info(f"Semantic search found {len(semantic_ids)} symbols for '{search}'")
                    # Combine SQL LIKE with Vector Search IDs
                    query = query.filter(
                        or_(
                            func.lower(Symbol.label).like(s),
                            func.lower(Symbol.description).like(s),
                            func.lower(Symbol.keywords).like(s),
                            Symbol.id.in_(semantic_ids)
                        )
                    )
                else:
                    # Fallback to standard LIKE
                    query = query.filter(
                        or_(
                            func.lower(Symbol.label).like(s),
                            func.lower(Symbol.description).like(s),
                            func.lower(Symbol.keywords).like(s),
                        )
                    )
            else:
                 query = query.filter(
                    or_(
                        func.lower(Symbol.label).like(s),
                        func.lower(Symbol.description).like(s),
                        func.lower(Symbol.keywords).like(s),
                    )
                )
        except Exception as e:
            logger.warning(f"Semantic search failed: {e}")
            query = query.filter(
                or_(
                    func.lower(Symbol.label).like(s),
                    func.lower(Symbol.description).like(s),
                    func.lower(Symbol.keywords).like(s),
                )
            )
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
    symbols: List[Symbol] = []
    for sym, use_count in results:
        setattr(sym, "is_in_use", bool(use_count and use_count > 0))
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
    return db_symbol


@router.put("/symbols/reorder")
def reorder_symbols(
    updates: List[schemas.SymbolReorderUpdate],
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
    # Attach usage flag
    use_count = db.query(BoardSymbol).filter(BoardSymbol.symbol_id == symbol_id).count()
    setattr(db_symbol, "is_in_use", use_count > 0)
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
    setattr(db_symbol, "is_in_use", use_count > 0)
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
    return {"ok": True, "deleted": symbol_id}


# --- Boards ---


@router.get("/")
def get_boards(
    skip: int = 0,
    limit: int = 100,
    user_id: Optional[int] = None,
    name: Optional[str] = None,
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

        result = [
            {
                "id": b.id,
                "user_id": b.user_id,
                "name": b.name,
                "description": b.description,
                "category": b.category,
                "is_public": b.is_public,
                "is_template": b.is_template,
                "created_at": b.created_at,
                "updated_at": b.updated_at,
                "grid_rows": b.grid_rows,
                "grid_cols": b.grid_cols,
                "ai_enabled": b.ai_enabled,
                "ai_provider": b.ai_provider,
                "ai_model": b.ai_model,
                "locale": getattr(b, "locale", "en"),
                "is_language_learning": getattr(b, "is_language_learning", False),
                "symbols": [],
                "playable_symbols_count": get_playable_count(b),
            }
            for b in boards
        ]

        return result
    except Exception as e:
        logger.error(f"Error fetching boards: {e}")
        logger.exception("Traceback:")
        # Fallback empty list to avoid UI crash; error logged by FastAPI
        return []


@router.get("/assigned", response_model=List[schemas.BoardResponse])
def get_assigned_boards(
    student_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    # Only allow if admin, teacher, or the student themselves
    if (
        current_user.user_type != "admin"
        and current_user.user_type != "teacher"
        and current_user.id != student_id
    ):
        raise HTTPException(
            status_code=403,
            detail=get_text(
                user=current_user, key="errors.boards.unauthorizedAssignments"
            ),
        )

    assignments = (
        db.query(BoardAssignment).filter(BoardAssignment.student_id == student_id).all()
    )
    board_ids = [a.board_id for a in assignments]
    boards = (
        db.query(CommunicationBoard)
        .filter(CommunicationBoard.id.in_(board_ids))
        .options(joinedload(CommunicationBoard.symbols).joinedload(BoardSymbol.symbol))
        .all()
        if board_ids
        else []
    )

    for b in boards:
        try:
            setattr(b, "playable_symbols_count", get_playable_count(b))
        except Exception:
            # If anything goes wrong, keep returning the board; client will fall back.
            pass

    return boards


@router.post("", response_model=schemas.BoardResponse)
@router.post("/", response_model=schemas.BoardResponse)
async def create_board(
    board: schemas.BoardCreate,
    user_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Create a new communication board"""
    # Verify permission
    if user_id != current_user.id and current_user.user_type != "admin":
        raise HTTPException(
            status_code=403,
            detail=get_text(
                user=current_user, key="errors.boards.cannotCreateBoardForOther"
            ),
        )

    # Verify user exists (if admin creating for someone else)
    if user_id != current_user.id:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=404,
                detail=get_text(user=current_user, key="errors.userNotFound"),
            )
    else:
        user = current_user

    # Validate AI configuration
    if board.ai_enabled:
        if not board.ai_provider or not board.ai_model:
            raise HTTPException(
                status_code=400,
                detail=get_text(
                    user=current_user, key="errors.boards.aiProviderRequired"
                ),
            )
        if board.ai_provider not in ["ollama", "openrouter"]:
            raise HTTPException(
                status_code=400,
                detail=get_text(
                    user=current_user, key="errors.boards.aiProviderInvalid"
                ),
            )

    payload = board.model_dump()
    # Extract symbols to handle manually (SQLAlchemy doesn't handle list of dicts for relationship automatically)
    symbols_data = payload.pop("symbols", []) if "symbols" in payload else []
    
    db_board = CommunicationBoard(**payload, user_id=user_id)
    db.add(db_board)
    # Flush to get an ID but don't commit yet
    db.flush()
    
    # Add manual symbols if provided
    if symbols_data:
        logger.info(f"Adding {len(symbols_data)} manual symbols to board {db_board.id}")
        for s_data in symbols_data:
            # s_data is a dict from BoardSymbolCreate
            try:
                bs = BoardSymbol(board_id=db_board.id, **s_data)
                db.add(bs)
            except Exception as e:
                logger.error(f"Failed to add symbol: {e}")
    else:
        logger.info("No manual symbols provided in payload")

    # Generate AI content if enabled
    if board.ai_enabled:
        try:
            logger.info(
                f"Generating AI content for board {db_board.id} using {board.ai_provider} ({board.ai_model})"
            )

            # Instantiate the correct provider based on request
            provider = None
            if board.ai_provider == "ollama":
                base_url = get_setting_value("ollama_base_url", config.OLLAMA_BASE_URL)
                provider = OllamaProvider(base_url=base_url, model=board.ai_model)
            elif board.ai_provider == "openrouter":
                api_key = get_setting_value("openrouter_api_key", "")
                provider = OpenRouterProvider(api_key=api_key, model=board.ai_model)

            if provider:
                # Create a temporary service instance
                ai_service = BoardGenerationService(provider)
                
                # Calculate item count based on grid size, default to 12 if not specified
                item_count = 12
                if board.grid_rows and board.grid_cols:
                    item_count = board.grid_rows * board.grid_cols
                
                # Pass fail_silently=False to catch errors and abort board creation
                items = await ai_service.generate_board_items(
                    board.name, 
                    board.description, 
                    item_count=item_count,
                    fail_silently=False
                )

                logger.info(f"AI generated {len(items)} items")

                for idx, item in enumerate(items):
                    # Check if symbol exists
                    symbol_key = item["symbol_key"]
                    # Use label as fallback if symbol_key is empty
                    if not symbol_key:
                        symbol_key = item["label"].lower().replace(" ", "_")

                    # Search by label since we don't have a unique key column
                    symbol = (
                        db.query(Symbol).filter(Symbol.label == item["label"]).first()
                    )

                    if not symbol:
                        # Create new symbol
                        symbol = Symbol(
                            label=item["label"],
                            keywords=symbol_key,
                            image_path=f"/static/symbols/generated/{symbol_key}.png",  # Placeholder
                            category="generated",
                            is_builtin=False,
                        )
                        db.add(symbol)
                        db.flush()

                    # Add to board
                    cols = db_board.grid_cols or 4
                    board_symbol = BoardSymbol(
                        board_id=db_board.id,
                        symbol_id=symbol.id,
                        custom_text=item["label"],
                        color=item.get("color"),
                        linked_board_id=item.get("linked_board_id"),
                        position_x=idx % cols,
                        position_y=idx // cols,
                        size=1,
                        is_visible=True,
                    )
                    db.add(board_symbol)

                logger.info(
                    f"Successfully added {len(items)} AI-generated symbols to board {db_board.id}"
                )
            else:
                logger.warning("Could not initialize AI provider")
                # If AI was requested but provider failed to init, we should probably fail?
                # For now, let's just log warning, but maybe we should raise error if strict?
                # The validation above checks for valid provider type, so this handles connection init issues?
                # Actually provider init is just class instantiation, so it shouldn't fail unless params are missing.
                pass

        except Exception as e:
            logger.error(f"AI Board generation failed: {e}")
            db.rollback()
            raise HTTPException(
                status_code=502,  # Bad Gateway / Upstream Error
                detail=get_text(
                    user=current_user, 
                    key="errors.boards.aiGenerationFailed", 
                    error=str(e)
                ),
            )

    db.commit()
    db.refresh(db_board)
    return db_board


def _resolve_provider_for_board(
    board: CommunicationBoard, db: Session, force_source: Optional[str] = None
) -> Optional[Union[OllamaProvider, OpenRouterProvider]]:
    """
    Build an LLM provider instance based on board configuration falling back to global settings.
    """
    # Determine effective source
    source = force_source

    # If no forced source, check board for stored intent (special markers)
    if not source:
        if board.ai_model == "@primary":
            source = "primary"
        elif board.ai_model == "@fallback":
            source = "fallback"

    # If explicit source (from request or board marker), load fresh from global settings
    if source == "primary":
        provider_type = get_setting_value("ai_provider", "ollama")
        if provider_type == "openrouter":
            model_name = get_setting_value("openrouter_model", "")
            api_key = get_setting_value("openrouter_api_key", "")
            return OpenRouterProvider(api_key=api_key, model=model_name)
        else:
            model_name = get_setting_value("ollama_model", "")
            base_url = get_setting_value("ollama_base_url", config.OLLAMA_BASE_URL)
            return OllamaProvider(base_url=base_url, model=model_name)

    if source == "fallback":
        provider_type = get_setting_value("fallback_ai_provider", "ollama")
        if provider_type == "openrouter":
            model_name = get_setting_value("fallback_openrouter_model", "")
            api_key = get_setting_value("fallback_openrouter_api_key", "")
            return OpenRouterProvider(api_key=api_key, model=model_name)
        else:
            model_name = get_setting_value("fallback_ollama_model", "")
            base_url = get_setting_value(
                "fallback_ollama_base_url", config.OLLAMA_BASE_URL
            )
            return OllamaProvider(base_url=base_url, model=model_name)

    # Legacy/Custom behavior: use board stored values
    provider_type = board.ai_provider or get_setting_value("ai_provider", "ollama")
    model_name = board.ai_model

    # If board doesn't carry a model, fallback to global/default (Primary)
    if not model_name:
        if provider_type == "openrouter":
            model_name = get_setting_value("openrouter_model", "")
        else:
            model_name = get_setting_value("ollama_model", "")

    if not provider_type or not model_name:
        return None

    if provider_type == "openrouter":
        api_key = get_setting_value("openrouter_api_key", "")
        return OpenRouterProvider(api_key=api_key, model=model_name)

    base_url = get_setting_value("ollama_base_url", config.OLLAMA_BASE_URL)
    return OllamaProvider(base_url=base_url, model=model_name)


@router.post("/{board_id}/ai/suggestions")
async def generate_ai_suggestions(
    board_id: int,
    payload: Optional[schemas.AISuggestionsRequest] = Body(None),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Generate AI symbol suggestions for an existing board without mutating it."""
    board = (
        db.query(CommunicationBoard).filter(CommunicationBoard.id == board_id).first()
    )
    if not board:
        raise HTTPException(
            status_code=404,
            detail=get_text(user=current_user, key="errors.boards.boardNotFound"),
        )

    # Allow admin, teacher, or board owner
    if (
        current_user.user_type not in ["admin", "teacher"]
        and board.user_id != current_user.id
    ):
        raise HTTPException(
            status_code=403,
            detail=get_text(
                user=current_user, key="errors.boards.unauthorizedSuggestions"
            ),
        )

    if not board.ai_enabled:
        raise HTTPException(
            status_code=400,
            detail=get_text(user=current_user, key="errors.boards.aiNotEnabled"),
        )

    provider = _resolve_provider_for_board(
        board, db, force_source=payload.ai_source if payload else None
    )
    if not provider:
        raise HTTPException(
            status_code=400,
            detail=get_text(user=current_user, key="errors.boards.aiNotConfigured"),
        )

    service = BoardGenerationService(provider)

    # Resolve language for generation
    ts = get_translation_service()
    lang = ts.resolve_language(current_user)

    # Calculate item count: use payload if provided, otherwise derive from grid, default to 12
    item_count = 12
    if payload and payload.item_count:
        item_count = payload.item_count
    elif board.grid_rows and board.grid_cols:
        item_count = board.grid_rows * board.grid_cols

    try:
        items = await service.generate_board_items(
            board.name,
            board.description or "",
            item_count=item_count,
            fail_silently=False,
            refine_prompt=payload.refine_prompt if payload else "",
            regenerate=payload.regenerate if payload else False,
            language=lang,
        )
        if not items:
            raise RuntimeError("AI returned no valid items")
        return {"items": items}
    except Exception as e:
        logger.error(f"Failed to generate AI suggestions for board {board_id}: {e}")
        if config.ENVIRONMENT != "production":
            fallback_items = _fallback_board_suggestions(db, board=board, item_count=item_count)
            if fallback_items:
                logger.warning(f"Using fallback suggestions for board {board_id} (provider unavailable)")
                return {"items": fallback_items}
        detail_msg = get_text(
            user=current_user, key="errors.boards.suggestionsFailed", error=str(e)
        )
        raise HTTPException(status_code=502, detail=detail_msg)


@router.post(
    "/{board_id}/ai/suggestions/apply", response_model=schemas.BoardSymbolResponse
)
async def apply_ai_suggestion(
    board_id: int,
    payload: schemas.AISuggestionApplyRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Apply a single AI suggestion by creating a symbol (if needed) and placing it on the board.
    """
    board = (
        db.query(CommunicationBoard).filter(CommunicationBoard.id == board_id).first()
    )
    if not board:
        raise HTTPException(
            status_code=404,
            detail=get_text(user=current_user, key="errors.boards.boardNotFound"),
        )

    if (
        current_user.user_type not in ["admin", "teacher"]
        and board.user_id != current_user.id
    ):
        raise HTTPException(
            status_code=403,
            detail=get_text(
                user=current_user, key="errors.boards.unauthorizedModifyBoard"
            ),
        )

    if not board.ai_enabled:
        raise HTTPException(
            status_code=400,
            detail=get_text(user=current_user, key="errors.boards.aiNotEnabled"),
        )

    item = payload.item
    if not item or not item.label:
        raise HTTPException(
            status_code=400,
            detail=get_text(
                user=current_user, key="errors.boards.suggestionLabelRequired"
            ),
        )

    symbol_key = item.symbol_key or item.label.lower().replace(" ", "_")

    # Try to reuse existing symbol by label to avoid duplicates
    symbol = db.query(Symbol).filter(Symbol.label == item.label).first()
    if not symbol:
        symbol = Symbol(
            label=item.label,
            keywords=symbol_key,
            image_path=f"/static/symbols/generated/{symbol_key}.png",  # placeholder
            category="generated",
            is_builtin=False,
        )
        db.add(symbol)
        db.flush()
    else:
        # Avoid duplicate symbol entries per board
        existing_board_symbol = (
            db.query(BoardSymbol)
            .filter(
                BoardSymbol.board_id == board.id, BoardSymbol.symbol_id == symbol.id
            )
            .first()
        )
        if existing_board_symbol:
            return existing_board_symbol

    # Find position
    r = board.grid_rows or 4
    c = board.grid_cols or 5
    used = {(s.position_x, s.position_y) for s in (board.symbols or [])}
    target_x = payload.position_x if payload.position_x is not None else 0
    target_y = payload.position_y if payload.position_y is not None else 0

    if (target_x, target_y) in used:
        found = None
        for y in range(r):
            for x in range(c):
                if (x, y) not in used:
                    found = (x, y)
                    break
            if found:
                break
        if found:
            target_x, target_y = found
        else:
            raise HTTPException(
                status_code=400,
                detail=get_text(user=current_user, key="errors.boards.boardFull"),
            )

    board_symbol = BoardSymbol(
        board_id=board.id,
        symbol_id=symbol.id,
        custom_text=item.label,
        color=item.color,
        linked_board_id=item.linked_board_id,
        position_x=target_x,
        position_y=target_y,
        size=1,
        is_visible=True,
    )
    db.add(board_symbol)
    db.commit()
    db.refresh(board_symbol)
    return board_symbol


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
        target_lang = ts.resolve_language(current_user)

        # If target lang is same as board locale (or 'en'), skip translation optimization
        board_locale = getattr(board, "locale", "en")
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
    db_board = (
        db.query(CommunicationBoard).filter(CommunicationBoard.id == board_id).first()
    )
    if not db_board:
        raise HTTPException(
            status_code=404,
            detail=get_text(user=current_user, key="errors.boards.boardNotFound"),
        )

    # Permission check
    if current_user.user_type != "admin" and db_board.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail=get_text(
                user=current_user, key="errors.boards.unauthorizedModifyBoard"
            ),
        )

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
    db_board = (
        db.query(CommunicationBoard).filter(CommunicationBoard.id == board_id).first()
    )
    if not db_board:
        raise HTTPException(
            status_code=404,
            detail=get_text(user=current_user, key="errors.boards.boardNotFound"),
        )

    # Permission check
    if current_user.user_type != "admin" and db_board.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail=get_text(
                user=current_user, key="errors.boards.unauthorizedModifyBoard"
            ),
        )

    # Delete associated symbols (cascade should handle this but let's be safe if needed,
    # but currently BoardSymbol is the link. Cascade delete on DB level usually handles it if configured)
    # SQLAlchemy relationship cascade="all, delete" might be needed on model.
    # Let's assume manual cleanup of association table if not.
    db.query(BoardSymbol).filter(BoardSymbol.board_id == board_id).delete()

    db.delete(db_board)
    db.commit()
    return {"ok": True}


# --- Board Symbols ---


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
        AchievementSystem().update_progress(user_id, "vocabulary_size", float(count))
        AchievementSystem().check_achievements(user_id)
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
    updates: List[dict],
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

        if db_board_symbol:
            if _update_single_symbol(db_board_symbol, update):
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


# --- Board Assignments ---


@router.post("/{board_id}/assign")
def assign_board_to_student(
    board_id: int,
    payload: schemas.BoardAssignRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    # Only Admin, Teacher, or Board Owner can assign
    board = (
        db.query(CommunicationBoard).filter(CommunicationBoard.id == board_id).first()
    )
    if not board:
        raise HTTPException(
            status_code=404,
            detail=get_text(user=current_user, key="errors.boards.boardNotFound"),
        )

    if (
        current_user.user_type != "admin"
        and current_user.user_type != "teacher"
        and board.user_id != current_user.id
    ):
        raise HTTPException(
            status_code=403,
            detail=get_text(user=current_user, key="errors.boards.unauthorizedAssign"),
        )

    student = db.query(User).filter(User.id == payload.student_id).first()
    if not student or student.user_type != "student":
        raise HTTPException(
            status_code=400,
            detail=get_text(user=current_user, key="errors.boards.invalidStudent"),
        )
    existing = (
        db.query(BoardAssignment)
        .filter(
            BoardAssignment.board_id == board_id,
            BoardAssignment.student_id == payload.student_id,
        )
        .first()
    )
    if existing:
        return {"ok": True}

    assigned_by_id = payload.assigned_by if payload.assigned_by else current_user.id
    assignment = BoardAssignment(
        board_id=board_id, student_id=payload.student_id, assigned_by=assigned_by_id
    )
    db.add(assignment)
    db.commit()
    return {"ok": True}


@router.delete("/{board_id}/assign/{student_id}")
def unassign_board_from_student(
    board_id: int,
    student_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    # Only Admin, Teacher, or Board Owner can unassign
    board = (
        db.query(CommunicationBoard).filter(CommunicationBoard.id == board_id).first()
    )
    if not board:
        raise HTTPException(
            status_code=404,
            detail=get_text(user=current_user, key="errors.boards.boardNotFound"),
        )

    if (
        current_user.user_type != "admin"
        and current_user.user_type != "teacher"
        and board.user_id != current_user.id
    ):
        raise HTTPException(
            status_code=403,
            detail=get_text(
                user=current_user, key="errors.boards.unauthorizedUnassign"
            ),
        )

    assignment = (
        db.query(BoardAssignment)
        .filter(
            BoardAssignment.board_id == board_id,
            BoardAssignment.student_id == student_id,
        )
        .first()
    )
    if not assignment:
        raise HTTPException(
            status_code=404,
            detail=get_text(user=current_user, key="errors.boards.assignmentNotFound"),
        )
    db.delete(assignment)
    db.commit()
    return {"ok": True}
