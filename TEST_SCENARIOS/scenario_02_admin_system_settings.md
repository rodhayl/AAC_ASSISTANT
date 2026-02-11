# Scenario 02: Admin - System Settings Flow

## Title
Admin System Settings Flow - Configure Global Settings and Verify Persistence

## Description
This end-to-end test scenario validates the complete system settings management workflow for administrators. It covers viewing, modifying, and persisting global system settings including UI language, theme, and other configuration options. All interactions are performed through the GUI using Chrome DevTools Protocol (CDP) commands.

## Prerequisites
- Application running at `http://localhost:8086`
- Admin user credentials available (set via environment variables `AAC_ADMIN_USERNAME` and `AAC_ADMIN_PASSWORD`)
- Chrome browser with remote debugging enabled on port 9222
- Default system settings are in place

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

### Step 2: Navigate to Settings Page
```python
# Navigate to settings page via sidebar or direct URL
await cdp.goto("http://localhost:8086/settings")
await cdp.wait_for_js("document.body && document.body.innerText.length > 0", timeout_s=10)

# Wait for loading spinner to disappear
await cdp.wait_for_js("!document.querySelector('.animate-spin')", timeout_s=20)

# Verify we're on the settings page
current_path = await cdp.eval("location.pathname", await_promise=False)
assert current_path == "/settings", f"Expected /settings, got {current_path}"

# Verify settings page heading is visible
settings_heading = await cdp.eval(
    """(() => {
        const headings = Array.from(document.querySelectorAll('h1, h2'));
        return headings.find(h => /settings|configuraci/i.test(h.innerText));
    })()""",
    await_promise=False
)
assert settings_heading, "Settings page heading not found"
```

**Expected Result:** Settings page loads successfully with the settings heading visible.

**Bug Detection Points:**
- Page not loading or showing error
- Loading spinner stuck
- Settings heading missing (permission issue)

**Regression Notes:**
- Verify navigation after route changes
- Check permission-based UI visibility

---

### Step 3: View Current System Settings
```python
# Capture current settings values before modification
current_ui_language = await cdp.eval(
    """(() => {
        const select = document.querySelector('select[name="ui_language"], select[name="language"]');
        return select ? select.value : null;
    })()""",
    await_promise=False
)

current_theme = await cdp.eval(
    """(() => {
        const select = document.querySelector('select[name="theme"]');
        return select ? select.value : null;
    })()""",
    await_promise=False
)

# Store original values for restoration later
original_settings = {
    "ui_language": current_ui_language,
    "theme": current_theme
}

print(f"Current UI Language: {current_ui_language}")
print(f"Current Theme: {current_theme}")

# Verify settings form is present
settings_form_exists = await cdp.eval(
    """(() => {
        return document.querySelector('form') !== null;
    })()""",
    await_promise=False
)
assert settings_form_exists, "Settings form not found on page"
```

**Expected Result:** Current system settings are displayed and can be retrieved. Settings form is present on the page.

**Bug Detection Points:**
- Settings not loading from database
- Form elements missing
- Default values not set correctly

**Regression Notes:**
- Verify settings are loaded from database
- Check that default values are correct

---

### Step 4: Change UI Language Setting
```python
# Find the UI language dropdown
language_select_exists = await cdp.eval(
    """(() => {
        const select = document.querySelector('select[name="ui_language"], select[name="language"]');
        return select !== null;
    })()""",
    await_promise=False
)
assert language_select_exists, "UI Language dropdown not found"

# Change UI language to Spanish (if currently English) or English (if currently Spanish)
new_language = "es" if current_ui_language == "en" else "en"
await cdp.set_select_value('select[name="ui_language"], select[name="language"]', new_language)

# Verify the value was changed
updated_language = await cdp.eval(
    """(() => {
        const select = document.querySelector('select[name="ui_language"], select[name="language"]');
        return select ? select.value : null;
    })()""",
    await_promise=False
)
assert updated_language == new_language, f"Language not updated to {new_language}, got {updated_language}"

print(f"Changed UI Language from {current_ui_language} to {new_language}")
```

**Expected Result:** UI language setting is successfully changed in the dropdown.

**Bug Detection Points:**
- Language dropdown not responding to change
- Invalid language option selected
- Dropdown not updating visual state

**Regression Notes:**
- Verify all supported languages are available
- Check that language change affects UI immediately or after save

---

