import json
import os
from typing import Dict, List, Optional, Sequence, Tuple
from loguru import logger
from sqlalchemy.orm import Session
from ..services.symbol_analytics import SymbolAnalytics
from ..models.database import BoardSymbol, Symbol, SymbolUsageLog, get_session

# Import NLTK
try:
    import nltk
    from nltk.corpus import brown
    from nltk import ConditionalFreqDist
    HAS_NLTK = True
except ImportError:
    HAS_NLTK = False
    logger.warning("NLTK library not found, falling back to internal N-grams")

class PredictionService:
    """
    Lightweight, multilanguage next-word prediction engine.
    Combines user usage history (statistical) with NLTK (or internal N-grams).
    Replaces heavy LLM calls for symbol suggestion.
    """
    
    _instance = None
    _models: Dict[str, Dict] = {}
    _nltk_cfd = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(PredictionService, cls).__new__(cls)
            cls._instance.analytics_service = SymbolAnalytics()
            if HAS_NLTK:
                try:
                    # Download brown corpus if needed (quietly)
                    try:
                        nltk.data.find('corpora/brown')
                    except LookupError:
                        logger.info("Downloading NLTK brown corpus...")
                        nltk.download('brown', quiet=True)
                    
                    # Build simple Bigram model
                    logger.info("Building NLTK Bigram model...")
                    words = brown.words()
                    # Filter for alpha only to reduce noise
                    words = [w.lower() for w in words if w.isalpha()]
                    bigrams = nltk.bigrams(words)
                    cls._instance._nltk_cfd = ConditionalFreqDist(bigrams)
                    logger.info("NLTK model ready")
                except Exception as e:
                     logger.error(f"Failed to init NLTK model: {e}")
                     cls._instance._nltk_cfd = None
        return cls._instance

    def _load_model(self, language_code: str) -> Dict:
        """Load static N-gram model for the given language."""
        # Normalize language code (e.g. 'es-ES' -> 'es')
        lang = language_code.split('-')[0].lower()
        
        if lang in self._models:
            return self._models[lang]
            
        try:
            # Use frozen-aware path from config
            from src import config
            ngrams_dir = config.get_ngrams_path()
            file_path = ngrams_dir / f"{lang}.json"
            
            if file_path.exists():
                with open(file_path, 'r', encoding='utf-8') as f:
                    self._models[lang] = json.load(f)
                logger.info(f"Loaded N-gram model for language: {lang} from {file_path}")
            else:
                logger.warning(f"No N-gram model found for language: {lang} at {file_path}, using empty model")
                self._models[lang] = {"bigrams": {}}
                
        except Exception as e:
            logger.error(f"Failed to load N-gram model for {lang}: {e}")
            self._models[lang] = {"bigrams": {}}
            
        return self._models[lang]

    def predict_next(
        self, 
        user_id: int, 
        current_symbols: List[Dict], 
        limit: int = 5, 
        language: str = "en",
        offset: int = 0,
        board_id: Optional[int] = None,
        db: Optional[Session] = None,
    ) -> List[Dict]:
        """
        Predict next symbols.
        
        Args:
            user_id: User ID
            current_symbols: List of symbols in current utterance
            limit: Max suggestions to return
            language: Language code (e.g., 'en', 'es-ES')
            offset: Pagination offset
            
        Returns:
            List of suggested symbol dicts
        """
        suggestions: List[Dict] = []
        seen_labels = set()

        punctuation: List[str] = [".", ",", "?", "!"]
        reserved_punct = len(punctuation) if offset == 0 else 0
        base_limit = max(0, limit - reserved_punct)

        lang = (language or "en").split("-")[0].lower()
        preferred_langs = [lang]
        if lang != "en":
            preferred_langs.append("en")

        allowed_symbol_ids: Optional[set[int]] = None
        if board_id is not None:
            try:
                if db is not None:
                    ids = (
                        db.query(BoardSymbol.symbol_id)
                        .filter(
                            BoardSymbol.board_id == board_id,
                            BoardSymbol.is_visible == True,  # noqa: E712
                            BoardSymbol.symbol_id.isnot(None),
                        )
                        .all()
                    )
                    allowed_symbol_ids = {sid for (sid,) in ids if sid is not None}
                else:
                    with get_session() as session:
                        ids = (
                            session.query(BoardSymbol.symbol_id)
                            .filter(
                                BoardSymbol.board_id == board_id,
                                BoardSymbol.is_visible == True,  # noqa: E712
                                BoardSymbol.symbol_id.isnot(None),
                            )
                            .all()
                        )
                        allowed_symbol_ids = {sid for (sid,) in ids if sid is not None}
            except Exception as e:
                logger.warning(f"Failed to resolve board symbols for board_id={board_id}: {e}")
                allowed_symbol_ids = None

        def normalize_label(label: str) -> str:
            return (label or "").strip().lower()

        def add_symbol(
            *,
            symbol_id: int,
            label: str,
            category: Optional[str],
            image_path: Optional[str],
            confidence: float,
            source: str,
        ) -> None:
            if len(suggestions) >= base_limit:
                return
            if allowed_symbol_ids is not None and symbol_id > 0 and symbol_id not in allowed_symbol_ids:
                return
            nl = normalize_label(label)
            if not nl or nl in seen_labels:
                return
            suggestions.append(
                {
                    "symbol_id": symbol_id,
                    "label": label,
                    "category": category,
                    "image_path": image_path,
                    "confidence": confidence,
                    "source": source,
                }
            )
            seen_labels.add(nl)

        def resolve_symbols_by_labels(
            labels: Sequence[str],
            *,
            prefer_language: Sequence[str],
        ) -> List[Tuple[Symbol, str]]:
            wanted = [normalize_label(l) for l in labels if normalize_label(l)]
            if not wanted:
                return []

            # Small enough library: load once and match in memory to avoid
            # per-label query overhead and case issues.
            if db is not None:
                rows = db.query(Symbol).filter(Symbol.label.isnot(None)).all()
            else:
                with get_session() as session:
                    rows = session.query(Symbol).filter(Symbol.label.isnot(None)).all()

            buckets: Dict[str, List[Symbol]] = {}
            for sym in rows:
                key = normalize_label(sym.label)
                if not key:
                    continue
                buckets.setdefault(key, []).append(sym)

            def lang_rank(sym: Symbol) -> int:
                s_lang = (getattr(sym, "language", None) or "").split("-")[0].lower()
                try:
                    return prefer_language.index(s_lang)
                except ValueError:
                    return len(prefer_language) + 1

            resolved: List[Tuple[Symbol, str]] = []
            for w in wanted:
                options = buckets.get(w, [])
                if not options:
                    continue
                if allowed_symbol_ids is not None:
                    options = [o for o in options if o.id in allowed_symbol_ids]
                    if not options:
                        continue
                best = sorted(options, key=lang_rank)[0]
                resolved.append((best, w))
            return resolved

        def standard_library_labels(lang_code: str) -> List[str]:
            if lang_code == "es":
                return [
                    # pronouns/core
                    "yo",
                    "tú",
                    "tu",
                    "me",
                    "mi",
                    "nosotros",
                    "nosotras",
                    "ellos",
                    "ellas",
                    # common verbs
                    "quiero",
                    "ir",
                    "ayudar",
                    "parar",
                    "comer",
                    "beber",
                    "jugar",
                    "ver",
                    "tener",
                    # function words
                    "por favor",
                    "más",
                    "no",
                    "sí",
                    "a",
                    "el",
                    "la",
                    "un",
                    "una",
                ]

            return [
                # pronouns/core
                "I",
                "you",
                "he",
                "she",
                "it",
                "we",
                "they",
                "me",
                "my",
                "your",
                # common verbs
                "want",
                "go",
                "like",
                "help",
                "stop",
                "eat",
                "drink",
                "play",
                "see",
                "have",
                # function words
                "please",
                "more",
                "no",
                "yes",
                "the",
                "a",
                "an",
                "to",
                "in",
                "on",
            ]
        
        # 1. Get personalized suggestions from user history (SymbolAnalytics)
        # This uses the user's past patterns
        history_suggestions = self.analytics_service.suggest_next_symbol(
            user_id=user_id,
            symbols=current_symbols,
            limit=max(base_limit, 5),
        )

        for s in history_suggestions:
            add_symbol(
                symbol_id=s.get("symbol_id"),
                label=s.get("label"),
                category=s.get("category"),
                image_path=s.get("image_path"),
                confidence=float(s.get("confidence", 0.5)),
                source="history",
            )
            
        # 2. Get general suggestions from NLTK library (English only currently)
        # or static N-gram model
        
        # Prepare text for prediction
        last_word = current_symbols[-1].get("label", "").lower() if current_symbols else ""
        
        # Try library first if available and language is English
        # (Assuming library is optimized for English)
        lib_suggestions = []
        logger.info(
            f"Checking NLTK: has_model={self._nltk_cfd is not None}, lang={language}, last_word={last_word}"
        )
        
        if self._nltk_cfd and language.startswith("en") and last_word:
             try:
                 # Get most frequent next words from CFD
                 if last_word in self._nltk_cfd:
                     # Get top 5 most common next words
                     top_next = self._nltk_cfd[last_word].most_common(5)
                     logger.info(f"NLTK suggestions for '{last_word}': {top_next}")
                     for word, count in top_next:
                         # Normalize score roughly (count is raw frequency)
                         # We just set a fixed confidence for library suggestions
                         lib_suggestions.append((word, 0.5))
                 else:
                     logger.info(f"Word '{last_word}' not in NLTK model")
             except Exception as e:
                 logger.warning(f"NLTK prediction failed: {e}")
        
        # If library gave results, use them
        if lib_suggestions and len(suggestions) < base_limit:
            if db is not None:
                for word, score in lib_suggestions:
                    if len(suggestions) >= base_limit:
                        break
                    if normalize_label(word) in seen_labels:
                        continue
                    query = db.query(Symbol).filter(Symbol.label.ilike(word))
                    if allowed_symbol_ids is not None:
                        query = query.filter(Symbol.id.in_(allowed_symbol_ids))
                    symbol_obj = query.first()
                    if symbol_obj:
                        add_symbol(
                            symbol_id=symbol_obj.id,
                            label=symbol_obj.label,
                            category=symbol_obj.category,
                            image_path=symbol_obj.image_path,
                            confidence=float(score),
                            source="nwp_lib",
                        )
            else:
                with get_session() as session:
                    for word, score in lib_suggestions:
                        if len(suggestions) >= base_limit:
                            break
                        if normalize_label(word) in seen_labels:
                            continue
                        query = session.query(Symbol).filter(Symbol.label.ilike(word))
                        if allowed_symbol_ids is not None:
                            query = query.filter(Symbol.id.in_(allowed_symbol_ids))
                        symbol_obj = query.first()
                        if symbol_obj:
                            add_symbol(
                                symbol_id=symbol_obj.id,
                                label=symbol_obj.label,
                                category=symbol_obj.category,
                                image_path=symbol_obj.image_path,
                                confidence=float(score),
                                source="nwp_lib",
                            )

        # 3. Fallback to static N-gram model (JSON) if still needed
        # (Especially for non-English or if library failed/returned nothing)
        if len(suggestions) < base_limit and current_symbols:
            model = self._load_model(language)
            bigrams = model.get("bigrams", {})
            
            # Increase limit for more diversity if we have space
            # We want to fill the bar
            target_count = base_limit

            last_symbol_label = current_symbols[-1].get("label", "").lower() if current_symbols else ""
            if last_symbol_label and last_symbol_label in bigrams:
                next_word_probs = bigrams[last_symbol_label]
                sorted_words = sorted(next_word_probs.items(), key=lambda x: x[1], reverse=True)
                if db is not None:
                    for word, score in sorted_words:
                        if len(suggestions) >= target_count:
                            break
                        if normalize_label(word) in seen_labels:
                            continue
                        query = db.query(Symbol).filter(Symbol.label.ilike(word))
                        if allowed_symbol_ids is not None:
                            query = query.filter(Symbol.id.in_(allowed_symbol_ids))
                        symbol_obj = query.first()
                        if symbol_obj:
                            add_symbol(
                                symbol_id=symbol_obj.id,
                                label=symbol_obj.label,
                                category=symbol_obj.category,
                                image_path=symbol_obj.image_path,
                                confidence=0.4,
                                source="general_model",
                            )
                else:
                    with get_session() as session:
                        for word, score in sorted_words:
                            if len(suggestions) >= target_count:
                                break
                            if normalize_label(word) in seen_labels:
                                continue
                            query = session.query(Symbol).filter(Symbol.label.ilike(word))
                            if allowed_symbol_ids is not None:
                                query = query.filter(Symbol.id.in_(allowed_symbol_ids))
                            symbol_obj = query.first()
                            if symbol_obj:
                                add_symbol(
                                    symbol_id=symbol_obj.id,
                                    label=symbol_obj.label,
                                    category=symbol_obj.category,
                                    image_path=symbol_obj.image_path,
                                    confidence=0.4,
                                    source="general_model",
                                )
        
        # 4. Fill remaining slots with most popular symbols if needed (fallback)
        # PRIORITIZE NOUNS/OBJECTS here if we are low on suggestions
        if len(suggestions) < base_limit:
            # If we still don't have enough, fill with most frequent global symbols
            # We call suggest_next_symbol with empty list to get global top used
            try:
                fallback_suggestions = self.analytics_service.suggest_next_symbol(
                    user_id=user_id, 
                    symbols=[], 
                    limit=max(base_limit * 2, 10) # Request more to filter
                )

                # If analytics has no usage data yet, fall back to standard-library
                # symbols but keep the `fallback` source so tier-4 behavior is explicit.
                if not fallback_suggestions:
                    resolved = resolve_symbols_by_labels(
                        standard_library_labels(lang), prefer_language=preferred_langs
                    )
                    fallback_suggestions = [
                        {
                            "symbol_id": sym.id,
                            "label": sym.label,
                            "category": sym.category,
                            "image_path": sym.image_path,
                        }
                        for sym, _ in resolved[: max(base_limit * 2, 10)]
                    ]
                
                # Split fallbacks into nouns and others to mix them
                noun_candidates = []
                other_candidates = []
                
                noun_keywords = ["food", "drink", "toy", "animal", "place", "object", "noun"]
                
                for s in fallback_suggestions:
                    cat = (s.get('category') or '').lower()
                    if any(k in cat for k in noun_keywords):
                        noun_candidates.append(s)
                    else:
                        other_candidates.append(s)
                
                # Interleave or prioritize nouns if we have few
                # Simple strategy: add a noun, then an other, etc.
                
                while len(suggestions) < base_limit and (noun_candidates or other_candidates):
                    # Try to add a noun
                    if noun_candidates:
                        s = noun_candidates.pop(0)
                        add_symbol(
                            symbol_id=s.get("symbol_id"),
                            label=s.get("label"),
                            category=s.get("category"),
                            image_path=s.get("image_path"),
                            confidence=0.15,
                            source="fallback",
                        )
                            
                    if len(suggestions) >= base_limit:
                        break
                    
                    # Try to add another
                    if other_candidates:
                        s = other_candidates.pop(0)
                        add_symbol(
                            symbol_id=s.get("symbol_id"),
                            label=s.get("label"),
                            category=s.get("category"),
                            image_path=s.get("image_path"),
                            confidence=0.1,
                            source="fallback",
                        )
                         
            except Exception as e:
                logger.error(f"Fallback prediction failed: {e}")

        # 5. Cold start: if still low, use standard-library labels from DB
        if len(suggestions) < base_limit:
            resolved = resolve_symbols_by_labels(
                standard_library_labels(lang), prefer_language=preferred_langs
            )
            for sym, _ in resolved:
                add_symbol(
                    symbol_id=sym.id,
                    label=sym.label,
                    category=sym.category,
                    image_path=sym.image_path,
                    confidence=0.25,
                    source="standard_library",
                )

        # 5b. If board-scoped and still low, fill from board library.
        # Prefer the user's most-used symbols on that board; then fall back to globally popular
        # symbols on that board; finally fall back to board layout order.
        if allowed_symbol_ids is not None and len(suggestions) < base_limit:
            try:
                from sqlalchemy import desc, func

                def fill_board_library(session: Session) -> None:
                    # User-personal, restricted to the board
                    personal = (
                        session.query(
                            Symbol.id,
                            Symbol.label,
                            Symbol.category,
                            Symbol.image_path,
                            func.count(SymbolUsageLog.id).label("cnt"),
                        )
                        .join(SymbolUsageLog, SymbolUsageLog.symbol_id == Symbol.id)
                        .filter(
                            SymbolUsageLog.user_id == user_id,
                            Symbol.id.in_(allowed_symbol_ids),
                        )
                        .group_by(Symbol.id, Symbol.label, Symbol.category, Symbol.image_path)
                        .order_by(desc("cnt"))
                        .limit(max(base_limit * 2, 10))
                        .all()
                    )

                    for sid, label, cat, img, cnt in personal:
                        add_symbol(
                            symbol_id=sid,
                            label=label,
                            category=cat,
                            image_path=img,
                            confidence=0.35,
                            source="board_personal",
                        )

                    # Global popularity, restricted to the board
                    if len(suggestions) < base_limit:
                        popular = (
                            session.query(
                                Symbol.id,
                                Symbol.label,
                                Symbol.category,
                                Symbol.image_path,
                                func.count(SymbolUsageLog.id).label("cnt"),
                            )
                            .join(SymbolUsageLog, SymbolUsageLog.symbol_id == Symbol.id)
                            .filter(Symbol.id.in_(allowed_symbol_ids))
                            .group_by(
                                Symbol.id, Symbol.label, Symbol.category, Symbol.image_path
                            )
                            .order_by(desc("cnt"))
                            .limit(max(base_limit * 2, 10))
                            .all()
                        )

                        for sid, label, cat, img, cnt in popular:
                            add_symbol(
                                symbol_id=sid,
                                label=label,
                                category=cat,
                                image_path=img,
                                confidence=0.22,
                                source="board_popular",
                            )

                    # Layout order fallback (top-left to bottom-right), unique by symbol_id
                    if len(suggestions) < base_limit and board_id is not None:
                        placed = (
                            session.query(
                                BoardSymbol.symbol_id,
                                Symbol.label,
                                Symbol.category,
                                Symbol.image_path,
                                BoardSymbol.position_y,
                                BoardSymbol.position_x,
                            )
                            .join(Symbol, Symbol.id == BoardSymbol.symbol_id)
                            .filter(
                                BoardSymbol.board_id == board_id,
                                BoardSymbol.is_visible == True,  # noqa: E712
                                BoardSymbol.symbol_id.isnot(None),
                            )
                            .order_by(BoardSymbol.position_y, BoardSymbol.position_x)
                            .all()
                        )

                        seen_ids = set()
                        for sid, label, cat, img, _, _ in placed:
                            if sid in seen_ids:
                                continue
                            seen_ids.add(sid)
                            add_symbol(
                                symbol_id=sid,
                                label=label,
                                category=cat,
                                image_path=img,
                                confidence=0.18,
                                source="board_layout",
                            )

                if db is not None:
                    fill_board_library(db)
                else:
                    with get_session() as session:
                        fill_board_library(session)
            except Exception as e:
                logger.warning(f"Board library fallback failed (board_id={board_id}): {e}")

        # 6. Punctuation (only if it fits, never the only thing we return unless limit is tiny)
        if offset == 0:
            for p in punctuation:
                if len(suggestions) >= limit:
                    break
                if normalize_label(p) in seen_labels:
                    continue
                fake_id = -(abs(hash(p)) % 1000000)
                suggestions.append(
                    {
                        "symbol_id": fake_id,
                        "label": p,
                        "category": "punctuation",
                        "image_path": None,
                        "confidence": 1.0,
                        "source": "punctuation",
                    }
                )
                seen_labels.add(normalize_label(p))

        return suggestions[:limit]

# Global instance
prediction_service = PredictionService()
