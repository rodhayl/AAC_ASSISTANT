# Scenario 03: Teacher - Board Creation & Sharing Flow

## Title
Teacher Board Creation & Sharing Flow - Create Board, Assign to Students, Verify Access

## Description
This end-to-end test scenario validates the complete board creation and sharing workflow for teachers. It covers creating a new communication board, adding symbols to the board, assigning the board to students, and verifying that students can access the assigned board. All interactions are performed through the GUI using Chrome DevTools Protocol (CDP) commands.

## Prerequisites
- Application running at `http://localhost:8086`
- Teacher user credentials available (set via environment variables `AAC_TEACHER_USERNAME` and `AAC_TEACHER_PASSWORD`)
- Student user credentials available (set via environment variables `AAC_STUDENT_USERNAME` and `AAC_STUDENT_PASSWORD`)
- Chrome browser with remote debugging enabled on port 9222
- At least one student exists in the system

## Test Steps

### Step 1: Initialize CDP Connection and Login as Teacher
```python
# Connect to Chrome DevTools Protocol
target = get_first_page_target()
async with CDP(target.ws_url) as cdp:
    await cdp.enable()
    await cdp.clear_origin_data("http://localhost:8086")
    
    # Navigate to login page
    await cdp.goto("http://localhost:8086/login")
    await cdp.wait_for_selector("#username", timeout_s=15)
    
    # Enter teacher credentials
    await cdp.set_value("#username", teacher_username)
    await cdp.set_value("#password", teacher_password)
    
    # Click login button (supports both English and Spanish)
    await cdp.click_text(r"(Iniciar sesi|Login)", tag="button")
    
    # Verify successful login - should be on dashboard
    await cdp.wait_for_js("document.body && document.body.innerText.length > 0", timeout_s=10)
    current_path = await cdp.eval("location.pathname", await_promise=False)
    assert current_path == "/", f"Expected to be on dashboard, got {current_path}"
```

**Expected Result:** Teacher is successfully logged in and redirected to the dashboard (`/`).

**Bug Detection Points:**
- Login button not found or not clickable
- Incorrect redirect after login
- Dashboard not loading properly

**Regression Notes:**
- Verify login flow works after authentication changes
- Check that role-based redirects are correct

---

### Step 2: Navigate to Boards Page
```python
# Navigate to boards page via sidebar or direct URL
await cdp.goto("http://localhost:8086/boards")
await cdp.wait_for_js("document.body && document.body.innerText.length > 0", timeout_s=10)

# Wait for loading spinner to disappear
await cdp.wait_for_js("!document.querySelector('.animate-spin')", timeout_s=20)

# Verify we're on the boards page
current_path = await cdp.eval("location.pathname", await_promise=False)
assert current_path == "/boards", f"Expected /boards, got {current_path}"

# Verify "New Board" button is visible
new_board_button_exists = await cdp.eval(
    """(() => {
        const btn = Array.from(document.querySelectorAll('button')).find(b => 
            /new board|nuevo|create board|crear/i.test(b.innerText)
        );
        return btn !== null;
    })()""",
    await_promise=False
)
assert new_board_button_exists, "New Board button not found"
```

**Expected Result:** Boards page loads successfully with "New Board" button visible.

**Bug Detection Points:**
- Page not loading or showing error
- Loading spinner stuck
- New Board button missing (permission issue)

**Regression Notes:**
- Verify navigation after route changes
- Check permission-based UI visibility

---

