# Scenario 01: Admin - User Management Flow

## Title
Admin User Management Flow - Create, Edit, and Delete Users Across All Roles

## Description
This end-to-end test scenario validates the complete user management workflow for administrators. It covers creating new users (teacher and student), editing user details, and deleting users. All interactions are performed through the GUI using Chrome DevTools Protocol (CDP) commands.

## Prerequisites
- Application running at `http://localhost:8086`
- Admin user credentials available (set via environment variables `AAC_ADMIN_USERNAME` and `AAC_ADMIN_PASSWORD`)
- Chrome browser with remote debugging enabled on port 9222
- No existing users with usernames matching the test patterns

## Test Steps

### Step 1: Initialize CDP Connection and Login as Admin
```python
# Connect to Chrome DevTools Protocol
target = get_first_page_target()
async with CDP(target.ws_url) as cdp:
    await cdp.enable()
    await cdp.clear_origin_data("http://localhost:8086")
    
    # Navigate to login page
    await cdp.goto("http://localhost:8086/login")
    await cdp.wait_for_selector("#username", timeout_s=15)
    
    # Enter admin credentials
    await cdp.set_value("#username", admin_username)
    await cdp.set_value("#password", admin_password)
    
    # Click login button (supports both English and Spanish)
    await cdp.click_text(r"(Iniciar sesi|Login)", tag="button")
    
    # Verify successful login - should be on dashboard
    await cdp.wait_for_js("document.body && document.body.innerText.length > 0", timeout_s=10)
    current_path = await cdp.eval("location.pathname", await_promise=False)
    assert current_path == "/", f"Expected to be on dashboard, got {current_path}"
```

**Expected Result:** Admin is successfully logged in and redirected to the dashboard (`/`).

**Bug Detection Points:**
- Login button not found or not clickable
- Incorrect redirect after login
- Dashboard not loading properly

**Regression Notes:**
- Verify login flow works after authentication changes
- Check that role-based redirects are correct

---

### Step 2: Navigate to Teachers Management Page
```python
# Navigate to teachers page via sidebar or direct URL
await cdp.goto("http://localhost:8086/teachers")
await cdp.wait_for_js("document.body && document.body.innerText.length > 0", timeout_s=10)

# Wait for loading spinner to disappear
await cdp.wait_for_js("!document.querySelector('.animate-spin')", timeout_s=20)

# Verify we're on the teachers page
current_path = await cdp.eval("location.pathname", await_promise=False)
assert current_path == "/teachers", f"Expected /teachers, got {current_path}"

# Verify "Create Teacher" button is visible
create_button_exists = await cdp.eval(
    """(() => {
        const btn = Array.from(document.querySelectorAll('button')).find(b => 
            /create teacher|crear/i.test(b.innerText)
        );
        return btn !== null;
    })()""",
    await_promise=False
)
assert create_button_exists, "Create Teacher button not found"
```

**Expected Result:** Teachers management page loads successfully with the "Create Teacher" button visible.

**Bug Detection Points:**
- Page not loading or showing error
- Loading spinner stuck
- Create button missing (permission issue)

**Regression Notes:**
- Verify navigation after route changes
- Check permission-based UI visibility

---

### Step 3: Create a New Teacher User
```python
# Generate unique teacher details
timestamp = await cdp.eval("Date.now()", await_promise=False)
teacher_username = f"test_teacher_{timestamp}"
teacher_display_name = f"Test Teacher {timestamp}"
teacher_password = "TeacherPass123!"

# Click "Create Teacher" button
await cdp.click_text(r"create teacher|crear", tag="button")

# Wait for modal to appear
await cdp.wait_for_selector('div[role="dialog"]', timeout_s=10)

# Fill in the teacher creation form
await cdp.set_value('input[name="username"]', teacher_username)
await cdp.set_value('input[name="displayName"]', teacher_display_name)
await cdp.set_value('input[name="password"]', teacher_password)
await cdp.set_value('input[name="confirmPassword"]', teacher_password)

# Submit the form
await cdp.click('button[type="submit"]')

# Wait for modal to close and list to refresh
await cdp.wait_for_js("!document.querySelector('div[role=\"dialog\"]')", timeout_s=15)
await cdp.wait_for_js("!document.querySelector('.animate-spin')", timeout_s=20)

# Verify the new teacher appears in the list
teacher_found = await cdp.eval(
    f"""(() => {{
        const text = document.body.innerText;
        return text.includes('{teacher_username}');
    }})()""",
    await_promise=False
)
assert teacher_found, f"Created teacher '{teacher_username}' not found in list"
```

