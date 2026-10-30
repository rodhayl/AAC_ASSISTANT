"""
Analytics API Router
Provides REST endpoints for symbol usage analytics and insights.
"""

from typing import Dict, List, Union

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger
from sqlalchemy.orm import Session

from src.aac_app.models.database import BoardSymbol, User, Symbol
from src.aac_app.services.symbol_analytics import SymbolAnalytics
from src.api.dependencies import get_current_active_user, get_db, get_text
from src.api.schemas import SymbolUsageRequest, NextSymbolRequest

router = APIRouter()
analytics_service = SymbolAnalytics()


@router.post("/usage", status_code=status.HTTP_201_CREATED)
async def log_symbol_usage(
    request: SymbolUsageRequest,
    current_user: User = Depends(get_current_active_user),
):
    """Log usage of symbols"""
    try:
        # Convert SymbolUsageItem objects to list of dicts
        symbols_list = [
            {
                "id": s.id,
                "label": s.label,
                "category": s.category,
            }
            for s in request.symbols
        ]
        
        analytics_service.log_symbol_usage(
            user_id=current_user.id,
            symbols=symbols_list,
            context_topic=request.context_topic,
            session_id=request.session_id,
        )
        
        logger.info(f"Logged usage for {len(symbols_list)} symbols for user {current_user.id}")
        return {"success": True, "count": len(symbols_list)}
    except Exception as e:
        logger.error(f"Failed to log usage: {e}")
        raise HTTPException(status_code=500, detail="Failed to log usage")


@router.get("/frequent-sequences", response_model=List[Dict])
async def get_frequent_sequences(
    limit: int = Query(10, ge=1, le=50, description="Maximum sequences to return"),
    min_occurrences: int = Query(
        2, ge=1, le=100, description="Minimum times sequence must appear"
    ),
    current_user: User = Depends(get_current_active_user),
):
    """
    Get user's most frequently used symbol sequences.

    Returns patterns of symbols commonly used together,
    useful for predictive suggestions and communication shortcuts.
    """
    try:
        sequences = analytics_service.get_frequent_sequences(
            user_id=current_user.id, limit=limit, min_occurrences=min_occurrences
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

@router.post("/next-symbol", response_model=List[Dict])
async def get_next_symbol_suggestions_post(
    request: NextSymbolRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Predict next symbol using N-gram engine and usage history.
    Replaces heavy LLM calls with lightweight multilanguage prediction.
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

                def apply_intent_filter(q):
                    if intent == "pronouns":
                        pronouns = (
                            ["yo", "tú", "tu", "él", "ella", "nosotros", "nosotras", "ellos", "ellas", "me", "mi", "mis"]
                            if user_lang.startswith("es")
                            else ["I", "you", "he", "she", "it", "we", "they", "me", "my", "your", "his", "her", "our", "their"]
                        )
                        return q.filter(
                            or_(
                                Symbol.category.ilike("%pronoun%"),
                                Symbol.category.ilike("%people%"),
                                func.lower(Symbol.label).in_([p.lower() for p in pronouns]),
                            )
                        )
                    if intent == "articles":
                        articles = (
                            ["el", "la", "los", "las", "un", "una", "unos", "unas", "es", "son", "está", "están", "en", "a", "de", "con", "para", "por"]
                            if user_lang.startswith("es")
                            else ["the", "a", "an", "is", "are", "am", "was", "were", "in", "on", "at", "to", "for", "of", "with"]
                        )
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
                            "food",
                            "drink",
                            "toy",
                            "animal",
                            "place",
                            "person",
                            "body",
                            "clothing",
                            "vehicle",
                            "home",
                            "school",
                            "nature",
                            "object",
                            "noun",
                            "generated",
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
                        place_categories = [
                            "place",
                            "places",
                            "location",
                            "room",
                            "home",
                            "school",
                            "city",
                            "country",
                            "nature",
                            "transport",
                            "vehicle",
                        ]
                        return q.filter(
                            or_(*[Symbol.category.ilike(f"%{cat}%") for cat in place_categories])
                        )
                    return q

                def format_results(rows):
                    seen = set()
                    suggestions = []
                    for sym in rows:
                        label_norm = (sym.label or "").strip().lower()
                        if not label_norm or label_norm in seen:
                            continue
                        seen.add(label_norm)
                        suggestions.append(
                            {
                                "symbol_id": sym.id,
                                "label": sym.label,
                                "category": sym.category,
                                "image_path": sym.image_path,
                                "confidence": 1.0,
                                "source": "category",
                            }
                        )
                        if len(suggestions) >= limit:
                            break
                    return suggestions

                # Prefer board-scoped results when possible; fall back to global library.
                for board_scoped in [request.board_id is not None, False]:
                    query = apply_intent_filter(build_query(board_scoped))
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



@router.get("/category-preferences", response_model=Dict)
async def get_category_preferences(
    current_user: User = Depends(get_current_active_user),
):
    """
    Analyze which symbol categories user uses most.

    Returns usage statistics by category with counts and percentages,
    useful for personalizing board layouts and symbol selection.
    """
    try:
        preferences = analytics_service.get_category_preferences(
            user_id=current_user.id
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


@router.get("/usage-stats", response_model=Dict)
async def get_usage_statistics(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    current_user: User = Depends(get_current_active_user),
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
        stats = analytics_service.get_usage_stats(user_id=current_user.id, days=days)

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


@router.post("/log", status_code=status.HTTP_201_CREATED)
async def log_symbol_usage(
    request: SymbolUsageRequest, current_user: User = Depends(get_current_active_user)
):
    """
    Log symbol usage for analytics.
    """
    try:
        # Convert Pydantic models to dicts for the service
        symbols_data = [s.model_dump() for s in request.symbols]

        success = analytics_service.log_symbol_usage(
            user_id=current_user.id,
            symbols=symbols_data,
            session_id=request.session_id,
            semantic_intent=request.semantic_intent,
            context_topic=request.context_topic,
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=get_text(
                    user=current_user, key="errors.analytics.logSymbolFailed"
                ),
            )

        return {"status": "success"}

    except Exception as e:
        logger.error(f"Failed to log symbol usage: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=get_text(
                user=current_user, key="errors.analytics.logFailed", error=str(e)
            ),
        )
