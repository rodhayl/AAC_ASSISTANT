# Scenario 09: Cross-Role - Board Collaboration Flow

## Title
Cross-Role Board Collaboration Flow - Teacher Creates, Student Uses, Admin Monitors

## Description
This end-to-end test scenario validates the complete board collaboration workflow across all three roles. It covers a teacher creating a board, a student using the board, and an admin monitoring the board usage. All interactions are performed through the GUI using Chrome DevTools Protocol (CDP) commands.

## Prerequisites
- Application running at `http://localhost:8086`
- Admin user credentials available (set via environment variables `AAC_ADMIN_USERNAME` and `AAC_ADMIN_PASSWORD`)
- Teacher user credentials available (set via environment variables `AAC_TEACHER_USERNAME` and `AAC_TEACHER_PASSWORD`)
- Student user credentials available (set via environment variables `AAC_STUDENT_USERNAME` and `AAC_STUDENT_PASSWORD`)
- Chrome browser with remote debugging enabled on port 9222

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

**Expected Result:** Teacher is successfully logged in and redirected to dashboard (`/`).

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
board_name = f"Collab Board {timestamp}"
board_description = f"Board created for cross-role collaboration testing at {timestamp}"
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

print(f"Teacher created board '{board_name}' with ID: {board_id}")
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

### Step 4: Assign Board to Student
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

print(f"Teacher assigned board '{board_name}' to student")
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

### Step 5: Logout as Teacher
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

### Step 6: Login as Student
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

**Expected Result:** Student is successfully logged in and redirected to dashboard.

**Bug Detection Points:**
- Student login failing
- Incorrect redirect after login

**Regression Notes:**
- Verify student login flow
- Check that student dashboard loads correctly

---