**Expected Result:** New teacher user is created successfully and appears in the teachers list.

**Bug Detection Points:**
- Modal not opening
- Form validation errors (password mismatch, username taken)
- Teacher not appearing in list after creation
- Duplicate username handling

**Regression Notes:**
- Verify form validation after schema changes
- Check password requirements enforcement
- Verify list refresh after creation

---

### Step 4: Edit the Created Teacher
```python
# Find the teacher row in the table
teacher_row_found = await cdp.eval(
    f"""(() => {{
        const rows = Array.from(document.querySelectorAll('tbody tr'));
        return rows.find(row => row.innerText.includes('{teacher_username}'));
    }})()""",
    await_promise=False
)
assert teacher_row_found, "Teacher row not found in table"

# Click the edit button (pencil icon) for the teacher
await cdp.eval(
    f"""(() => {{
        const rows = Array.from(document.querySelectorAll('tbody tr'));
        const row = rows.find(r => r.innerText.includes('{teacher_username}'));
        if (!row) return false;
        const editBtn = Array.from(row.querySelectorAll('button')).find(b => 
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

# Wait for edit modal to appear
await cdp.wait_for_selector('div[role="dialog"]', timeout_s=10)

# Update the display name
new_display_name = f"{teacher_display_name} (Updated)"
await cdp.set_value('input[name="displayName"]', new_display_name)

# Save the changes
await cdp.click_text(r"save|guardar", tag="button")

# Wait for modal to close
await cdp.wait_for_js("!document.querySelector('div[role=\"dialog\"]')", timeout_s=15)

# Verify the updated name appears
updated_name_found = await cdp.eval(
    f"""(() => {{
        const text = document.body.innerText;
        return text.includes('{new_display_name}');
    }})()""",
    await_promise=False
)
assert updated_name_found, f"Updated display name '{new_display_name}' not found"
```

**Expected Result:** Teacher details are successfully updated and the new display name appears in the list.

**Bug Detection Points:**
- Edit button not found or not clickable
- Modal not opening with pre-filled data
- Changes not saving
- List not updating after save

**Regression Notes:**
- Verify edit form pre-population
- Check that only editable fields can be modified
- Verify update persistence

---

### Step 5: Navigate to Students Management Page
```python
# Navigate to students page
await cdp.goto("http://localhost:8086/students")
await cdp.wait_for_js("document.body && document.body.innerText.length > 0", timeout_s=10)

# Wait for loading to complete
await cdp.wait_for_js("!document.querySelector('.animate-spin')", timeout_s=20)

# Verify we're on the students page
current_path = await cdp.eval("location.pathname", await_promise=False)
assert current_path == "/students", f"Expected /students, got {current_path}"

# Verify "Create Student" button is visible
create_button_exists = await cdp.eval(
    """(() => {
        const btn = Array.from(document.querySelectorAll('button')).find(b => 
            /create student|crear/i.test(b.innerText)
        );
        return btn !== null;
    })()""",
    await_promise=False
)
assert create_button_exists, "Create Student button not found"
```

**Expected Result:** Students management page loads successfully with the "Create Student" button visible.

**Bug Detection Points:**
- Page navigation issues
- Permission errors
- UI elements not rendering

**Regression Notes:**
- Verify route protection
- Check role-based access control

---

### Step 6: Create a New Student User
```python
# Generate unique student details
timestamp = await cdp.eval("Date.now()", await_promise=False)
student_username = f"test_student_{timestamp}"
student_display_name = f"Test Student {timestamp}"
student_password = "StudentPass123!"

# Click "Create Student" button
await cdp.click_text(r"create student|crear", tag="button")

# Wait for modal to appear
await cdp.wait_for_selector('div[role="dialog"]', timeout_s=10)

# Fill in the student creation form
await cdp.set_value('input[name="username"]', student_username)
await cdp.set_value('input[name="displayName"]', student_display_name)
await cdp.set_value('input[name="password"]', student_password)
await cdp.set_value('input[name="confirmPassword"]', student_password)

# Submit the form
await cdp.click('button[type="submit"]')

# Wait for modal to close and list to refresh
await cdp.wait_for_js("!document.querySelector('div[role=\"dialog\"]')", timeout_s=15)
await cdp.wait_for_js("!document.querySelector('.animate-spin')", timeout_s=20)

# Verify the new student appears in the list
student_found = await cdp.eval(
    f"""(() => {{
        const text = document.body.innerText;
        return text.includes('{student_username}');
    }})()""",
    await_promise=False
)
assert student_found, f"Created student '{student_username}' not found in list"
```