### Step 3: Create a New Communication Board
```python
# Generate unique board details
timestamp = await cdp.eval("Date.now()", await_promise=False)
board_name = f"Test Board {timestamp}"
board_description = f"Board created for E2E testing at {timestamp}"
board_category = "general"

# Click "New Board" button
await cdp.click_text(r"new board|nuevo|create board|crear", tag="button")

# Wait for modal to appear
await cdp.wait_for_selector('div[role="dialog"]', timeout_s=10)

# Fill in the board creation form
await cdp.set_value('input[name="name"]', board_name)
await cdp.set_value('textarea[name="description"], input[name="description"]', board_description)
await cdp.set_value('input[name="category"], select[name="category"]', board_category)

# Set grid dimensions
await cdp.set_value('input[name="grid_cols"]', "4")
await cdp.set_value('input[name="grid_rows"]', "4")

# Submit the form
await cdp.click_text(r"create|crear", tag="button")

# Wait for modal to close and list to refresh
await cdp.wait_for_js("!document.querySelector('div[role=\"dialog\"]')", timeout_s=15)
await cdp.wait_for_js("!document.querySelector('.animate-spin')", timeout_s=20)

# Verify the new board appears in the list
board_found = await cdp.eval(
    f"""(() => {{
        const text = document.body.innerText;
        return text.includes('{board_name}');
    }})()""",
    await_promise=False
)
assert board_found, f"Created board '{board_name}' not found in list"

# Store board ID for later use
board_id = await cdp.eval(
    f"""(() => {{
        const cards = Array.from(document.querySelectorAll('.relative, .board-card'));
        const card = cards.find(c => c.innerText.includes('{board_name}'));
        if (!card) return null;
        const link = card.querySelector('a[href*="/boards/"]');
        if (!link) return null;
        const href = link.getAttribute('href');
        return href ? href.split('/').pop() : null;
    }})()""",
    await_promise=False
)
assert board_id, "Could not extract board ID from board card"

print(f"Created board '{board_name}' with ID: {board_id}")
```

**Expected Result:** New communication board is created successfully and appears in the boards list.

**Bug Detection Points:**
- Modal not opening
- Form validation errors (empty name, invalid dimensions)
- Board not appearing in list after creation
- Board ID not extractable from card

**Regression Notes:**
- Verify form validation after schema changes
- Check that board is created with correct owner
- Verify list refresh after creation

---

### Step 4: Open Board Editor and Add Symbols
```python
# Navigate to the board editor
await cdp.goto(f"http://localhost:8086/boards/{board_id}")
await cdp.wait_for_js("document.body && document.body.innerText.length > 0", timeout_s=10)

# Wait for loading to complete
await cdp.wait_for_js("!document.querySelector('.animate-spin')", timeout_s=20)

# Verify we're on the board editor page
current_path = await cdp.eval("location.pathname", await_promise=False)
assert f"/boards/{board_id}" in current_path, f"Expected to be on board editor, got {current_path}"

# Look for "Add Symbol" button or similar
add_symbol_button_exists = await cdp.eval(
    """(() => {
        const btn = Array.from(document.querySelectorAll('button')).find(b => 
            /add symbol|aadir smbolo/i.test(b.innerText)
        );
        return btn !== null;
    })()""",
    await_promise=False
)

if add_symbol_button_exists:
    # Click "Add Symbol" button
    await cdp.click_text(r"add symbol|aadir smbolo", tag="button")
    
    # Wait for symbol selection modal
    await cdp.wait_for_selector('div[role="dialog"]', timeout_s=10)
    
    # Select a symbol from the library (first available symbol)
    symbol_selected = await cdp.eval(
        """(() => {
            const symbols = Array.from(document.querySelectorAll('.symbol-item, [data-testid*="symbol"]'));
            if (symbols.length === 0) return false;
            symbols[0].click();
            return true;
        })()""",
        await_promise=False
    )
    
    if symbol_selected:
        # Confirm symbol addition
        await cdp.click_text(r"add|aadir", tag="button")
        
        # Wait for modal to close
        await cdp.wait_for_js("!document.querySelector('div[role=\"dialog\"]')", timeout_s=15)
        
        print("Added symbol to board")
    else:
        print("No symbols available in library to add")
else:
    print("Add Symbol button not found - may need to use different UI flow")
```

**Expected Result:** Board editor opens and symbols can be added to the board.

**Bug Detection Points:**
- Board editor not loading
- Add Symbol button not found
- Symbol selection modal not opening
- Symbol not being added to board

**Regression Notes:**
- Verify board editor loads with correct board data
- Check that symbol library is accessible
- Verify symbol addition updates the board

---

### Step 5: Save Board Changes
```python
# Look for save button in board editor
save_button_exists = await cdp.eval(
    """(() => {
        const btn = Array.from(document.querySelectorAll('button')).find(b => 
            /save|guardar/i.test(b.innerText) && b.type === 'submit'
        );
        return btn !== null;
    })()""",
    await_promise=False
)

if save_button_exists:
    # Click save button
    await cdp.click_text(r"save|guardar", tag="button")
    
    # Wait for loading to complete
    await cdp.wait_for_js("!document.querySelector('.animate-spin')", timeout_s=20)
    
    # Verify success message
    success_message = await cdp.eval(
        """(() => {
            const text = document.body.innerText;
            return /saved|guardado/i.test(text);
        })()""",
        await_promise=False
    )
    assert success_message, "Success message not found after saving board"
    
    print("Board changes saved successfully")
else:
    print("Save button not found - board may auto-save")
```

