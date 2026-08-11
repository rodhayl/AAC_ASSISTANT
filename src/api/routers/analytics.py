"""
Analytics API Router
Provides REST endpoints for symbol usage analytics and insights.
"""


from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger
from sqlalchemy.orm import Session

from src.aac_app.models import BoardSymbol, Symbol, User
from src.aac_app.services.runtime_translation import normalize_language_code, translate_text
from src.aac_app.services.symbol_analytics import SymbolAnalytics
from src.aac_app.services.symbol_catalog import (
    ANALYTICS_EXTRA_NOUN_CATEGORIES,
    NOUN_CATEGORY_KEYWORDS,
    PLACE_CATEGORY_KEYWORDS,
    intent_articles,
    intent_pronouns,
)
from src.api.deps import get_current_active_user, get_db, get_text
from src.api.schemas import NextSymbolRequest, SymbolUsageRequest

router = APIRouter()
analytics_service = SymbolAnalytics()


def _log_usage_request(
    request: SymbolUsageRequest,
    current_user: User,
    db: Session,
    failure_detail: str = "Failed to log usage",
) -> int:
    """Persist one analytics write request and return its symbol count."""
    symbols = [symbol.model_dump() for symbol in request.symbols]
    if not analytics_service.log_symbol_usage(
        user_id=current_user.id,
        symbols=symbols,
        context_topic=request.context_topic,
        session_id=request.session_id,
        semantic_intent=request.semantic_intent,
        db=db,
    ):
        raise HTTPException(status_code=500, detail=failure_detail)

    # Commit before responding: the UI requests next-symbol predictions right
    # after logging usage, and the request dependency's teardown commit runs
    # only after the response is sent. A prediction could otherwise miss the
    # symbols the user just selected. (The analytics service itself documents
    # that a caller-supplied request session remains responsible for its
    # commit.)
    db.commit()
    return len(symbols)


@router.post("/usage", status_code=status.HTTP_201_CREATED)
def log_symbol_usage(
    request: SymbolUsageRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Log usage of symbols."""
    try:
        count = _log_usage_request(request, current_user, db)
        logger.info(f"Logged usage for {count} symbols for user {current_user.id}")
        return {"success": True, "count": count}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to log usage: {e}")
        raise HTTPException(status_code=500, detail="Failed to log usage")


@router.get("/frequent-sequences", response_model=list[dict])
def get_frequent_sequences(
    limit: int = Query(10, ge=1, le=50, description="Maximum sequences to return"),
    min_occurrences: int = Query(
        2, ge=1, le=100, description="Minimum times sequence must appear"
    ),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Get user's most frequently used symbol sequences.

    Returns patterns of symbols commonly used together,
    useful for predictive suggestions and communication shortcuts.
    """
    try:
        sequences = analytics_service.get_frequent_sequences(
            user_id=current_user.id,
            limit=limit,
            min_occurrences=min_occurrences,
            db=db,
        )

        logger.info(
            f"Retrieved {len(sequences)} frequent sequences for user {current_user.id}"
        )
        return sequences

    except Exception as e:
        logger.error(f"Failed to get frequent sequences: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=get_text(
                user=current_user,
                key="errors.analytics.frequentSequencesFailed",
                error=str(e),
            ),
        )


from src.aac_app.services.prediction_service import prediction_service


