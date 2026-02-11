import os
import sys
from unittest.mock import MagicMock

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.aac_app.models.database import BoardSymbol, CommunicationBoard, Symbol  # noqa: E402
from src.api.routers.boards import serialize_board  # noqa: E402


def test_translation_logic():
    print("Setting up test data...")

    # Mock Symbol
    symbol = MagicMock(spec=Symbol)
    symbol.id = 1
    symbol.label = "Apple"
    symbol.description = "A red fruit"
    symbol.category = "food"
    symbol.image_path = "/path/to/apple.png"
    symbol.audio_path = None
    symbol.keywords = "apple, fruit"
    symbol.language = "en"
    symbol.is_builtin = True
    symbol.created_at = "2023-01-01"

    # Mock BoardSymbol
    board_symbol = MagicMock(spec=BoardSymbol)
    board_symbol.id = 101
    board_symbol.symbol_id = 1
    board_symbol.position_x = 0
    board_symbol.position_y = 0
    board_symbol.size = 1
    board_symbol.is_visible = True
    board_symbol.custom_text = "Delicious Apple"  # Custom text to override label
    board_symbol.color = "red"
    board_symbol.linked_board_id = None
    board_symbol.symbol = symbol

    # Mock Board
    board = MagicMock(spec=CommunicationBoard)
    board.id = 1001
    board.user_id = 1
    board.name = "Food Board"
    board.description = "Board about food"
    board.category = "general"
    board.is_public = True
    board.is_template = False
    board.created_at = "2023-01-01"
    board.updated_at = "2023-01-01"
    board.grid_rows = 4
    board.grid_cols = 5
    board.ai_enabled = False
    board.ai_provider = None
    board.ai_model = None
    board.locale = "en"
    board.is_language_learning = False
    board.symbols = [board_symbol]

    print("\n--- Test Case 1: Translation Enabled (Normal Board) ---")
    # Target language Spanish, Board is NOT language learning
    # We expect translation of "Delicious Apple" to Spanish (e.g., "Manzana deliciosa")

    print("Calling serialize_board with target_lang='es'...")
    result = serialize_board(board, target_lang="es")

    serialized_symbol = result["symbols"][0]
    print("Original Custom Text: 'Delicious Apple'")
    print(f"Translated Custom Text: '{serialized_symbol['custom_text']}'")
    print("Original Label: 'Apple'")
    print(f"Translated Label: '{serialized_symbol['symbol']['label']}'")

    # Verify translation occurred (rough check)
    if (
        "anzana" in serialized_symbol["custom_text"]
        or "eliciosa" in serialized_symbol["custom_text"]
    ):
        print("SUCCESS: Custom text was translated.")
    else:
        print(
            "WARNING: Custom text might not have been translated correctly (or translation API failed/returned same text)."
        )

    print("\n--- Test Case 2: Translation Disabled (Language Learning Board) ---")
    # Set board to Language Learning
    board.is_language_learning = True
    # Update mock to reflect the change if getattr is used
    # Note: MagicMock attributes are dynamic, so setting it on the object works if getattr accesses the attribute
    # But if the function uses getattr(b, 'is_language_learning', False), it should work.

    print(
        "Calling serialize_board with target_lang='es' (Board is Language Learning)..."
    )
    result_learning = serialize_board(board, target_lang="es")

    serialized_symbol_learning = result_learning["symbols"][0]
    print(f"Result Custom Text: '{serialized_symbol_learning['custom_text']}'")

    if serialized_symbol_learning["custom_text"] == "Delicious Apple":
        print("SUCCESS: Text was NOT translated (preserved original).")
    else:
        print(
            f"FAILURE: Text WAS translated: {serialized_symbol_learning['custom_text']}"
        )

    print("\n--- Test Case 3: No Target Language ---")
    board.is_language_learning = False
    print("Calling serialize_board with target_lang=None...")
    result_none = serialize_board(board, target_lang=None)

    if result_none["symbols"][0]["custom_text"] == "Delicious Apple":
        print("SUCCESS: Text was NOT translated.")
    else:
        print("FAILURE: Text WAS translated unexpectedly.")


if __name__ == "__main__":
    test_translation_logic()