### Step 5: Change Theme Setting
```python
# Find the theme dropdown
theme_select_exists = await cdp.eval(
    """(() => {
        const select = document.querySelector('select[name="theme"]');
        return select !== null;
    })()""",
    await_promise=False
)
assert theme_select_exists, "Theme dropdown not found"

# Change theme (cycle through available options)
theme_options = ["light", "dark", "auto"]
current_theme_index = theme_options.index(current_theme) if current_theme in theme_options else 0
new_theme = theme_options[(current_theme_index + 1) % len(theme_options)]

await cdp.set_select_value('select[name="theme"]', new_theme)

# Verify the value was changed
updated_theme = await cdp.eval(
    """(() => {
        const select = document.querySelector('select[name="theme"]');
        return select ? select.value : null;
    })()""",
    await_promise=False
)
assert updated_theme == new_theme, f"Theme not updated to {new_theme}, got {updated_theme}"

print(f"Changed Theme from {current_theme} to {new_theme}")
```

**Expected Result:** Theme setting is successfully changed in the dropdown.

**Bug Detection Points:**
- Theme dropdown not responding to change
- Invalid theme option selected
- Theme not applying to UI

**Regression Notes:**
- Verify all supported themes are available
- Check that theme change applies immediately or after save

---

### Step 6: Save Settings Changes
```python
# Click the save button
save_clicked = await cdp.eval(
    """(() => {
        const buttons = Array.from(document.querySelectorAll('button[type="submit"]'));
        const saveBtn = buttons.find(b => /save|guardar/i.test(b.innerText));
        if (saveBtn) {
            saveBtn.click();
            return true;
        }
        return false;
    })()""",
    await_promise=False
)
assert save_clicked, "Save button not found or not clickable"

# Wait for loading to complete
await cdp.wait_for_js("!document.querySelector('.animate-spin')", timeout_s=20)

# Verify success message appears
success_message = await cdp.eval(
    """(() => {
        const text = document.body.innerText;
        return /saved|guardado|settings saved/i.test(text);
    })()""",
    await_promise=False
)
assert success_message, "Success message not found after saving settings"
```

**Expected Result:** Settings are saved successfully with a confirmation message displayed.

**Bug Detection Points:**
- Save button not found
- Save operation failing silently
- Success message not displaying
- Settings not persisting to database

**Regression Notes:**
- Verify settings are saved to database
- Check that success message is localized
- Verify no data loss during save

---

### Step 7: Verify Settings Persistence (Page Refresh)
```python
# Refresh the page to verify settings persist
await cdp.goto("http://localhost:8086/settings")
await cdp.wait_for_js("!document.querySelector('.animate-spin')", timeout_s=20)

# Verify UI language is still set to new value
persisted_language = await cdp.eval(
    """(() => {
        const select = document.querySelector('select[name="ui_language"], select[name="language"]');
        return select ? select.value : null;
    })()""",
    await_promise=False
)
assert persisted_language == new_language, f"Language not persisted, expected {new_language}, got {persisted_language}"

# Verify theme is still set to new value
persisted_theme = await cdp.eval(
    """(() => {
        const select = document.querySelector('select[name="theme"]');
        return select ? select.value : null;
    })()""",
    await_promise=False
)
assert persisted_theme == new_theme, f"Theme not persisted, expected {new_theme}, got {persisted_theme}"

print(f"Settings persisted after refresh: Language={persisted_language}, Theme={persisted_theme}")
```

**Expected Result:** Settings are persisted after page refresh and display the previously saved values.

**Bug Detection Points:**
- Settings reverting to defaults after refresh
- Database not saving settings correctly
- Settings not loading from database on page load

**Regression Notes:**
- Verify settings persistence across sessions
- Check that settings are loaded correctly on page load

---

### Step 8: Verify Settings Persistence (Logout/Login)
```python
# Logout from admin account
await cdp.goto("http://localhost:8086/")
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
current_path = await cdp.eval("location.pathname", await_promise=False)
assert current_path == "/login", f"Expected to be on /login after logout, got {current_path}"

# Login again as admin
await cdp.set_value("#username", admin_username)
await cdp.set_value("#password", admin_password)
await cdp.click_text(r"(Iniciar sesi|Login)", tag="button")

# Wait for dashboard to load
await cdp.wait_for_js("document.body && document.body.innerText.length > 0", timeout_s=10)
current_path = await cdp.eval("location.pathname", await_promise=False)
assert current_path == "/", f"Expected to be on dashboard after login, got {current_path}"

# Navigate to settings page
await cdp.goto("http://localhost:8086/settings")
await cdp.wait_for_js("!document.querySelector('.animate-spin')", timeout_s=20)

# Verify settings are still persisted after logout/login
persisted_after_login_language = await cdp.eval(
    """(() => {
        const select = document.querySelector('select[name="ui_language"], select[name="language"]');
        return select ? select.value : null;
    })()""",
    await_promise=False
)
assert persisted_after_login_language == new_language, f"Language not persisted after login, expected {new_language}, got {persisted_after_login_language}"

persisted_after_login_theme = await cdp.eval(
    """(() => {
        const select = document.querySelector('select[name="theme"]');
        return select ? select.value : null;
    })()""",
    await_promise=False
)
assert persisted_after_login_theme == new_theme, f"Theme not persisted after login, expected {new_theme}, got {persisted_after_login_theme}"

print(f"Settings persisted after logout/login: Language={persisted_after_login_language}, Theme={persisted_after_login_theme}")
```

