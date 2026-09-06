from src.aac_app.models import BoardSymbol, CommunicationBoard
from src.aac_app.services.runtime_translation import translate_text as _translate_symbol_text

SUPPORTED_AI_PROVIDERS = ("ollama", "openrouter", "lmstudio", "groq")


def _serialize_symbol(
    bs: BoardSymbol,
    target_lang: str = None,
    is_language_learning: bool = False,
    *,
    export: bool = False,
) -> dict:
    """Serialize one placement for either the API or export contract."""
    sym = getattr(bs, "symbol", None)
    custom_text = bs.custom_text
    symbol_label = sym.label if sym else None

    if target_lang and not is_language_learning:
        custom_text = _translate_symbol_text(custom_text, target_lang)
        symbol_label = _translate_symbol_text(symbol_label, target_lang)

    symbol_data = None
    if sym is not None:
        symbol_data = {
            "id": sym.id,
            "label": symbol_label,
            "description": sym.description,
            "category": sym.category,
            "image_path": sym.image_path,
            "audio_path": sym.audio_path,
            "keywords": sym.keywords,
            "language": sym.language,
        }
        if not export:
            symbol_data.update(
                is_builtin=sym.is_builtin,
                created_at=sym.created_at,
            )

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
        "symbol": symbol_data,
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
            _serialize_symbol(bs, target_lang, is_learning) for bs in (b.symbols or [])
        ],
    }


def serialize_export_board(board: CommunicationBoard) -> dict:
    """Return the stable, minimal board shape used by data exports."""
    is_learning = getattr(board, "is_language_learning", False)
    return {
        "id": board.id,
        "name": board.name,
        "description": board.description,
        "category": board.category,
        "is_public": board.is_public,
        "is_template": board.is_template,
        "grid_rows": board.grid_rows,
        "grid_cols": board.grid_cols,
        "symbols": [
            _serialize_symbol(symbol, is_language_learning=is_learning, export=True)
            for symbol in (board.symbols or [])
        ],
        "created_at": board.created_at.isoformat() if board.created_at else None,
        "updated_at": board.updated_at.isoformat() if board.updated_at else None,
    }