**Expected Result:** Board changes are saved successfully with a confirmation message.

**Bug Detection Points:**
- Save button not found
- Save operation failing silently
- Success message not displaying
- Changes not persisting to database

**Regression Notes:**
- Verify board data is saved to database
- Check that success message is localized
- Verify no data loss during save

---

### Step 6: Navigate Back to Boards List
```python
# Navigate back to boards list
await cdp.goto("http://localhost:8086/boards")
await cdp.wait_for_js("!document.querySelector('.animate-spin')", timeout_s=20)

# Verify the board is still in the list
board_still_found = await cdp.eval(
    f"""(() => {{
        const text = document.body.innerText;
        return text.includes('{board_name}');
    }})()""",
    await_promise=False
)
assert board_still_found, f"Board '{board_name}' not found in list after editing"
```

**Expected Result:** Board is still visible in the boards list after editing.

**Bug Detection Points:**
- Board disappearing from list after edit
- List not refreshing properly

**Regression Notes:**
- Verify board list updates after edits
- Check that board metadata is correct

---

### Step 7: Assign Board to a Student
```python
# Find the board card and click "Assign" button
assign_clicked = await cdp.eval(
    f"""(() => {{
        const cards = Array.from(document.querySelectorAll('.relative, .board-card'));
        const card = cards.find(c => c.innerText.includes('{board_name}'));
        if (!card) return false;
        const assignBtn = Array.from(card.querySelectorAll('button')).find(b => 
            b.getAttribute('aria-label')?.includes('assign') ||
            b.querySelector('svg.lucide-user-plus')
        );
        if (assignBtn) {{
            assignBtn.click();
            return true;
        }}
        return false;
    }})()""",
    await_promise=False
)
assert assign_clicked, "Assign button not found for board"

# Wait for assignment modal to appear
await cdp.wait_for_selector('div[role="dialog"]', timeout_s=10)

# Verify modal contains student selection
student_select_exists = await cdp.eval(
    """(() => {
        const select = document.querySelector('select[name="student"], select[name="user_id"]');
        return select !== null;
    })()""",
    await_promise=False
)
assert student_select_exists, "Student selection dropdown not found in assignment modal"

# Select the first available student
await cdp.eval(
    """(() => {
        const select = document.querySelector('select[name="student"], select[name="user_id"]');
        if (select && select.options.length > 1) {
            select.selectedIndex = 1; // Select first student (skip default)
            select.dispatchEvent(new Event('change', { bubbles: true }));
            return true;
        }
        return false;
    })()""",
    await_promise=False
)

# Confirm the assignment
await cdp.click_text(r"assign|asignar", tag="button")

# Wait for modal to close
await cdp.wait_for_js("!document.querySelector('div[role=\"dialog\"]')", timeout_s=15)

# Verify success message
success_message = await cdp.eval(
    """(() => {
        const text = document.body.innerText;
        return /assigned|asignado/i.test(text);
    })()""",
    await_promise=False
)
assert success_message, "Success message not found after assigning board"

print(f"Board '{board_name}' assigned to student")
```

**Expected Result:** Board is successfully assigned to a student with a confirmation message.

**Bug Detection Points:**
- Assign button not found
- Assignment modal not opening
- Student selection dropdown empty
- Assignment not completing

**Regression Notes:**
- Verify assignment is saved to database
- Check that student can access assigned board
- Verify assignment appears in student's board list

---

### Step 8: Logout as Teacher
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

**Expected Result:** Teacher is successfully logged out and redirected to login page.

**Bug Detection Points:**
- Logout button not found
- Session not being cleared

**Regression Notes:**
- Verify session cleanup after logout
- Check that authentication tokens are cleared

---

### Step 9: Login as Student
```python
# Enter student credentials
await cdp.set_value("#username", student_username)
await cdp.set_value("#password", student_password)

# Click login button
await cdp.click_text(r"(Iniciar sesi|Login)", tag="button")

# Verify successful login - should be on dashboard
await cdp.wait_for_js("document.body && document.body.innerText.length > 0", timeout_s=10)
current_path = await cdp.eval("location.pathname", await_promise=False)
assert current_path == "/", f"Expected to be on dashboard, got {current_path}"
```

**Expected Result:** Student is successfully logged in and redirected to the dashboard.

