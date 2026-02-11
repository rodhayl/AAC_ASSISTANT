import sys
import os
from unittest.mock import MagicMock

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Mocking the models since we don't need a real DB for this logic test
class MockSymbol:
    def __init__(self, label=None):
        self.label = label

class MockBoardSymbol:
    def __init__(self, is_visible=True, custom_text=None, symbol=None):
        self.is_visible = is_visible
        self.custom_text = custom_text
        self.symbol = symbol

class MockBoard:
    def __init__(self, symbols=None):
        self.symbols = symbols or []

# Import the function to test
# We might need to mock the broader module if it has side effects on import
from src.api.routers.boards import get_playable_count

def test_get_playable_count():
    print("Running test_get_playable_count...")
    
    # Test case 1: Empty board
    board1 = MockBoard(symbols=[])
    assert get_playable_count(board1) == 0
    print("Pass: Empty board returns 0")

    # Test case 2: Visible symbol with custom_text
    s2 = MockBoardSymbol(is_visible=True, custom_text="Hello")
    board2 = MockBoard(symbols=[s2])
    assert get_playable_count(board2) == 1
    print("Pass: Visible symbol with custom_text returns 1")

    # Test case 3: Visible symbol with symbol.label (no custom_text)
    s3 = MockBoardSymbol(is_visible=True, custom_text=None, symbol=MockSymbol(label="Dog"))
    board3 = MockBoard(symbols=[s3])
    assert get_playable_count(board3) == 1
    print("Pass: Visible symbol with label returns 1")

    # Test case 4: Invisible symbol with text (should not count)
    s4 = MockBoardSymbol(is_visible=False, custom_text="Hello")
    board4 = MockBoard(symbols=[s4])
    assert get_playable_count(board4) == 0
    print("Pass: Invisible symbol returns 0")

    # Test case 5: Visible symbol with NO text (should not count)
    s5 = MockBoardSymbol(is_visible=True, custom_text=None, symbol=MockSymbol(label=None))
    board5 = MockBoard(symbols=[s5])
    assert get_playable_count(board5) == 0
    print("Pass: Visible symbol WITHOUT text returns 0")

    # Test case 6: Mix of symbols
    s6_1 = MockBoardSymbol(is_visible=True, custom_text="One")     # Count
    s6_2 = MockBoardSymbol(is_visible=True, custom_text=None)      # No count (no symbol either)
    s6_3 = MockBoardSymbol(is_visible=False, custom_text="Two")    # No count
    s6_4 = MockBoardSymbol(is_visible=True, symbol=MockSymbol("Three")) # Count
    board6 = MockBoard(symbols=[s6_1, s6_2, s6_3, s6_4])
    assert get_playable_count(board6) == 2
    print("Pass: Mix of symbols returns correct count (2)")

    print("All backend logic tests passed!")

if __name__ == "__main__":
    try:
        test_get_playable_count()
    except AssertionError as e:
        print(f"Test FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
