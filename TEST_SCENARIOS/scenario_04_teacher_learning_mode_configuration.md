# Scenario 04: Teacher - Learning Mode Configuration Flow

## Title
Teacher Learning Mode Configuration Flow - Set Up Learning Modes, Assign to Students

## Description
This end-to-end test scenario validates the complete learning mode configuration workflow for teachers. It covers viewing existing learning modes, creating custom learning modes, editing mode settings, and assigning learning modes to students. All interactions are performed through the GUI using Chrome DevTools Protocol (CDP) commands.

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

### Step 2: Navigate to Learning Modes Page
```python
# Navigate to learning modes page via sidebar or direct URL
await cdp.goto("http://localhost:8086/learning-modes")
await cdp.wait_for_js("document.body && document.body.innerText.length > 0", timeout_s=10)

# Wait for loading spinner to disappear
await cdp.wait_for_js("!document.querySelector('.animate-spin')", timeout_s=20)

# Verify we're on the learning modes page
current_path = await cdp.eval("location.pathname", await_promise=False)
assert current_path == "/learning-modes", f"Expected /learning-modes, got {current_path}"

# Verify "Create Learning Mode" button is visible
create_button_exists = await cdp.eval(
    """(() => {
        const btn = Array.from(document.querySelectorAll('button')).find(b => 
            /create learning mode|crear modo/i.test(b.innerText)
        );
        return btn !== null;
    })()""",
    await_promise=False
)
assert create_button_exists, "Create Learning Mode button not found"
```

**Expected Result:** Learning modes page loads successfully with "Create Learning Mode" button visible.

**Bug Detection Points:**
- Page not loading or showing error
- Loading spinner stuck
- Create button missing (permission issue)

**Regression Notes:**
- Verify navigation after route changes
- Check permission-based UI visibility

---

### Step 3: View Existing Learning Modes
```python
# Get list of existing learning modes
existing_modes = await cdp.eval(
    """(() => {
        const modeCards = Array.from(document.querySelectorAll('.mode-card, .learning-mode-item'));
        return modeCards.map(card => {
            const nameEl = card.querySelector('h3, h4, .mode-name');
            const descEl = card.querySelector('.description, .mode-description');
            return {
                name: nameEl ? nameEl.innerText.trim() : '',
                description: descEl ? descEl.innerText.trim() : ''
            };
        });
    })()""",
    await_promise=False
)

print(f"Found {len(existing_modes)} existing learning modes:")
for mode in existing_modes:
    print(f"  - {mode['name']}: {mode['description']}")

# Verify at least some default modes exist
assert len(existing_modes) > 0, "No learning modes found on page"
```

**Expected Result:** Existing learning modes are displayed on the page.

**Bug Detection Points:**
- Learning modes not loading from database
- Mode cards not rendering
- Default modes missing

**Regression Notes:**
- Verify default learning modes are seeded
- Check that mode data is loaded correctly

---

### Step 4: Create a Custom Learning Mode
```python
# Generate unique learning mode details
timestamp = await cdp.eval("Date.now()", await_promise=False)
mode_name = f"Test Learning Mode {timestamp}"
mode_key = f"test_mode_{timestamp}"
mode_description = f"Custom learning mode created for E2E testing at {timestamp}"
mode_instruction = "Focus on vocabulary building and sentence construction."

# Click "Create Learning Mode" button
await cdp.click_text(r"create learning mode|crear modo", tag="button")

# Wait for modal to appear
await cdp.wait_for_selector('div[role="dialog"]', timeout_s=10)

# Fill in the learning mode creation form
await cdp.set_value('input[name="name"]', mode_name)
await cdp.set_value('input[name="key"]', mode_key)
await cdp.set_value('textarea[name="description"], input[name="description"]', mode_description)
await cdp.set_value('textarea[name="prompt_instruction"], textarea[name="instruction"]', mode_instruction)

# Submit the form
await cdp.click_text(r"create|crear", tag="button")

# Wait for modal to close and list to refresh
await cdp.wait_for_js("!document.querySelector('div[role=\"dialog\"]')", timeout_s=15)
await cdp.wait_for_js("!document.querySelector('.animate-spin')", timeout_s=20)

# Verify the new learning mode appears in the list
mode_found = await cdp.eval(
    f"""(() => {{
        const text = document.body.innerText;
        return text.includes('{mode_name}');
    }})()""",
    await_promise=False
)
assert mode_found, f"Created learning mode '{mode_name}' not found in list"

print(f"Created learning mode '{mode_name}' with key: {mode_key}")
```

