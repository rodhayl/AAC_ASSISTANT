"""
Analytics API Router
Provides REST endpoints for symbol usage analytics and insights.
"""


import json
import re

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger
from sqlalchemy.orm import Session

from src.aac_app.models import BoardSymbol, Symbol, User
from src.aac_app.services.runtime_translation import normalize_language_code, translate_text
from src.aac_app.services.symbol_analytics import SymbolAnalytics
from src.aac_app.services.symbol_catalog import (
    ARTICLE_CATEGORIES,
    NON_NOUN_CATEGORIES,
    PLACE_CATEGORIES,
    PRONOUN_CATEGORIES,
    VERB_CATEGORIES,
    intent_articles,
    intent_pronouns,
)
from src.api.deps import (
    get_board_or_404,
    get_current_active_user,
    get_db,
    get_llm_provider,
    get_text,
    require_board_view_access,
)
from src.api.schemas import NextSymbolRequest, SymbolUsageRequest

router = APIRouter()
analytics_service = SymbolAnalytics()


# Capped topic-vocabulary expansion so a single bad provider response cannot
# flood the Smartbar. TTL-bounded in-memory cache lives in PredictionService.
_TOPIC_WORDS_MAX = 10


def _parse_topic_words(response: str) -> list[str]:
    """Extract a word list from a model response (JSON array or plain list)."""
    text = (response or "").strip()
    if not text:
        return []
    # Strip markdown fences that some providers wrap lists in.
    if text.startswith("```"):
        text = text.strip("`")
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1 :]
    items: list[str] = []
    stripped = text.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, list):
                items = [str(item) for item in parsed]
        except (ValueError, TypeError):
            items = []
    if not items:
        items = [
            part.strip().strip('"\'-,•')
            for part in re.split(r"[\n,;]+", stripped)
            if part.strip()
        ]
    return [item for item in items if item][:_TOPIC_WORDS_MAX]


def _build_topic_word_fetcher():
    """Return a (language, topic) -> words callable backed by the LLM provider.

    Built lazily per request and only used when the catalog misses the topic.
    The provider is ignored on any failure; the prediction tiers then behave
    exactly as before (pure catalog/history suggestions).
    """

    def fetch(language: str, topic: str) -> list[str]:
        provider = get_llm_provider()
        generate_sync = getattr(provider, "generate_sync", None)
        if not callable(generate_sync):
            return []
        lang_name = "Spanish" if language.startswith("es") else "English"
        prompt = (
            f"List up to {_TOPIC_WORDS_MAX} short words or short phrases "
            f"({lang_name}) a student studying the topic would want to say. "
            f"Topic: {topic}.\n"
            "Return only a comma-separated list, no numbering, no extra text."
        )
        try:
            text = generate_sync(
                prompt=prompt,
                temperature=0.5,
                max_tokens=150,
            )
            return _parse_topic_words(text)
        except Exception as exc:
            logger.warning("Topic word generation failed: {}", exc)
            return []

    return fetch


