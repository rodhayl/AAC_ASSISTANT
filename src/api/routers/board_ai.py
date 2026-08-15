import random

from fastapi import APIRouter, Body, Depends, HTTPException
from loguru import logger
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from src import config
from src.aac_app.models import BoardSymbol, CommunicationBoard, Symbol, User
from src.aac_app.providers.ollama_provider import OllamaProvider
from src.aac_app.providers.openrouter_provider import OpenRouterProvider
from src.aac_app.services.board_generation_service import BoardGenerationService
from src.aac_app.services.translation_service import get_translation_service
from src.aac_app.services.vector_utils import index_symbol
from src.api import schemas
from src.api.deps import (
    get_board_or_404,
    get_current_active_user,
    get_db,
    get_setting_value,
    get_text,
    require_board_staff_or_owner,
    validate_board_position,
    validate_linked_board,
)

router = APIRouter()


def get_or_create_symbol(
    db: Session, label: str, symbol_key: str
) -> tuple[Symbol, bool]:
    """Return the symbol matching ``label``, creating it when absent.

    Returns ``(symbol, created)`` so callers know whether the symbol is new
    (and therefore needs embedding indexing). Reuse by label keeps AI board
    creation and AI suggestions from duplicating symbols.
    """
    symbol = db.query(Symbol).filter(Symbol.label == label).first()
    if symbol is not None:
        return symbol, False
    created = Symbol(
        label=label,
        keywords=symbol_key,
        image_path=f"/static/symbols/generated/{symbol_key}.png",  # placeholder
        category="generated",
        is_builtin=False,
    )
    db.add(created)
    db.flush()
    return created, True


def _fallback_board_suggestions(
    db: Session, *, board: CommunicationBoard, item_count: int
) -> list[dict]:
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

    # Sample from the indexed primary key instead of sorting the whole symbol
    # table with ORDER BY RANDOM().  The cyclic second query handles sparse IDs
    # and keeps the candidate set bounded for this development fallback.
    def sample_candidates(candidate_query):
        candidate_limit = max(item_count * 5, 25)
        max_id = candidate_query.with_entities(func.max(Symbol.id)).scalar()
        if not max_id:
            return []

        anchor = random.randint(1, max_id)
        candidates = (
            candidate_query.filter(Symbol.id >= anchor)
            .order_by(Symbol.id)
            .limit(candidate_limit)
            .all()
        )
        if len(candidates) < candidate_limit:
            candidates.extend(
                candidate_query.filter(Symbol.id < anchor)
                .order_by(Symbol.id)
                .limit(candidate_limit - len(candidates))
                .all()
            )
        return candidates

    candidates = sample_candidates(query)
    if not candidates and apply_cat_filter:
        # Category filters can be too strict for our built-in symbol sets; retry unfiltered.
        query = db.query(Symbol).filter(Symbol.label.isnot(None))
        if existing_symbol_ids:
            query = query.filter(~Symbol.id.in_(existing_symbol_ids))
        candidates = sample_candidates(query)

    seen: set[str] = set()
    items: list[dict] = []
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

    # Add manual symbols only after validating their foreign keys, positions,
    # and linked-board visibility. Invalid entries must abort the whole board
    # creation instead of being logged and silently dropped.
    if symbols_data:
        logger.info(f"Adding {len(symbols_data)} manual symbols to board {db_board.id}")
        for s_data in symbols_data:
            symbol = db.query(Symbol).filter(Symbol.id == s_data["symbol_id"]).first()
            if symbol is None:
                raise HTTPException(
                    status_code=404,
                    detail=get_text(user=current_user, key="errors.boards.symbolNotFound"),
                )
            validate_board_position(
                db_board,
                s_data["position_x"],
                s_data["position_y"],
                current_user,
            )
            validate_linked_board(
                db,
                db_board.id,
                s_data.get("linked_board_id"),
                current_user,
            )
            db.add(BoardSymbol(board_id=db_board.id, **s_data))
    else:
        logger.info("No manual symbols provided in payload")

    # Generate AI content if enabled
    created_symbols: list[Symbol] = []
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
                    item_count = min(board.grid_rows * board.grid_cols, 100)

                # Pass fail_silently=False to catch errors and abort board creation
                items = await ai_service.generate_board_items(
                    board.name,
                    board.description,
                    item_count=item_count,
                    fail_silently=False
                )

                logger.info(f"AI generated {len(items)} items")

                for idx, item in enumerate(items):
                    symbol_key = item["symbol_key"]
                    # Use label as fallback if symbol_key is empty
                    if not symbol_key:
                        symbol_key = item["label"].lower().replace(" ", "_")

                    symbol, is_new = get_or_create_symbol(
                        db, item["label"], symbol_key
                    )
                    if is_new:
                        created_symbols.append(symbol)

                    # Add to board
                    cols = db_board.grid_cols or 4
                    linked_board_id = item.get("linked_board_id")
                    validate_board_position(
                        db_board,
                        idx % cols,
                        idx // cols,
                        current_user,
                    )
                    validate_linked_board(
                        db, db_board.id, linked_board_id, current_user
                    )
                    board_symbol = BoardSymbol(
                        board_id=db_board.id,
                        symbol_id=symbol.id,
                        custom_text=item["label"],
                        color=item.get("color"),
                        linked_board_id=linked_board_id,
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

    db.refresh(db_board)
    for symbol in created_symbols:
        index_symbol(symbol)
    # Commit before responding: the board and its symbols must be durable
    # before the client navigates to it in a follow-up request. A single
    # commit here also keeps the whole create atomic if indexing fails.
    db.commit()
    return db_board


def _resolve_provider_for_board(
    board: CommunicationBoard, db: Session
) -> OllamaProvider | OpenRouterProvider | None:
    """
    Build an LLM provider instance from the board or primary global settings.
    """
    provider_type = board.ai_provider or get_setting_value("ai_provider", "ollama")
    model_name = board.ai_model

    # The primary marker and older source markers use the current global primary model.
    if not model_name or model_name.startswith("@"):
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
    payload: schemas.AISuggestionsRequest | None = Body(None),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Generate AI symbol suggestions for an existing board without mutating it."""
    board = get_board_or_404(db, board_id, current_user)
    require_board_staff_or_owner(
        board,
        current_user,
        db,
        error_key="errors.boards.unauthorizedSuggestions",
    )

    if not board.ai_enabled:
        raise HTTPException(
            status_code=400,
            detail=get_text(user=current_user, key="errors.boards.aiNotEnabled"),
        )

    provider = _resolve_provider_for_board(board, db)
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
        item_count = min(board.grid_rows * board.grid_cols, 100)

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
def apply_ai_suggestion(
    board_id: int,
    payload: schemas.AISuggestionApplyRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Apply a single AI suggestion by creating a symbol (if needed) and placing it on the board.
    """
    board = get_board_or_404(db, board_id, current_user)
    require_board_staff_or_owner(board, current_user, db)

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
    symbol, was_created = get_or_create_symbol(db, item.label, symbol_key)
    created_symbol = symbol if was_created else None
    if created_symbol is None:
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

    validate_board_position(board, target_x, target_y, current_user)
    validate_linked_board(
        db, board.id, item.linked_board_id, current_user
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
    if created_symbol is not None:
        index_symbol(created_symbol)
    db.commit()
    return board_symbol