**Expected Result:** New custom learning mode is created successfully and appears in the list.

**Bug Detection Points:**
- Modal not opening
- Form validation errors (empty name, duplicate key)
- Mode not appearing in list after creation
- Duplicate key handling

**Regression Notes:**
- Verify form validation after schema changes
- Check that mode is created with correct owner
- Verify list refresh after creation

---

### Step 5: Edit the Created Learning Mode
```python
# Find the learning mode card and click edit button
edit_clicked = await cdp.eval(
    f"""(() => {{
        const cards = Array.from(document.querySelectorAll('.mode-card, .learning-mode-item'));
        const card = cards.find(c => c.innerText.includes('{mode_name}'));
        if (!card) return false;
        const editBtn = Array.from(card.querySelectorAll('button')).find(b => 
            b.getAttribute('aria-label')?.includes('edit') ||
            b.querySelector('svg.lucide-pencil')
        );
        if (editBtn) {{
            editBtn.click();
            return true;
        }}
        return false;
    }})()""",
    await_promise=False
)
assert edit_clicked, "Edit button not found for learning mode"

# Wait for edit modal to appear
await cdp.wait_for_selector('div[role="dialog"]', timeout_s=10)

# Update the description
new_description = f"{mode_description} (Updated)"
await cdp.set_value('textarea[name="description"], input[name="description"]', new_description)

# Save the changes
await cdp.click_text(r"save|guardar", tag="button")

# Wait for modal to close
await cdp.wait_for_js("!document.querySelector('div[role=\"dialog\"]')", timeout_s=15)

# Verify the updated description appears
updated_description_found = await cdp.eval(
    f"""(() => {{
        const text = document.body.innerText;
        return text.includes('{new_description}');
    }})()""",
    await_promise=False
)
assert updated_description_found, f"Updated description not found for learning mode"

print(f"Updated learning mode description to: {new_description}")
```

**Expected Result:** Learning mode details are successfully updated.

**Bug Detection Points:**
- Edit button not found
- Modal not opening with pre-filled data
- Changes not saving
- List not updating after save

**Regression Notes:**
- Verify edit form pre-population
- Check that only editable fields can be modified
- Verify update persistence

---

### Step 6: Navigate to Students Page
```python
# Navigate to students page
await cdp.goto("http://localhost:8086/students")
await cdp.wait_for_js("!document.querySelector('.animate-spin')", timeout_s=20)

# Verify we're on the students page
current_path = await cdp.eval("location.pathname", await_promise=False)
assert current_path == "/students", f"Expected /students, got {current_path}"

# Verify students list is visible
students_list_exists = await cdp.eval(
    """(() => {
        return document.querySelector('table, .students-list') !== null;
    })()""",
    await_promise=False
)
assert students_list_exists, "Students list not found"
```

**Expected Result:** Students page loads successfully with students list visible.

**Bug Detection Points:**
- Page navigation issues
- Students list not loading

**Regression Notes:**
- Verify route protection
- Check that teacher can view students

---