def _log_usage_request(
    request: SymbolUsageRequest,
    current_user: User,
    db: Session,
    failure_detail: str | None = None,
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
        raise HTTPException(
            status_code=500,
            detail=failure_detail
            or get_text(user=current_user, key="errors.analytics.logSymbolFailed"),
        )

    # Commit before responding: the UI requests next-symbol predictions right
    # after logging usage, and the request dependency's teardown commit runs
    # only after the response is sent. A prediction could otherwise miss the
    # symbols the user just selected. (The analytics service itself documents
    # that a caller-supplied request session remains responsible for its
    # commit.)
    db.commit()
    return len(symbols)


@router.post("/usage", status_code=status.HTTP_201_CREATED)
@router.post("/log", status_code=status.HTTP_201_CREATED)
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
        raise HTTPException(
            status_code=500,
            detail=get_text(user=current_user, key="errors.analytics.logSymbolFailed"),
        )


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

        if request.board_id is not None:
            board = get_board_or_404(db, request.board_id, current_user)
            require_board_view_access(board, current_user, db)

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
                from sqlalchemy import func, or_

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
                    translated = translate_text(sym.label, normalized_user_lang)
                    if not translated:
                        raise RuntimeError("Required symbol translation returned no text")
                    return translated

                def apply_intent_filter(q):
                    if intent == "pronouns":
                        pronouns = intent_pronouns(user_lang)
                        return q.filter(
                            or_(
                                Symbol.category.in_(PRONOUN_CATEGORIES),
                                func.lower(Symbol.label).in_([p.lower() for p in pronouns]),
                            )
                        )
                    if intent == "articles":
                        articles = intent_articles(user_lang)
                        return q.filter(
                            or_(
                                Symbol.category.in_(ARTICLE_CATEGORIES),
                                func.lower(Symbol.label).in_([a.lower() for a in articles]),
                            )
                        )
                    if intent == "verbs":
                        return q.filter(Symbol.category.in_(VERB_CATEGORIES))
                    if intent == "nouns":
                        return q.filter(
                            Symbol.category.isnot(None),
                            ~Symbol.category.in_(NON_NOUN_CATEGORIES),
                        )
                    if intent == "places":
                        return q.filter(Symbol.category.in_(PLACE_CATEGORIES))
                    return q

                def format_results(rows, *, offset, limit):
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
                    # Paginate AFTER the language-rank sort: applying SQL OFFSET
                    # to the unsorted rows first would skip or repeat entries
                    # across pages because the rank ordering is computed in
                    # Python, not by the database.
                    return suggestions[offset : offset + limit]

                strict_passes = [True, False]
                # A board-scoped intent must never silently fall back to the
                # global symbol catalog: that is how unrelated suggestions
                # escaped into Learning when a board lacked that category.
                board_scopes = [request.board_id is not None]
                for strict in strict_passes:
                    for board_scoped in board_scopes:
                        query = build_query(board_scoped)
                        query = apply_language_filter(query, strict)
                        query = apply_intent_filter(query)
                        # Fetch a bounded window, then sort and paginate in
                        # Python so pages follow the language-rank ordering.
                        results = query.limit(500).all()
                        suggestions = format_results(results, offset=offset, limit=limit)
                        if suggestions:
                            return suggestions
            except Exception as db_err:
                logger.error(f"Database error in intent query: {db_err}")
                # Fall back to general suggestion only when no board context
                # was requested. A scoped request must not leak global items.
                if request.board_id is not None:
                    return []

            if request.board_id is not None:
                return []

        # Get unified suggestions from PredictionService. When a topic is set
        # and no catalog symbols match it, an LLM-generated word list expands
        # the vocabulary so learners are never limited by the symbol database.
        #
        # Layered content safety: resolve the student's effective policy once,
        # drop a blocked/custom-locked topic (friendly silent fallback for
        # prediction — the chat/topic surfaces surface explicit redirects),
        # and hand the policy to predict_next so topic words and pictogram
        # generation are gated too.
        from src.aac_app.services.content_safety import (
            check_text,
            log_event,
            resolve_policy_for_user,
        )

        content_policy = resolve_policy_for_user(current_user.id, db)
        effective_topic = request.topic
        if effective_topic and effective_topic.strip():
            if content_policy.feature_blocked("block_custom_topics"):
                log_event(
                    user_id=current_user.id,
                    surface="topic",
                    direction="input",
                    verdict="blocked",
                    detail=(
                        f"feature_lock: block_custom_topics; topic: {effective_topic[:120]}"
                    ),
                    db=db,
                )
                effective_topic = ""
            else:
                topic_verdict = check_text(content_policy, effective_topic)
                if topic_verdict.blocked:
                    log_event(
                        user_id=current_user.id,
                        surface="topic",
                        direction="input",
                        verdict="redirected",
                        matched=list(topic_verdict.matched_terms),
                        detail=effective_topic[:300],
                        db=db,
                    )
                    effective_topic = ""

        topic_word_fetcher = None
        if effective_topic and effective_topic.strip():
            topic_word_fetcher = _build_topic_word_fetcher()

        final_suggestions = prediction_service.predict_next(
            user_id=current_user.id,
            current_symbols=symbols_list,
            limit=limit,
            language=user_lang,
            offset=offset,
            board_id=request.board_id,
            topic=effective_topic,
            db=db,
            topic_word_fetcher=topic_word_fetcher,
            content_policy=content_policy,
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