### Step 7: Student Accesses Assigned Board
```python
# Navigate to communication page
await cdp.goto("http://localhost:8086/communication")
await cdp.wait_for_js("!document.querySelector('.animate-spin')", timeout_s=20)

# Verify we're on the communication page
current_path = await cdp.eval("location.pathname", await_promise=False)
assert current_path == "/communication", f"Expected /communication, got {current_path}"

# Verify the assigned board appears in the list
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

**Expected Result:** Assigned board appears in the student's communication board list.

**Bug Detection Points:**
- Assigned board not visible to student
- Student's board list not loading correctly
- Permission issue preventing access

**Regression Notes:**
- Verify board assignment permissions
- Check that assigned boards are filtered correctly
- Verify student cannot see unassigned boards

---

### Step 8: Student Opens the Board
```python
# Find and click on the assigned board
board_clicked = await cdp.eval(
    f"""(() => {{
        const cards = Array.from(document.querySelectorAll('.board-card, [data-testid*="board"]'));
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

print(f"Student opened assigned board '{board_name}'")
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

### Step 9: Student Uses the Board
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
        
        print("Student used a symbol from the board")
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

### Step 10: Logout as Student
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

### Step 11: Login as Admin
```python
# Enter admin credentials
await cdp.set_value("#username", admin_username)
await cdp.set_value("#password", admin_password)

# Click login button
await cdp.click_text(r"(Iniciar sesi|Login)", tag="button")

# Verify successful login - should be on dashboard
await cdp.wait_for_js("document.body && document.body.innerText.length > 0", timeout_s=10)
current_path = await cdp.eval("location.pathname", await_promise=False)
assert current_path == "/", f"Expected to be on dashboard, got {current_path}"
```

**Expected Result:** Admin is successfully logged in and redirected to dashboard.

**Bug Detection Points:**
- Admin login failing
- Incorrect redirect after login

**Regression Notes:**
- Verify admin login flow
- Check that admin dashboard loads correctly

---

### Step 12: Admin Views All Boards
```python
# Navigate to boards page
await cdp.goto("http://localhost:8086/boards")
await cdp.wait_for_js("!document.querySelector('.animate-spin')", timeout_s=20)

# Verify we're on the boards page
current_path = await cdp.eval("location.pathname", await_promise=False)
assert current_path == "/boards", f"Expected /boards, got {current_path}"

# Verify the board created by teacher is visible
board_visible_to_admin = await cdp.eval(
    f"""(() => {{
        const text = document.body.innerText;
        return text.includes('{board_name}');
    }})()""",
    await_promise=False
)
assert board_visible_to_admin, f"Board '{board_name}' not visible to admin"

print(f"Admin can see board '{board_name}' created by teacher")
```

**Expected Result:** Admin can view all boards including the one created by the teacher.

**Bug Detection Points:**
- Boards not loading for admin
- Teacher's board not visible to admin
- Permission issue preventing access

**Regression Notes:**
- Verify admin can see all boards
- Check that board metadata is correct
- Verify admin has full access

---

### Step 13: Admin Views Board Details
```python
# Find and click on the board
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

# Verify board name and description are displayed
board_info = await cdp.eval(
    f"""(() => {{
        const nameEl = document.querySelector('h1, h2, .board-name');
        const descEl = document.querySelector('.description, .board-description');
        return {{
            name: nameEl ? nameEl.innerText.trim() : '',
            description: descEl ? descEl.innerText.trim() : ''
        }};
    }})()""",
    await_promise=False
)

print(f"Admin viewing board details: {board_info['name']}")
print(f"Description: {board_info['description']}")
```

**Expected Result:** Admin can view board details including name and description.

**Bug Detection Points:**
- Board not opening for admin
- Board details not displaying
- Permission issue preventing access

**Regression Notes:**
- Verify admin has full read access to all boards
- Check that board metadata is correct
- Verify admin can see board owner information

---

### Step 14: Admin Views Board Usage Statistics
```python
# Look for usage statistics section on the board
stats_section_exists = await cdp.eval(
    """(() => {
        const headings = Array.from(document.querySelectorAll('h2, h3, .section-title'));
        return headings.some(h => /statistics|usage|estadsticas/i.test(h.innerText));
    })()""",
    await_promise=False
)

if stats_section_exists:
    # Get usage statistics
    stats = await cdp.eval(
        """(() => {
            const statCards = Array.from(document.querySelectorAll('.stat-card, .stat-item'));
            return statCards.map(card => {
                const labelEl = card.querySelector('.label, .stat-label');
                const valueEl = card.querySelector('.value, .stat-value');
                return {
                    label: labelEl ? labelEl.innerText.trim() : '',
                    value: valueEl ? valueEl.innerText.trim() : ''
                };
            });
        })()""",
        await_promise=False
    )
    
    print(f"Found {len(stats)} usage statistics:")
    for stat in stats:
        print(f"  - {stat['label']}: {stat['value']}")
else:
    print("Usage statistics section not found on board page")
```

**Expected Result:** Board usage statistics are displayed (if available).

**Bug Detection Points:**
- Statistics not loading
- Stats not calculating correctly
- Stats section missing

**Regression Notes:**
- Verify statistics are calculated correctly
- Check that stats update with new usage
- Verify stats are accurate

---

### Step 15: Admin Views Board Assignments
```python
# Look for assignments section on the board
assignments_section_exists = await cdp.eval(
    """(() => {
        const headings = Array.from(document.querySelectorAll('h2, h3, .section-title'));
        return headings.some(h => /assignments|asignaciones/i.test(h.innerText));
    })()""",
    await_promise=False
)

if assignments_section_exists:
    # Get board assignments
    assignments = await cdp.eval(
        """(() => {
            const assignmentItems = Array.from(document.querySelectorAll('.assignment-item, .student-assignment'));
            return assignmentItems.map(item => {
                const nameEl = item.querySelector('.name, .student-name');
                const dateEl = item.querySelector('.date, .assigned-date');
                return {
                    name: nameEl ? nameEl.innerText.trim() : '',
                    date: dateEl ? dateEl.innerText.trim() : ''
                };
            });
        })()""",
        await_promise=False
    )
    
    print(f"Found {len(assignments)} board assignments:")
    for assignment in assignments:
        print(f"  - {assignment['name']} (assigned: {assignment['date']})")
else:
    print("Assignments section not found on board page")
```

**Expected Result:** Board assignments are displayed (if available).

**Bug Detection Points:**
- Assignments not loading
- Assignment data not displaying
- Assignments section missing

**Regression Notes:**
- Verify assignments are loaded correctly
- Check that assignment dates are correct
- Verify admin can see all assignments

---

### Step 16: Admin Views Board Symbols
```python
# Look for symbols section on the board
symbols_section_exists = await cdp.eval(
    """(() => {
        const headings = Array.from(document.querySelectorAll('h2, h3, .section-title'));
        return headings.some(h => /symbols|smbolos/i.test(h.innerText));
    })()""",
    await_promise=False
)

if symbols_section_exists:
    # Get board symbols
    symbols = await cdp.eval(
        """(() => {
            const symbolCells = Array.from(document.querySelectorAll('.symbol-cell, .board-symbol'));
            return symbolCells.map(cell => {
                const labelEl = cell.querySelector('.label, .symbol-label');
                const imgEl = cell.querySelector('img');
                return {
                    label: labelEl ? labelEl.innerText.trim() : '',
                    has_image: imgEl !== null
                };
            });
        })()""",
        await_promise=False
    )
    
    print(f"Found {len(symbols)} symbols on board:")
    for symbol in symbols[:5]:  # Show first 5 symbols
        print(f"  - {symbol['label']} (image: {symbol['has_image']})")
else:
    print("Symbols section not found on board page")
```

**Expected Result:** Board symbols are displayed.

**Bug Detection Points:**
- Symbols not loading
- Symbol grid not rendering
- Empty board

**Regression Notes:**
- Verify symbols are loaded correctly
- Check that symbol images are displayed
- Verify symbol positions are correct

---

### Step 17: Logout as Admin
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

**Expected Result:** Admin is successfully logged out and redirected to login page.

**Bug Detection Points:**
- Logout button not found
- Session not being cleared

**Regression Notes:**
- Verify session cleanup after logout
- Check that authentication tokens are cleared

---

### Step 18: Login as Teacher and Verify Board Still Exists
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
assert board_still_exists, f"Board '{board_name}' not found after admin viewing"

print(f"Teacher can still access board '{board_name}' after admin viewing")
```

**Expected Result:** Teacher can still access the board after admin has viewed it.

**Bug Detection Points:**
- Board not visible to teacher after admin viewing
- Board data corrupted by admin interaction

**Regression Notes:**
- Verify board ownership is maintained
- Check that admin viewing doesn't affect board ownership

---

### Step 19: Cleanup - Delete Test Board
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
- Verify cascade deletion of board symbols and assignments

---

## Cleanup Steps
- Delete the test board created during the test
- Remove any board assignments made during the test
- Verify no orphaned data remains in the database

## Edge Cases to Consider
1. **Board with No Symbols:** Creating a board with no symbols
2. **Multiple Assignments:** Assigning the same board to multiple students
3. **Unassign Board:** Removing a board assignment from a student
4. **Admin Edit Board:** Admin attempting to edit a board created by teacher
5. **Concurrent Access:** Multiple users accessing the same board simultaneously
6. **Board Deletion:** Deleting a board while a student is using it
7. **Permission Issues:** Teacher trying to access admin-only features
8. **Network Issues:** Testing behavior during slow network conditions

## Success Criteria
- Teacher can create a new communication board
- Teacher can assign the board to a student
- Student can access the assigned board
- Student can use the board (select symbols)
- Admin can view all boards including teacher's board
- Admin can view board details and statistics
- Admin can view board assignments
- Admin can view board symbols
- Teacher can still access the board after admin viewing
- Board can be deleted by the teacher
- All UI elements are responsive and accessible
- Proper error handling for invalid operations
- Session management works correctly (login/logout for all roles)
- Role-based access control is enforced correctly

## Related Files
- `src/api/routers/boards.py` - Board management API endpoints
- `src/api/routers/collab.py` - Board collaboration/assignment endpoints
- `src/api/routers/analytics.py` - Analytics API endpoints
- `src/frontend/src/components/Boards.tsx` - Boards list UI
- `src/frontend/src/components/board/BoardEditor.tsx` - Board editor UI
- `src/frontend/src/components/board/CommunicationBoard.tsx` - Communication board UI
- `scripts/cdp_harness.py` - CDP harness for automation