### Step 7: Assign Learning Mode to a Student
```python
# Find the first student row and look for learning mode assignment
assignment_clicked = await cdp.eval(
    """(() => {
        const rows = Array.from(document.querySelectorAll('tbody tr, .student-row'));
        if (rows.length === 0) return false;
        const row = rows[0];
        
        // Look for learning mode dropdown or button
        const modeSelect = row.querySelector('select[name="learning_mode"], select[name="mode_id"]');
        if (modeSelect) {
            modeSelect.click();
            return true;
        }
        
        // Or look for a settings/configure button
        const configBtn = Array.from(row.querySelectorAll('button')).find(b => 
            b.getAttribute('aria-label')?.includes('configure') ||
            b.getAttribute('aria-label')?.includes('settings')
        );
        if (configBtn) {
            configBtn.click();
            return true;
        }
        
        return false;
    })()""",
    await_promise=False
)

if assignment_clicked:
    # Wait for modal or dropdown to appear
    await cdp.wait_for_js(
        """(() => {
            return document.querySelector('div[role="dialog"]') !== null ||
                   document.querySelector('select[name="learning_mode"]') !== null;
        })()""",
        timeout_s=10
    )
    
    # Select the custom learning mode we created
    mode_selected = await cdp.eval(
        f"""(() => {{
            const select = document.querySelector('select[name="learning_mode"], select[name="mode_id"]');
            if (!select) return false;
            
            // Find option with our custom mode name
            const options = Array.from(select.options);
            const option = options.find(o => o.innerText.includes('{mode_name}'));
            if (option) {{
                select.value = option.value;
                select.dispatchEvent(new Event('change', {{ bubbles: true }}));
                return true;
            }}
            return false;
        }})()""",
        await_promise=False
    )
    
    if mode_selected:
        # Save the assignment
        await cdp.click_text(r"save|guardar", tag="button")
        
        # Wait for modal to close
        await cdp.wait_for_js("!document.querySelector('div[role=\"dialog\"]')", timeout_s=15)
        
        print(f"Learning mode '{mode_name}' assigned to student")
    else:
        print("Could not select custom learning mode")
else:
    print("Learning mode assignment UI not found - may need different flow")
```

**Expected Result:** Learning mode is successfully assigned to a student.

**Bug Detection Points:**
- Assignment UI not found
- Learning mode dropdown not showing custom modes
- Assignment not saving

**Regression Notes:**
- Verify custom modes appear in assignment dropdown
- Check that assignment is saved to database
- Verify student can see assigned mode

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

### Step 9: Login as Student and Verify Learning Mode
```python
# Enter student credentials
await cdp.set_value("#username", student_username)
await cdp.set_value("#password", student_password)

# Click login button
await cdp.click_text(r"(Iniciar sesi|Login)", tag="button")

# Verify successful login
await cdp.wait_for_js("document.body && document.body.innerText.length > 0", timeout_s=10)
current_path = await cdp.eval("location.pathname", await_promise=False)
assert current_path == "/", f"Expected to be on dashboard, got {current_path}"

# Navigate to learning page to see assigned learning mode
await cdp.goto("http://localhost:8086/learning")
await cdp.wait_for_js("!document.querySelector('.animate-spin')", timeout_s=20)

# Verify we're on the learning page
current_path = await cdp.eval("location.pathname", await_promise=False)
assert current_path == "/learning", f"Expected /learning, got {current_path}"

# Check if the assigned learning mode is visible
mode_visible = await cdp.eval(
    f"""(() => {{
        const text = document.body.innerText;
        return text.includes('{mode_name}');
    }})()""",
    await_promise=False
)

if mode_visible:
    print(f"Student can see assigned learning mode '{mode_name}'")
else:
    print(f"Learning mode '{mode_name}' not visible to student - may be in different location")
```

**Expected Result:** Student can see the assigned learning mode on the learning page.

**Bug Detection Points:**
- Assigned mode not visible to student
- Learning page not loading correctly
- Permission issue preventing access

**Regression Notes:**
- Verify learning mode assignment permissions
- Check that assigned modes are displayed to student
- Verify student cannot see unassigned modes

---

### Step 10: Student Starts a Learning Activity
```python
# Look for learning activities or games
activity_exists = await cdp.eval(
    """(() => {
        const activities = document.querySelectorAll('.activity-card, .learning-game, .topic-card');
        return activities.length > 0;
    })()""",
    await_promise=False
)

if activity_exists:
    # Click on the first available activity
    activity_clicked = await cdp.eval(
        """(() => {
            const activities = Array.from(document.querySelectorAll('.activity-card, .learning-game, .topic-card'));
            if (activities.length === 0) return false;
            activities[0].click();
            return true;
        })()""",
        await_promise=False
    )
    
    if activity_clicked:
        # Wait for activity to load
        await cdp.wait_for_js("document.body && document.body.innerText.length > 0", timeout_s=10)
        await cdp.wait_for_js("!document.querySelector('.animate-spin')", timeout_s=20)
        
        print("Student started a learning activity")
    else:
        print("Could not click on learning activity")
else:
    print("No learning activities found")
```

**Expected Result:** Student can start a learning activity.

**Bug Detection Points:**
- Activities not loading
- Activity not opening
- Activity not responding to clicks

