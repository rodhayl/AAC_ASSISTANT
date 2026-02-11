# Scenario 06: Student - Communication Board Usage Flow

## Title
Student Communication Board Usage Flow - Navigate Boards, Select Symbols, Build Messages

## Description
This end-to-end test scenario validates the complete communication board usage workflow for students. It covers viewing available boards, opening a board, selecting symbols, building messages, and using the communication strip. All interactions are performed through the GUI using Chrome DevTools Protocol (CDP) commands.

## Prerequisites
- Application running at `http://localhost:8086`
- Student user credentials available (set via environment variables `AAC_STUDENT_USERNAME` and `AAC_STUDENT_PASSWORD`)
- Chrome browser with remote debugging enabled on port 9222
- At least one communication board exists and is assigned to the student

## Test Steps

### Step 1: Initialize CDP Connection and Login as Student
```python
# Connect to Chrome DevTools Protocol
target = get_first_page_target()
async with CDP(target.ws_url) as cdp:
    await cdp.enable()
    await cdp.clear_origin_data("http://localhost:8086")
    
    # Navigate to login page
    await cdp.goto("http://localhost:8086/login")
    await cdp.wait_for_selector("#username", timeout_s=15)
    
    # Enter student credentials
    await cdp.set_value("#username", student_username)
    await cdp.set_value("#password", student_password)
    
    # Click login button (supports both English and Spanish)
    await cdp.click_text(r"(Iniciar sesi|Login)", tag="button")
    
    # Verify successful login - should be on dashboard
    await cdp.wait_for_js("document.body && document.body.innerText.length > 0", timeout_s=10)
    current_path = await cdp.eval("location.pathname", await_promise=False)
    assert current_path == "/", f"Expected to be on dashboard, got {current_path}"
```

**Expected Result:** Student is successfully logged in and redirected to dashboard (`/`).

**Bug Detection Points:**
- Login button not found or not clickable
- Incorrect redirect after login
- Dashboard not loading properly

**Regression Notes:**
- Verify login flow works after authentication changes
- Check that role-based redirects are correct

---

### Step 2: Navigate to Communication Page
```python
# Navigate to communication page via sidebar or direct URL
await cdp.goto("http://localhost:8086/communication")
await cdp.wait_for_js("document.body && document.body.innerText.length > 0", timeout_s=10)

# Wait for loading spinner to disappear
await cdp.wait_for_js("!document.querySelector('.animate-spin')", timeout_s=20)

# Verify we're on the communication page
current_path = await cdp.eval("location.pathname", await_promise=False)
assert current_path == "/communication", f"Expected /communication, got {current_path}"

# Verify communication page heading is visible
communication_heading = await cdp.eval(
    """(() => {
        const headings = Array.from(document.querySelectorAll('h1, h2'));
        return headings.find(h => /communication boards|tableros de comunicaci/i.test(h.innerText));
    })()""",
    await_promise=False
)
assert communication_heading, "Communication page heading not found"
```

**Expected Result:** Communication page loads successfully with the heading visible.

**Bug Detection Points:**
- Page not loading or showing error
- Loading spinner stuck
- Communication heading missing

**Regression Notes:**
- Verify navigation after route changes
- Check that student can access communication page

---

### Step 3: View Available Boards
```python
# Get list of available boards
boards = await cdp.eval(
    """(() => {
        const boardCards = Array.from(document.querySelectorAll('.board-card, [data-testid*="board"]'));
        return boardCards.map(card => {
            const nameEl = card.querySelector('h3, h4, .board-name');
            const descEl = card.querySelector('.description, .board-description');
            const symbolCountEl = card.querySelector('.symbol-count, .symbols-count');
            return {
                name: nameEl ? nameEl.innerText.trim() : '',
                description: descEl ? descEl.innerText.trim() : '',
                symbol_count: symbolCountEl ? symbolCountEl.innerText.trim() : ''
            };
        });
    })()""",
    await_promise=False
)

print(f"Found {len(boards)} available boards:")
for board in boards:
    print(f"  - {board['name']}: {board['symbol_count']} symbols")

# Verify at least one board is available
assert len(boards) > 0, "No boards found on communication page"

# Store the first board's name for later use
target_board_name = boards[0]['name']
print(f"Target board for testing: {target_board_name}")
```