**Bug Detection Points:**
- Student login failing
- Incorrect redirect after login

**Regression Notes:**
- Verify student login flow
- Check that student dashboard loads correctly

---

### Step 10: Navigate to Student's Boards Page
```python
# Navigate to boards page
await cdp.goto("http://localhost:8086/boards")
await cdp.wait_for_js("!document.querySelector('.animate-spin')", timeout_s=20)

# Verify we're on the boards page
current_path = await cdp.eval("location.pathname", await_promise=False)
assert current_path == "/boards", f"Expected /boards, got {current_path}"

# Verify the assigned board appears in the student's list
assigned_board_found = await cdp.eval(
    f"""(() => {{
        const text = document.body.innerText;
        return text.includes('{board_name}');
    }})()""",
    await_promise=False
)
assert assigned_board_found, f"Assigned board '{board_name}' not found in student's board list"

print(f"Student can access assigned board '{board_name}'")
```

**Expected Result:** Assigned board appears in the student's boards list.

**Bug Detection Points:**
- Assigned board not visible to student
- Student's board list not loading correctly
- Permission issue preventing access

**Regression Notes:**
- Verify board assignment permissions
- Check that assigned boards are filtered correctly
- Verify student cannot see unassigned boards

---

### Step 11: Student Opens the Assigned Board
```python
# Find and click on the assigned board
board_clicked = await cdp.eval(
    f"""(() => {{
        const cards = Array.from(document.querySelectorAll('.relative, .board-card'));
        const card = cards.find(c => c.innerText.includes('{board_name}'));
        if (!card) return false;
        const link = card.querySelector('a[href*="/boards/"]');
        if (!link) return false;
        link.click();
        return true;
    }})()""",
    await_promise=False
)
assert board_clicked, f"Could not click on board '{board_name}'"

# Wait for board to load
await cdp.wait_for_js("document.body && document.body.innerText.length > 0", timeout_s=10)
await cdp.wait_for_js("!document.querySelector('.animate-spin')", timeout_s=20)

# Verify we're on the board view page
current_path = await cdp.eval("location.pathname", await_promise=False)
assert f"/boards/{board_id}" in current_path, f"Expected to be on board view, got {current_path}"

# Verify board name is displayed
board_name_displayed = await cdp.eval(
    f"""(() => {{
        const text = document.body.innerText;
        return text.includes('{board_name}');
    }})()""",
    await_promise=False
)
assert board_name_displayed, f"Board name '{board_name}' not displayed on board view"

print(f"Student successfully opened assigned board '{board_name}'")
```

**Expected Result:** Student can open and view the assigned board.

**Bug Detection Points:**
- Board not opening for student
- Board view not loading correctly
- Board name not displayed

**Regression Notes:**
- Verify student has read access to assigned boards
- Check that board symbols are visible to student
- Verify student cannot edit board (if read-only)

---

### Step 12: Student Uses Board for Communication
```python
# Look for symbols on the board
symbols_exist = await cdp.eval(
    """(() => {
        const symbols = document.querySelectorAll('.symbol-cell, .board-symbol');
        return symbols.length > 0;
    })()""",
    await_promise=False
)

if symbols_exist:
    # Click on the first symbol
    symbol_clicked = await cdp.eval(
        """(() => {
            const symbols = Array.from(document.querySelectorAll('.symbol-cell, .board-symbol'));
            if (symbols.length === 0) return false;
            symbols[0].click();
            return true;
        })()""",
        await_promise=False
    )
    
    if symbol_clicked:
        # Wait for symbol to be added to message strip
        await cdp.wait_for_js(
            """(() => {
                const strip = document.querySelector('.message-strip, .symbol-strip');
                return strip && strip.children.length > 0;
            })()""",
            timeout_s=5
        )
        
        print("Student successfully used symbol for communication")
    else:
        print("Could not click on symbol")
else:
    print("No symbols found on board")
```

**Expected Result:** Student can click on symbols and build a message.

**Bug Detection Points:**
- Symbols not clickable
- Message strip not updating
- Symbol not being added to message

**Regression Notes:**
- Verify symbol click handlers work correctly
- Check that message strip updates in real-time
- Verify symbol usage is logged

---

### Step 13: Logout as Student
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