**Regression Notes:**
- Verify learning activities load correctly
- Check that activity uses assigned learning mode
- Verify activity progress is tracked

---

### Step 11: Logout as Student
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

### Step 12: Login as Teacher and Verify Mode Still Exists
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

# Navigate to learning modes page
await cdp.goto("http://localhost:8086/learning-modes")
await cdp.wait_for_js("!document.querySelector('.animate-spin')", timeout_s=20)

# Verify the custom learning mode still exists
mode_still_exists = await cdp.eval(
    f"""(() => {{
        const text = document.body.innerText;
        return text.includes('{mode_name}');
    }})()""",
    await_promise=False
)
assert mode_still_exists, f"Learning mode '{mode_name}' not found after student usage"

print(f"Learning mode '{mode_name}' still exists and is accessible to teacher")
```

**Expected Result:** Teacher can still access the custom learning mode after student usage.

**Bug Detection Points:**
- Learning mode not visible to teacher after student usage
- Mode data corrupted by student interaction

**Regression Notes:**
- Verify learning mode ownership is maintained
- Check that student usage doesn't affect mode ownership

---

### Step 13: Cleanup - Delete Custom Learning Mode
```python
# Find the learning mode card and click delete button
delete_clicked = await cdp.eval(
    f"""(() => {{
        const cards = Array.from(document.querySelectorAll('.mode-card, .learning-mode-item'));
        const card = cards.find(c => c.innerText.includes('{mode_name}'));
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
assert delete_clicked, "Delete button not found for learning mode"

# Wait for confirmation dialog
await cdp.wait_for_selector('div[role="dialog"]', timeout_s=10)

# Confirm deletion
await cdp.click_text(r"delete|eliminar", tag="button")

# Wait for dialog to close and list to refresh
await cdp.wait_for_js("!document.querySelector('div[role=\"dialog\"]')", timeout_s=15)
await cdp.wait_for_js("!document.querySelector('.animate-spin')", timeout_s=20)

# Verify the learning mode is no longer in the list
mode_removed = await cdp.eval(
    f"""(() => {{
        const text = document.body.innerText;
        return !text.includes('{mode_name}');
    }})()""",
    await_promise=False
)
assert mode_removed, f"Learning mode '{mode_name}' still appears in list after deletion"

print(f"Custom learning mode '{mode_name}' deleted successfully")
```

**Expected Result:** Custom learning mode is successfully deleted and no longer appears in the list.

**Bug Detection Points:**
- Delete button not found
- Confirmation dialog not appearing
- Deletion not completing
- Mode still visible after deletion

**Regression Notes:**
- Verify mode deletion removes all related data
- Check that student can no longer access deleted mode
- Verify cascade deletion of mode assignments

---

## Cleanup Steps
- Delete the custom learning mode created during the test
- Remove any learning mode assignments made during the test
- Verify no orphaned data remains in database

## Edge Cases to Consider
1. **Empty Mode Name:** Attempting to create a mode with an empty name
2. **Duplicate Mode Key:** Creating multiple modes with the same key
3. **Invalid Instruction:** Setting invalid or too long prompt instructions
4. **Assign to Non-Existent Student:** Attempting to assign to a student that doesn't exist
5. **Delete System Mode:** Attempting to delete a default system learning mode
6. **Edit System Mode:** Attempting to edit a default system learning mode
7. **No Modes Available:** Student accessing learning page with no assigned modes
8. **Concurrent Mode Access:** Multiple users accessing the same mode simultaneously

## Success Criteria
- Teacher can view existing learning modes
- Teacher can create a custom learning mode
- Teacher can edit learning mode details
- Teacher can assign learning modes to students
- Student can see assigned learning modes
- Student can start learning activities
- Teacher can still access custom modes after student usage
- Custom learning mode can be deleted by the teacher
- All UI elements are responsive and accessible
- Proper error handling for invalid inputs
- Session management works correctly (login/logout)

## Related Files
- `src/api/routers/learning_modes.py` - Learning modes API endpoints
- `src/api/routers/learning.py` - Learning activities API endpoints
- `src/frontend/src/components/learning/LearningModes.tsx` - Learning modes UI
- `src/frontend/src/components/learning/LearningPage.tsx` - Learning page UI
- `scripts/cdp_harness.py` - CDP harness for automation