**Expected Result:** Available boards are displayed with names and symbol counts.

**Bug Detection Points:**
- Boards not loading from database
- Board cards not rendering
- Empty board list

**Regression Notes:**
- Verify assigned boards are displayed
- Check that board metadata is correct
- Verify unassigned boards are not visible

---

### Step 4: Open a Communication Board
```python
# Find and click on the target board
board_clicked = await cdp.eval(
    f"""(() => {{
        const cards = Array.from(document.querySelectorAll('.board-card, [data-testid*="board"]'));
        const card = cards.find(c => c.innerText.includes('{target_board_name}'));
        if (!card) return false;
        
        // Click on the board card
        card.click();
        return true;
    }})()""",
    await_promise=False
)
assert board_clicked, f"Could not click on board '{target_board_name}'"

# Wait for board to load
await cdp.wait_for_js("document.body && document.body.innerText.length > 0", timeout_s=10)
await cdp.wait_for_js("!document.querySelector('.animate-spin')", timeout_s=20)

# Verify we're on the board view page
current_path = await cdp.eval("location.pathname", await_promise=False)
assert "/boards/" in current_path, f"Expected to be on board view, got {current_path}"

# Verify board name is displayed
board_name_displayed = await cdp.eval(
    f"""(() => {{
        const text = document.body.innerText;
        return text.includes('{target_board_name}');
    }})()""",
    await_promise=False
)
assert board_name_displayed, f"Board name '{target_board_name}' not displayed on board view"

print(f"Opened communication board '{target_board_name}'")
```

**Expected Result:** Board opens successfully with the board name displayed.

**Bug Detection Points:**
- Board not opening
- Board view not loading correctly
- Board name not displayed

**Regression Notes:**
- Verify board loads with correct data
- Check that board symbols are visible
- Verify student has read access to board

---

### Step 5: View Board Symbols Grid
```python
# Get list of symbols on the board
symbols = await cdp.eval(
    """(() => {
        const symbolCells = Array.from(document.querySelectorAll('.symbol-cell, .board-symbol, [data-testid*="symbol"]'));
        return symbolCells.map(cell => {
            const labelEl = cell.querySelector('.label, .symbol-label');
            const imgEl = cell.querySelector('img');
            return {
                label: labelEl ? labelEl.innerText.trim() : '',
                has_image: imgEl !== null,
                position: cell.getAttribute('data-position') || ''
            };
        });
    })()""",
    await_promise=False
)

print(f"Found {len(symbols)} symbols on board:")
for symbol in symbols[:5]:  # Show first 5 symbols
    print(f"  - {symbol['label']} (image: {symbol['has_image']})")

# Verify at least some symbols are on the board
assert len(symbols) > 0, "No symbols found on board"
```

**Expected Result:** Board symbols are displayed in a grid layout.

**Bug Detection Points:**
- Symbols not loading from database
- Symbol grid not rendering
- Empty board

**Regression Notes:**
- Verify symbols are loaded correctly
- Check that symbol images are displayed
- Verify symbol positions are correct

---

### Step 6: Select a Symbol
```python
# Click on the first symbol
symbol_clicked = await cdp.eval(
    """(() => {
        const symbols = Array.from(document.querySelectorAll('.symbol-cell, .board-symbol, [data-testid*="symbol"]'));
        if (symbols.length === 0) return false;
        
        // Click on the first symbol
        symbols[0].click();
        return true;
    })()""",
    await_promise=False
)
assert symbol_clicked, "Could not click on symbol"

# Wait for symbol to be added to message strip
await cdp.wait_for_js(
    """(() => {
        const strip = document.querySelector('.message-strip, .symbol-strip, .communication-bar');
        return strip && strip.children.length > 0;
    })()""",
    timeout_s=5
)

print("Selected first symbol from board")
```

**Expected Result:** Symbol is clicked and added to the message strip.

**Bug Detection Points:**
- Symbols not clickable
- Message strip not updating
- Symbol not being added to message

**Regression Notes:**
- Verify symbol click handlers work correctly
- Check that message strip updates in real-time
- Verify symbol usage is logged

---