### Step 14: Login as Teacher and Verify Assignment
```python
# Enter teacher credentials
await cdp.set_value("#username", teacher_username)
await cdp.set_value("#password", teacher_password)

# Click login button
await cdp.click_text(r"(Iniciar sesi|Login)", tag="button")

# Verify successful login
await cdp.wait_for_js("document.body && document.body.innerText.length > 0", timeout_s=10)
current_path = await cdp.eval("location.pathname", await_promise=False)
assert current_path == "/", f"Expected to be on dashboard, got {current_path}"

# Navigate to boards page
await cdp.goto("http://localhost:8086/boards")
await cdp.wait_for_js("!document.querySelector('.animate-spin')", timeout_s=20)

# Verify the board still exists
board_still_exists = await cdp.eval(
    f"""(() => {{
        const text = document.body.innerText;
        return text.includes('{board_name}');
    }})()""",
    await_promise=False
)
assert board_still_exists, f"Board '{board_name}' not found after student usage"

print(f"Board '{board_name}' still exists and is accessible to teacher")
```

**Expected Result:** Teacher can still access the board after student usage.

**Bug Detection Points:**
- Board not visible to teacher after student usage
- Board data corrupted by student interaction

**Regression Notes:**
- Verify board ownership is maintained
- Check that student usage doesn't affect board ownership

---

### Step 15: Cleanup - Delete Test Board
```python
# Find the board card and click delete button
delete_clicked = await cdp.eval(
    f"""(() => {{
        const cards = Array.from(document.querySelectorAll('.relative, .board-card'));
        const card = cards.find(c => c.innerText.includes('{board_name}'));
        if (!card) return false;
        const deleteBtn = Array.from(card.querySelectorAll('button')).find(b => 
            b.getAttribute('aria-label')?.includes('delete') ||
            b.querySelector('svg.lucide-trash-2')
        );
        if (deleteBtn) {{
            deleteBtn.click();
            return true;
        }}
        return false;
    }})()""",
    await_promise=False
)
assert delete_clicked, "Delete button not found for board"

# Wait for confirmation dialog
await cdp.wait_for_selector('div[role="dialog"]', timeout_s=10)

# Confirm deletion
await cdp.click_text(r"delete|eliminar", tag="button")

# Wait for dialog to close and list to refresh
await cdp.wait_for_js("!document.querySelector('div[role=\"dialog\"]')", timeout_s=15)
await cdp.wait_for_js("!document.querySelector('.animate-spin')", timeout_s=20)

# Verify the board is no longer in the list
board_removed = await cdp.eval(
    f"""(() => {{
        const text = document.body.innerText;
        return !text.includes('{board_name}');
    }})()""",
    await_promise=False
)
assert board_removed, f"Board '{board_name}' still appears in list after deletion"

print(f"Test board '{board_name}' deleted successfully")
```

**Expected Result:** Test board is successfully deleted and no longer appears in the list.

**Bug Detection Points:**
- Delete button not found
- Confirmation dialog not appearing
- Deletion not completing
- Board still visible after deletion

**Regression Notes:**
- Verify board deletion removes all related data
- Check that student can no longer access deleted board
- Verify cascade deletion of board symbols

---

## Cleanup Steps
- Delete the test board created during the test
- Remove any board assignments made during the test
- Verify no orphaned data remains in database

## Edge Cases to Consider
1. **Empty Board Name:** Attempting to create a board with an empty name
2. **Invalid Grid Dimensions:** Setting invalid grid rows/columns
3. **No Symbols Available:** Creating a board when no symbols exist in the library
4. **Assign to Non-Existent Student:** Attempting to assign to a student that doesn't exist
5. **Duplicate Board Name:** Creating multiple boards with the same name
6. **Unassign Board:** Removing a board assignment from a student
7. **Board with No Symbols:** Student accessing a board with no symbols
8. **Concurrent Board Access:** Multiple users accessing the same board simultaneously

## Success Criteria
- Teacher can create a new communication board
- Teacher can add symbols to the board
- Teacher can assign the board to a student
- Student can access the assigned board
- Student can use the board for communication
- Teacher can still access the board after student usage
- Board can be deleted by the teacher
- All UI elements are responsive and accessible
- Proper error handling for invalid inputs
- Session management works correctly (login/logout)

## Related Files
- `src/api/routers/boards.py` - Board management API endpoints
- `src/api/routers/collab.py` - Board collaboration/assignment endpoints
- `src/frontend/src/components/board/BoardEditor.tsx` - Board editor UI
- `src/frontend/src/components/Boards.tsx` - Boards list UI
- `scripts/cdp_harness.py` - CDP harness for automation