**Expected Result:** New student user is created successfully and appears in the students list.

**Bug Detection Points:**
- Form submission errors
- Student not appearing in list
- Duplicate username handling

**Regression Notes:**
- Verify student-specific fields (if any)
- Check that student role is correctly assigned

---

### Step 7: Set Guardian Profile for the Student
```python
# Find the student row and click the Guardian Profile button
guardian_profile_clicked = await cdp.eval(
    f"""(() => {{
        const rows = Array.from(document.querySelectorAll('tbody tr'));
        const row = rows.find(r => r.innerText.includes('{student_username}'));
        if (!row) return false;
        const profileBtn = Array.from(row.querySelectorAll('button')).find(b => 
            b.getAttribute('title')?.includes('guardian') ||
            b.getAttribute('aria-label')?.includes('guardian') ||
            b.querySelector('svg.lucide-sparkles')
        );
        if (profileBtn) {{
            profileBtn.click();
            return true;
        }}
        return false;
    }})()""",
    await_promise=False
)
assert guardian_profile_clicked, "Guardian Profile button not found or not clickable"

# Wait for guardian profile modal to appear
await cdp.wait_for_selector('div[role="dialog"]', timeout_s=10)

# Verify modal title contains "Guardian Profile"
modal_title = await cdp.eval(
    """(() => {
        const modal = document.querySelector('div[role="dialog"]');
        return modal ? modal.innerText : '';
    })()""",
    await_promise=False
)
assert "guardian" in modal_title.lower() or "perfil" in modal_title.lower(), "Guardian Profile modal not found"

# Set guardian profile details
await cdp.set_value('input[name="age"]', "10")
await cdp.set_value('input[name="language"]', "en")

# Save the guardian profile
await cdp.click_text(r"save|guardar", tag="button")

# Wait for modal to close and success message
await cdp.wait_for_js("!document.querySelector('div[role=\"dialog\"]')", timeout_s=15)

# Verify success message appears
success_message = await cdp.eval(
    """(() => {
        const text = document.body.innerText;
        return /saved|guardado/i.test(text);
    })()""",
    await_promise=False
)
assert success_message, "Success message not found after saving guardian profile"
```

**Expected Result:** Guardian profile is successfully saved for the student with a confirmation message displayed.

**Bug Detection Points:**
- Guardian Profile button not accessible
- Modal not opening
- Profile data not saving
- Success message not displaying

**Regression Notes:**
- Verify guardian profile fields after schema changes
- Check that profile data persists

---

### Step 8: Delete the Created Teacher
```python
# Navigate back to teachers page
await cdp.goto("http://localhost:8086/teachers")
await cdp.wait_for_js("!document.querySelector('.animate-spin')", timeout_s=20)

# Find the teacher row and click delete button
delete_clicked = await cdp.eval(
    f"""(() => {{
        const rows = Array.from(document.querySelectorAll('tbody tr'));
        const row = rows.find(r => r.innerText.includes('{teacher_username}'));
        if (!row) return false;
        const deleteBtn = Array.from(row.querySelectorAll('button')).find(b => 
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
assert delete_clicked, "Delete button not found for teacher"

# Wait for confirmation dialog
await cdp.wait_for_selector('div[role="dialog"]', timeout_s=10)

# Confirm deletion by clicking the delete button in the dialog
await cdp.click_text(r"delete|eliminar", tag="button")

# Wait for dialog to close and list to refresh
await cdp.wait_for_js("!document.querySelector('div[role=\"dialog\"]')", timeout_s=15)
await cdp.wait_for_js("!document.querySelector('.animate-spin')", timeout_s=20)

# Verify the teacher is no longer in the list
teacher_removed = await cdp.eval(
    f"""(() => {{
        const text = document.body.innerText;
        return !text.includes('{teacher_username}');
    }})()""",
    await_promise=False
)
assert teacher_removed, f"Teacher '{teacher_username}' still appears in list after deletion"
```

**Expected Result:** Teacher is successfully deleted and no longer appears in the teachers list.