### Step 7: View Message Strip
```python
# Get symbols in the message strip
strip_symbols = await cdp.eval(
    """(() => {
        const strip = document.querySelector('.message-strip, .symbol-strip, .communication-bar');
        if (!strip) return [];
        
        const items = Array.from(strip.children);
        return items.map(item => {
            const labelEl = item.querySelector('.label, .symbol-label');
            const imgEl = item.querySelector('img');
            return {
                label: labelEl ? labelEl.innerText.trim() : '',
                has_image: imgEl !== null
            };
        });
    })()""",
    await_promise=False
)

print(f"Message strip contains {len(strip_symbols)} symbols:")
for symbol in strip_symbols:
    print(f"  - {symbol['label']}")

# Verify the selected symbol is in the strip
assert len(strip_symbols) > 0, "Message strip is empty after selecting symbol"
```

**Expected Result:** Message strip displays the selected symbol.

**Bug Detection Points:**
- Message strip not visible
- Selected symbol not appearing in strip
- Strip not updating correctly

**Regression Notes:**
- Verify message strip displays correctly
- Check that symbols can be removed from strip
- Verify strip persists across page navigation

---

### Step 8: Select Multiple Symbols to Build a Message
```python
# Select 3 more symbols to build a message
for i in range(3):
    symbol_clicked = await cdp.eval(
        f"""((index) => {{
            const symbols = Array.from(document.querySelectorAll('.symbol-cell, .board-symbol, [data-testid*="symbol"]'));
            // Select a different symbol each time
            const symbolIndex = (index + 1) % symbols.length;
            if (symbols[symbolIndex]) {{
                symbols[symbolIndex].click();
                return true;
            }}
            return false;
        }})({i})""",
        await_promise=False
    )
    
    if symbol_clicked:
        # Wait for symbol to be added to strip
        await cdp.wait_for_js(
            """(() => {
                const strip = document.querySelector('.message-strip, .symbol-strip, .communication-bar');
                return strip && strip.children.length > 0;
            })()""",
            timeout_s=3
        )
        print(f"Selected symbol {i+2}")
    else:
        print(f"Could not select symbol {i+2}")

# Get updated message strip
updated_strip_symbols = await cdp.eval(
    """(() => {
        const strip = document.querySelector('.message-strip, .symbol-strip, .communication-bar');
        if (!strip) return [];
        
        const items = Array.from(strip.children);
        return items.map(item => {
            const labelEl = item.querySelector('.label, .symbol-label');
            return labelEl ? labelEl.innerText.trim() : '';
        });
    })()""",
    await_promise=False
)

print(f"Message strip now contains {len(updated_strip_symbols)} symbols: {', '.join(updated_strip_symbols)}")
```

**Expected Result:** Multiple symbols are selected and appear in the message strip.

**Bug Detection Points:**
- Symbols not responding to clicks
- Message strip not updating with multiple selections
- Symbols not being added in order

**Regression Notes:**
- Verify multiple symbols can be selected
- Check that symbol order is maintained
- Verify message strip can handle many symbols

---

### Step 9: Clear the Message Strip
```python
# Look for a clear button on the message strip
clear_button_exists = await cdp.eval(
    """(() => {
        const strip = document.querySelector('.message-strip, .symbol-strip, .communication-bar');
        if (!strip) return false;
        
        const clearBtn = Array.from(strip.querySelectorAll('button')).find(b => 
            /clear|limpiar/i.test(b.innerText) ||
            b.getAttribute('aria-label')?.includes('clear')
        );
        return clearBtn !== null;
    })()""",
    await_promise=False
)

if clear_button_exists:
    # Click the clear button
    await cdp.click_text(r"clear|limpiar", tag="button")
    
    # Wait for strip to be cleared
    await cdp.wait_for_js(
        """(() => {
            const strip = document.querySelector('.message-strip, .symbol-strip, .communication-bar');
            return strip && strip.children.length === 0;
        })()""",
        timeout_s=5
    )
    
    print("Message strip cleared")
else:
    print("Clear button not found - may need different UI flow")
```

**Expected Result:** Message strip is cleared and all symbols are removed.

**Bug Detection Points:**
- Clear button not found
- Strip not clearing
- Symbols remaining after clear