**Expected Result:** Settings are persisted across logout/login cycles.

**Bug Detection Points:**
- Settings not persisting across sessions
- User-specific settings vs global settings confusion
- Settings being reset on login

**Regression Notes:**
- Verify settings are stored at the correct level (user vs system)
- Check that settings are loaded correctly after login

---

### Step 9: Restore Original Settings
```python
# Restore original settings for cleanup
await cdp.set_select_value('select[name="ui_language"], select[name="language"]', original_settings["ui_language"])
await cdp.set_select_value('select[name="theme"]', original_settings["theme"])

# Save the restored settings
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
assert success_message, "Success message not found after restoring settings"

print(f"Restored original settings: Language={original_settings['ui_language']}, Theme={original_settings['theme']}")
```

**Expected Result:** Original settings are successfully restored.

**Bug Detection Points:**
- Settings not restoring correctly
- Save operation failing

**Regression Notes:**
- Verify settings can be reverted
- Check that no data corruption occurs during restore

---

### Step 10: Test Export Data Functionality (Admin Only)
```python
# Look for Export Data button
export_button_exists = await cdp.eval(
    """(() => {
        const buttons = Array.from(document.querySelectorAll('button'));
        const exportBtn = buttons.find(b => /export data|backup/i.test(b.innerText));
        return exportBtn !== null;
    })()""",
    await_promise=False
)

if export_button_exists:
    print("Export Data button found - testing export functionality")
    
    # Set download directory for the test
    import os
    download_dir = os.path.join(os.getcwd(), "test_downloads")
    os.makedirs(download_dir, exist_ok=True)
    await cdp.set_download_dir(download_dir)
    
    # Click export button
    await cdp.click_text(r"export data|backup", tag="button")
    
    # Wait for download to complete (check for file in download directory)
    import time
    time.sleep(3)
    
    # Verify a file was downloaded
    downloaded_files = os.listdir(download_dir) if os.path.exists(download_dir) else []
    assert len(downloaded_files) > 0, "No file downloaded after export"
    
    print(f"Export successful. Downloaded files: {downloaded_files}")
    
    # Cleanup downloaded files
    for file in downloaded_files:
        os.remove(os.path.join(download_dir, file))
else:
    print("Export Data button not found - skipping export test")
```

**Expected Result:** If Export Data button exists, data is successfully exported and downloaded.

**Bug Detection Points:**
- Export button not working
- Download not starting
- Exported file is empty or corrupted

**Regression Notes:**
- Verify export includes all necessary data
- Check that export format is correct

---

### Step 11: Logout and Verify Session Cleanup
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

# Verify we cannot access settings without login
await cdp.goto("http://localhost:8086/settings")
await cdp.wait_for_js("document.body && document.body.innerText.length > 0", timeout_s=10)

# Should be redirected back to login
current_path = await cdp.eval("location.pathname", await_promise=False)
assert current_path == "/login", f"Expected redirect to /login, got {current_path}"
```

**Expected Result:** Admin is successfully logged out and redirected to login page. Access to settings page is denied.

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
- Restore original settings if test fails mid-execution
- Clean up any downloaded export files
- Verify no orphaned settings remain in database

## Edge Cases to Consider
1. **Invalid Settings Values:** Attempting to set invalid values for settings
2. **Concurrent Settings Changes:** Multiple admins modifying settings simultaneously
3. **Settings Reset:** Testing behavior when settings need to be reset to defaults
4. **Network Issues:** Testing behavior during slow network conditions
5. **Browser Storage:** Testing if settings are cached in localStorage
6. **Settings Validation:** Testing form validation for settings inputs
7. **Settings Permissions:** Verifying non-admin users cannot access settings
8. **Settings Export/Import:** Testing data export and import functionality

## Success Criteria
- Admin can view current system settings
- Admin can modify UI language and theme settings
- Settings persist across page refreshes
- Settings persist across logout/login cycles
- Export data functionality works (if available)
- Proper error handling for invalid inputs
- Session management works correctly (login/logout)
- Protected routes are properly secured

## Related Files
- `src/api/routers/settings.py` - Settings API endpoints
- `src/api/routers/admin.py` - Admin-specific endpoints
- `src/frontend/src/components/SettingsManager.tsx` - Settings UI component
- `scripts/cdp_harness.py` - CDP harness for automation