**Bug Detection Points:**
- Delete button not found
- Confirmation dialog not appearing
- Deletion not completing
- Teacher still visible after deletion

**Regression Notes:**
- Verify cascade deletion (related data cleanup)
- Check that deletion is irreversible

---

### Step 9: Delete the Created Student
```python
# Navigate to students page
await cdp.goto("http://localhost:8086/students")
await cdp.wait_for_js("!document.querySelector('.animate-spin')", timeout_s=20)

# Find the student row and click delete button
delete_clicked = await cdp.eval(
    f"""(() => {{
        const rows = Array.from(document.querySelectorAll('tbody tr'));
        const row = rows.find(r => r.innerText.includes('{student_username}'));
        if (!row) return false;
        const deleteBtn = Array.from(row.querySelectorAll('button')).find(b => 
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
assert delete_clicked, "Delete button not found for student"

# Wait for confirmation dialog
await cdp.wait_for_selector('div[role="dialog"]', timeout_s=10)

# Confirm deletion by clicking the delete button in the dialog
await cdp.click_text(r"delete|eliminar", tag="button")

# Wait for dialog to close and list to refresh
await cdp.wait_for_js("!document.querySelector('div[role=\"dialog\"]')", timeout_s=15)
await cdp.wait_for_js("!document.querySelector('.animate-spin')", timeout_s=20)

# Verify the student is no longer in the list
student_removed = await cdp.eval(
    f"""(() => {{
        const text = document.body.innerText;
        return !text.includes('{student_username}');
    }})()""",
    await_promise=False
)
assert student_removed, f"Student '{student_username}' still appears in list after deletion"
```

**Expected Result:** Student is successfully deleted and no longer appears in the students list.

**Bug Detection Points:**
- Delete confirmation not working
- Student data not being cleaned up
- UI not updating after deletion

**Regression Notes:**
- Verify student-specific data cleanup (achievements, progress)
- Check that guardian profile is also deleted

---

### Step 10: Logout and Verify Session Cleanup
```python
# Navigate to dashboard
await cdp.goto("http://localhost:8086/")

# Click logout button (may be in different locations)
logout_clicked = await cdp.eval(
    """(() => {
        // Try to find logout button by text
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

# Verify we're on the login page
current_path = await cdp.eval("location.pathname", await_promise=False)
assert current_path == "/login", f"Expected to be on /login after logout, got {current_path}"

# Verify we cannot access protected pages without login
await cdp.goto("http://localhost:8086/teachers")
await cdp.wait_for_js("document.body && document.body.innerText.length > 0", timeout_s=10)

# Should be redirected back to login
current_path = await cdp.eval("location.pathname", await_promise=False)
assert current_path == "/login", f"Expected redirect to /login, got {current_path}"
```

**Expected Result:** Admin is successfully logged out and redirected to the login page. Access to protected pages is denied.

**Bug Detection Points:**
- Logout button not found
- Session not being cleared
- Protected pages still accessible after logout

**Regression Notes:**
- Verify session cleanup after logout
- Check that authentication tokens are cleared
- Verify redirect behavior for unauthenticated users

---

## Cleanup Steps
No explicit cleanup needed as the test deletes the created users. However, if the test fails mid-execution, manual cleanup may be required:
- Delete any test users created (pattern: `test_teacher_*`, `test_student_*`)
- Verify no orphaned data remains in the database

## Edge Cases to Consider
1. **Duplicate Username:** Attempting to create a user with an existing username
2. **Invalid Password:** Creating a user with a password that doesn't meet requirements
3. **Password Mismatch:** Confirm password field doesn't match password field
4. **Empty Fields:** Submitting the form with required fields empty
5. **Special Characters:** Using special characters in username or display name
6. **Very Long Names:** Testing with extremely long display names
7. **Concurrent Operations:** Multiple admins managing users simultaneously
8. **Network Issues:** Testing behavior during slow network conditions

## Success Criteria
- Admin can successfully create teacher and student users
- Admin can edit user details (display name, guardian profile)
- Admin can delete users with confirmation
- All UI elements are responsive and accessible
- Proper error handling for invalid inputs
- Session management works correctly (login/logout)
- Protected routes are properly secured

## Related Files
- `src/api/routers/users.py` - User management API endpoints
- `src/api/routers/admin.py` - Admin-specific endpoints
- `src/frontend/src/components/admin/UserManagement.tsx` - User management UI
- `scripts/cdp_harness.py` - CDP harness for automation