**Regression Notes:**
- Verify clear button works correctly
- Check that all symbols are removed
- Verify clear action is logged

---

### Step 10: Build a New Message
```python
# Select symbols to build a simple message (e.g., "I want water")
message_symbols = ["I", "want", "water"]

for symbol_label in message_symbols:
    symbol_clicked = await cdp.eval(
        f"""((label) => {{
            const symbols = Array.from(document.querySelectorAll('.symbol-cell, .board-symbol, [data-testid*="symbol"]'));
            const symbol = symbols.find(s => s.innerText.includes(label));
            if (symbol) {{
                symbol.click();
                return true;
            }}
            return false;
        }})('{symbol_label}')""",
        await_promise=False
    )
    
    if symbol_clicked:
        # Wait for symbol to be added to strip
        await cdp.wait_for_js(
            """(() => {
                const strip = document.querySelector('.message-strip, .symbol-strip, .communication-bar');
                return strip && strip.children.length > 0;
            })()""",
            timeout_s=3
        )
        print(f"Added symbol '{symbol_label}' to message")
    else:
        print(f"Could not find symbol '{symbol_label}'")

# Get the built message
built_message = await cdp.eval(
    """(() => {
        const strip = document.querySelector('.message-strip, .symbol-strip, .communication-bar');
        if (!strip) return '';
        
        const items = Array.from(strip.children);
        return items.map(item => {
            const labelEl = item.querySelector('.label, .symbol-label');
            return labelEl ? labelEl.innerText.trim() : '';
        }).join(' ');
    })()""",
    await_promise=False
)

print(f"Built message: {built_message}")
```

**Expected Result:** A message is built by selecting multiple symbols.

**Bug Detection Points:**
- Symbols not found by label
- Message not building correctly
- Symbols not appearing in order

**Regression Notes:**
- Verify message building works correctly
- Check that symbol order is maintained
- Verify message can be spoken (if TTS is available)

---

### Step 11: Use Speak/Play Button (if available)
```python
# Look for a speak/play button on the message strip
speak_button_exists = await cdp.eval(
    """(() => {
        const strip = document.querySelector('.message-strip, .symbol-strip, .communication-bar');
        if (!strip) return false;
        
        const speakBtn = Array.from(strip.querySelectorAll('button')).find(b => 
            /speak|hablar|play|reproducir/i.test(b.innerText) ||
            b.getAttribute('aria-label')?.includes('speak')
        );
        return speakBtn !== null;
    })()""",
    await_promise=False
)

if speak_button_exists:
    # Click the speak button
    await cdp.click_text(r"speak|hablar|play|reproducir", tag="button")
    
    # Wait a moment for TTS to play
    await cdp.wait_for_js("true", timeout_s=2)
    
    print("Speak/play button clicked")
else:
    print("Speak/play button not found - TTS may not be available")
```

**Expected Result:** If available, the speak button plays the message using text-to-speech.

**Bug Detection Points:**
- Speak button not working
- TTS not playing
- Audio not outputting

**Regression Notes:**
- Verify TTS integration works correctly
- Check that audio plays without errors
- Verify TTS uses correct language

---

### Step 12: Navigate Back to Boards List
```python
# Navigate back to communication page
await cdp.goto("http://localhost:8086/communication")
await cdp.wait_for_js("!document.querySelector('.animate-spin')", timeout_s=20)

# Verify we're back on the communication page
current_path = await cdp.eval("location.pathname", await_promise=False)
assert current_path == "/communication", f"Expected /communication, got {current_path}"

# Verify the target board is still visible
board_still_visible = await cdp.eval(
    f"""(() => {{
        const text = document.body.innerText;
        return text.includes('{target_board_name}');
    }})()""",
    await_promise=False
)
assert board_still_visible, f"Board '{target_board_name}' not found after returning to list"
```

**Expected Result:** Communication page loads with the target board still visible.

**Bug Detection Points:**
- Navigation not working correctly
- Board list not refreshing

**Regression Notes:**
- Verify navigation works correctly
- Check that board list updates after usage

---

