from functools import lru_cache

from loguru import logger

from src.aac_app.models import BoardSymbol, CommunicationBoard

_GoogleTranslator = None
_translation_import_attempted = False
_translation_dependency_warning_emitted = False


def _load_translation_dependency():
    """Import the translator lazily only when a translated board is requested."""
    global _GoogleTranslator, _translation_import_attempted
    if _translation_import_attempted:
        return _GoogleTranslator
    _translation_import_attempted = True
    try:
        from deep_translator import GoogleTranslator

        _GoogleTranslator = GoogleTranslator
    except Exception:  # pragma: no cover - keep board loads resilient
        _GoogleTranslator = None
    return _GoogleTranslator


@lru_cache(maxsize=16)
def _build_symbol_translator(target_lang: str):
    translator_class = _load_translation_dependency()
    if translator_class is None:
        return None
    return translator_class(source="auto", target=target_lang)


def _translate_symbol_text(text: str | None, target_lang: str | None) -> str | None:
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


def serialize_symbol(
    bs: BoardSymbol, target_lang: str = None, is_language_learning: bool = False
):
    sym = getattr(bs, "symbol", None)

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
    """Count visible symbols that have custom text or a symbol label."""
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