@router.post("/next-symbol", response_model=list[dict])
def get_next_symbol_suggestions_post(
    request: NextSymbolRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Predict next symbol using N-gram engine and usage history.
    Replaces heavy LLM calls with lightweight multilanguage prediction.

    Deliberately a sync endpoint: the work is CPU/DB/translation bound and
    must run in FastAPI's threadpool so it never blocks the event loop and
    stalls unrelated requests (boards, SPA assets, etc.).
    """
    try:
        current_symbols = request.current_symbols
        limit = request.limit
        intent = request.intent  # general, pronouns, verbs, articles, nouns, places
        offset = request.offset

        logger.info(f"Suggestions request: user={current_user.id}, intent={intent}, limit={limit}, offset={offset}")

        # Parse current symbols
        symbols_list = []
        if current_symbols:
            labels = [
                label.strip() for label in current_symbols.split(",") if label.strip()
            ]
            symbols_list = [{"label": label} for label in labels]

        # Determine language from user settings (intent lists and fallback behavior)
        user_lang = "en"
        if current_user.settings and current_user.settings.ui_language:
            user_lang = current_user.settings.ui_language
        normalized_user_lang = normalize_language_code(user_lang) or "en"

        # 0. Handle specific intents (Quick Words)
        if intent in ["pronouns", "verbs", "articles", "nouns", "places"]:
            try:
                from sqlalchemy import and_, func, or_

                def build_query(board_scoped: bool):
                    q = db.query(Symbol).filter(Symbol.label.isnot(None))
                    if board_scoped and request.board_id is not None:
                        q = q.join(BoardSymbol, BoardSymbol.symbol_id == Symbol.id).filter(
                            BoardSymbol.board_id == request.board_id,
                            BoardSymbol.is_visible == True,  # noqa: E712
                        )
                    return q

                def apply_language_filter(q, strict: bool):
                    if not strict:
                        return q
                    return q.filter(
                        or_(
                            func.lower(Symbol.language) == normalized_user_lang,
                            func.lower(Symbol.language).like(f"{normalized_user_lang}-%"),
                        )
                    )

                def language_rank(sym: Symbol) -> int:
                    sym_lang = normalize_language_code(getattr(sym, "language", None))
                    if sym_lang == normalized_user_lang:
                        return 0
                    if sym_lang == "en":
                        return 1
                    return 2

                def localized_label(sym: Symbol) -> str:
                    if language_rank(sym) == 0:
                        return sym.label
                    return translate_text(sym.label, normalized_user_lang) or sym.label

                def apply_intent_filter(q):
                    if intent == "pronouns":
                        pronouns = intent_pronouns(user_lang)
                        return q.filter(
                            or_(
                                Symbol.category.ilike("%pronoun%"),
                                Symbol.category.ilike("%people%"),
                                func.lower(Symbol.label).in_([p.lower() for p in pronouns]),
                            )
                        )
                    if intent == "articles":
                        articles = intent_articles(user_lang)
                        return q.filter(
                            or_(
                                Symbol.category.ilike("%article%"),
                                Symbol.category.ilike("%preposition%"),
                                func.lower(Symbol.label).in_([a.lower() for a in articles]),
                            )
                        )
                    if intent == "verbs":
                        return q.filter(Symbol.category.ilike("%verb%"))
                    if intent == "nouns":
                        noun_categories = [
                            *NOUN_CATEGORY_KEYWORDS,
                            *ANALYTICS_EXTRA_NOUN_CATEGORIES,
                        ]
                        return q.filter(
                            and_(
                                ~Symbol.category.ilike("%pronoun%"),
                                ~Symbol.category.ilike("%people%"),
                                ~Symbol.category.ilike("%article%"),
                                ~Symbol.category.ilike("%preposition%"),
                                or_(*[Symbol.category.ilike(f"%{cat}%") for cat in noun_categories]),
                            )
                        )
                    if intent == "places":
                        return q.filter(
                            or_(*[Symbol.category.ilike(f"%{cat}%") for cat in PLACE_CATEGORY_KEYWORDS])
                        )
                    return q

                def format_results(rows):
                    rows = sorted(rows, key=lambda sym: (language_rank(sym), sym.id))
                    seen = set()
                    suggestions = []
                    for sym in rows:
                        label = localized_label(sym)
                        label_norm = (label or "").strip().lower()
                        if not label_norm or label_norm in seen:
                            continue
                        seen.add(label_norm)
                        suggestions.append(
                            {
                                "symbol_id": sym.id,
                                "label": label,
                                "category": sym.category,
                                "image_path": sym.image_path,
                                "confidence": 1.0,
                                "source": "category",
                            }
                        )
                        if len(suggestions) >= limit:
                            break
                    return suggestions

                strict_passes = [True, False]
                board_scopes = [request.board_id is not None, False]
                for strict in strict_passes:
                    for board_scoped in board_scopes:
                        query = build_query(board_scoped)
                        query = apply_language_filter(query, strict)
                        query = apply_intent_filter(query)
                        results = query.offset(offset).limit(limit * 3).all()
                        suggestions = format_results(results)
                        if suggestions:
                            return suggestions
            except Exception as db_err:
                logger.error(f"Database error in intent query: {db_err}")
                # Fall back to general suggestion if specific intent fails
                pass

        # Get unified suggestions from PredictionService
        final_suggestions = prediction_service.predict_next(
            user_id=current_user.id,
            current_symbols=symbols_list,
            limit=limit,
            language=user_lang,
            offset=offset,
            board_id=request.board_id,
            db=db,
        )

        logger.info(
            f"Generated {len(final_suggestions)} suggestions using PredictionService for user {current_user.id}"
        )
        return final_suggestions

    except Exception as e:
        logger.error(f"Failed to get next symbol suggestions: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=get_text(
                user=current_user,
                key="errors.analytics.suggestionsFailed",
                error=str(e),
            ),
        )



@router.post("/log", status_code=status.HTTP_201_CREATED)
def log_symbol_usage_legacy(
    request: SymbolUsageRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Log symbol usage for older clients that still use ``/analytics/log``."""
    try:
        _log_usage_request(
            request,
            current_user,
            db,
            failure_detail=get_text(
                user=current_user, key="errors.analytics.logSymbolFailed"
            ),
        )
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to log symbol usage: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=get_text(
                user=current_user, key="errors.analytics.logFailed", error=str(e)
            ),
        )


@router.get("/category-preferences", response_model=dict)
def get_category_preferences(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Analyze which symbol categories user uses most.

    Returns usage statistics by category with counts and percentages,
    useful for personalizing board layouts and symbol selection.
    """
    try:
        preferences = analytics_service.get_category_preferences(
            user_id=current_user.id, db=db
        )

        logger.info(f"Retrieved category preferences for user {current_user.id}")
        return preferences

    except Exception as e:
        logger.error(f"Failed to get category preferences: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=get_text(
                user=current_user,
                key="errors.analytics.preferencesFailed",
                error=str(e),
            ),
        )


@router.get("/usage-stats", response_model=dict)
def get_usage_statistics(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Get overall usage statistics for user.

    Returns comprehensive usage data including:
    - Total symbols used
    - Unique symbols
    - Most frequently used symbols
    - Intent distribution
    - Average utterance length
    """
    try:
        stats = analytics_service.get_usage_stats(
            user_id=current_user.id, days=days, db=db
        )

        logger.info(f"Retrieved {days}-day usage stats for user {current_user.id}")
        return stats

    except Exception as e:
        logger.error(f"Failed to get usage statistics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=get_text(
                user=current_user, key="errors.analytics.statsFailed", error=str(e)
            ),
        )