### Step 13: Try to Open a Different Board
```python
# Get list of boards again
boards_after = await cdp.eval(
    """(() => {
        const boardCards = Array.from(document.querySelectorAll('.board-card, [data-testid*="board"]'));
        return boardCards.map(card => {
            const nameEl = card.querySelector('h3, h4, .board-name');
            return nameEl ? nameEl.innerText.trim() : '';
        });
    })()""",
    await_promise=False
)

# If there's more than one board, try to open a different one
if len(boards_after) > 1:
    # Find a board that's not the one we just used
    other_board_name = next((b for b in boards_after if b != target_board_name), None)
    
    if other_board_name:
        board_clicked = await cdp.eval(
            f"""(() => {{
                const cards = Array.from(document.querySelectorAll('.board-card, [data-testid*="board"]'));
                const card = cards.find(c => c.innerText.includes('{other_board_name}'));
                if (!card) return false;
                card.click();
                return true;
            }})()""",
            await_promise=False
        )
        
        if board_clicked:
            # Wait for board to load
            await cdp.wait_for_js("document.body && document.body.innerText.length > 0", timeout_s=10)
            await cdp.wait_for_js("!document.querySelector('.animate-spin')", timeout_s=20)
            
            print(f"Opened different board '{other_board_name}'")
        else:
            print(f"Could not click on board '{other_board_name}'")
    else:
        print("No different board found to open")
else:
    print("Only one board available - skipping different board test")
```

**Expected Result:** If multiple boards exist, a different board can be opened.

**Bug Detection Points:**
- Board switching not working
- Previous board state persisting
- Board not loading correctly

**Regression Notes:**
- Verify board switching works correctly
- Check that message strip is cleared on board change
- Verify board state is isolated

---

### Step 14: Logout as Student
```python
# Navigate to dashboard
await cdp.goto("http://localhost:8086/")

# Click logout button
logout_clicked = await cdp.eval(
    """(() => {
        const buttons = Array.from(document.querySelectorAll('button, a'));
        const logoutBtn = buttons.find(b => /cerrar sesi|logout/i.test(b.innerText));
        if (logoutBtn) {
            logoutBtn.click();
            return true;
        }
        return false;
    })()""",
    await_promise=False
)
assert logout_clicked, "Logout button not found"

# Wait for redirect to login page
await cdp.wait_for_js("document.body && document.body.innerText.length > 0", timeout_s=10)

# Verify we're on login page
current_path = await cdp.eval("location.pathname", await_promise=False)
assert current_path == "/login", f"Expected to be on /login after logout, got {current_path}"
```

**Expected Result:** Student is successfully logged out and redirected to login page.

**Bug Detection Points:**
- Logout button not found
- Session not being cleared

**Regression Notes:**
- Verify session cleanup after logout
- Check that authentication tokens are cleared

---

## Cleanup Steps
No explicit cleanup needed as this is a read-only usage test. However:
- Verify no orphaned symbol usage logs remain
- Check that message strip state is cleared on logout

## Edge Cases to Consider
1. **Empty Board:** Student accessing a board with no symbols
2. **Large Board:** Board with hundreds of symbols
3. **No Boards Available:** Student with no assigned boards
4. **Long Message:** Building a message with many symbols
5. **Duplicate Symbols:** Selecting the same symbol multiple times
6. **Special Characters:** Symbols with special characters in labels
7. **Network Issues:** Testing behavior during slow network conditions
8. **TTS Unavailable:** Testing behavior when TTS is not configured

## Success Criteria
- Student can view available communication boards
- Student can open a communication board
- Student can view board symbols in a grid
- Student can select symbols by clicking
- Selected symbols appear in the message strip
- Student can build messages with multiple symbols
- Student can clear the message strip
- Student can use the speak/play button (if available)
- Student can switch between different boards
- All UI elements are responsive and accessible
- Proper error handling for missing data
- Session management works correctly (login/logout)

## Related Files
- `src/api/routers/boards.py` - Board management API endpoints
- `src/api/routers/collab.py` - Board collaboration endpoints
- `src/frontend/src/components/board/CommunicationBoard.tsx` - Communication board UI
- `src/frontend/src/components/board/CommunicationToolbar.tsx` - Communication toolbar UI
- `src/frontend/src/components/board/MessageStrip.tsx` - Message strip UI
- `scripts/cdp_harness.py` - CDP harness for automation
