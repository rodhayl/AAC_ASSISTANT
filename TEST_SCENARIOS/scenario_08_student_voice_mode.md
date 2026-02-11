# Scenario 08: Student - Voice Mode Flow

## Title
Student Voice Mode Flow - Use Speech-to-Text and Text-to-Speech Features

## Description
This end-to-end test scenario validates the complete voice mode workflow for students. It covers enabling voice mode, using speech-to-text for input, and using text-to-speech for output. All interactions are performed through the GUI using Chrome DevTools Protocol (CDP) commands.

## Prerequisites
- Application running at `http://localhost:8086`
- Student user credentials available (set via environment variables `AAC_STUDENT_USERNAME` and `AAC_STUDENT_PASSWORD`)
- Chrome browser with remote debugging enabled on port 9222
- Microphone access available (for speech-to-text testing)
- Text-to-speech provider configured (for TTS testing)

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

### Step 3: Open a Communication Board
```python
# Get list of available boards
boards = await cdp.eval(
    """(() => {
        const boardCards = Array.from(document.querySelectorAll('.board-card, [data-testid*="board"]'));
        return boardCards.map(card => {
            const nameEl = card.querySelector('h3, h4, .board-name');
            return nameEl ? nameEl.innerText.trim() : '';
        });
    })()""",
    await_promise=False
)

if len(boards) > 0:
    target_board_name = boards[0]
    
    # Click on the first board
    board_clicked = await cdp.eval(
        f"""(() => {{
            const cards = Array.from(document.querySelectorAll('.board-card, [data-testid*="board"]'));
            const card = cards.find(c => c.innerText.includes('{target_board_name}'));
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
        
        print(f"Opened communication board '{target_board_name}'")
    else:
        print("Could not click on board")
else:
    print("No boards available to open")
```

**Expected Result:** A communication board opens successfully.

**Bug Detection Points:**
- Boards not loading
- Board not opening
- Board view not loading correctly

**Regression Notes:**
- Verify board loads with correct data
- Check that student has read access to board

---

### Step 4: Look for Voice Mode Toggle
```python
# Look for voice mode toggle button
voice_toggle_exists = await cdp.eval(
    """(() => {
        const buttons = Array.from(document.querySelectorAll('button'));
        const voiceBtn = buttons.find(b => 
            /voice|voz|microphone|mic/i.test(b.innerText) ||
            b.getAttribute('aria-label')?.includes('voice') ||
            b.getAttribute('aria-label')?.includes('microphone')
        );
        return voiceBtn !== null;
    })()""",
    await_promise=False
)

if voice_toggle_exists:
    print("Voice mode toggle button found")
else:
    print("Voice mode toggle button not found - voice mode may not be available")
```

**Expected Result:** Voice mode toggle button is visible (if voice mode is available).

**Bug Detection Points:**
- Voice toggle not visible
- Voice mode not accessible

**Regression Notes:**
- Verify voice mode is available when configured
- Check that toggle button is accessible

---

### Step 5: Enable Voice Mode (if available)
```python
if voice_toggle_exists:
    # Click the voice mode toggle button
    voice_clicked = await cdp.eval(
        """(() => {
            const buttons = Array.from(document.querySelectorAll('button'));
            const voiceBtn = buttons.find(b => 
                /voice|voz|microphone|mic/i.test(b.innerText) ||
                b.getAttribute('aria-label')?.includes('voice') ||
                b.getAttribute('aria-label')?.includes('microphone')
            );
            if (voiceBtn) {
                voiceBtn.click();
                return true;
            }
            return false;
        })()""",
        await_promise=False
    )
    
    if voice_clicked:
        # Wait for voice mode to activate
        await cdp.wait_for_js("document.body && document.body.innerText.length > 0", timeout_s=5)
        
        # Check if voice mode is now active
        voice_active = await cdp.eval(
            """(() => {
                const buttons = Array.from(document.querySelectorAll('button'));
                const voiceBtn = buttons.find(b => 
                    /voice|voz|microphone|mic/i.test(b.innerText) ||
                    b.getAttribute('aria-label')?.includes('voice') ||
                    b.getAttribute('aria-label')?.includes('microphone')
                );
                if (!voiceBtn) return false;
                return voiceBtn.classList.contains('active') ||
                       voiceBtn.getAttribute('aria-pressed') === 'true';
            })()""",
            await_promise=False
        )
        
        if voice_active:
            print("Voice mode enabled")
        else:
            print("Voice mode button clicked but may not be active")
    else:
        print("Could not click voice mode toggle")
else:
    print("Skipping voice mode enable - toggle not found")
```

**Expected Result:** Voice mode is enabled and the toggle button shows active state.

**Bug Detection Points:**
- Voice mode not activating
- Toggle button not updating visual state
- Voice mode not requesting microphone permission

**Regression Notes:**
- Verify microphone permission is requested
- Check that voice mode state persists
- Verify voice mode UI is correct

---

### Step 6: Look for Speech-to-Text Input
```python
# Look for speech-to-text input area or microphone button
stt_input_exists = await cdp.eval(
    """(() => {
        // Look for a text input that might be used for speech-to-text
        const textInput = document.querySelector('input[type="text"], textarea, .speech-input');
        // Look for a microphone button for speech input
        const micButton = Array.from(document.querySelectorAll('button')).find(b => 
            b.querySelector('svg[data-icon="microphone"]') ||
            b.querySelector('.mic-icon')
        );
        return textInput !== null || micButton !== null;
    })()""",
    await_promise=False
)

if stt_input_exists:
    print("Speech-to-text input found")
else:
    print("Speech-to-text input not found - STT may not be available")
```

**Expected Result:** Speech-to-text input area is visible (if STT is available).

**Bug Detection Points:**
- STT input not visible
- Microphone button not accessible

**Regression Notes:**
- Verify STT is available when configured
- Check that input area is accessible

---

### Step 7: Test Speech-to-Text (if available)
```python
if stt_input_exists:
    # Look for microphone button
    mic_button_clicked = await cdp.eval(
        """(() => {
            const buttons = Array.from(document.querySelectorAll('button'));
            const micBtn = buttons.find(b => 
                b.querySelector('svg[data-icon="microphone"]') ||
                b.querySelector('.mic-icon')
            );
            if (micBtn) {
                micBtn.click();
                return true;
            }
            return false;
        })()""",
        await_promise=False
    )
    
    if mic_button_clicked:
        # Wait for speech recognition to initialize
        await cdp.wait_for_js("document.body && document.body.innerText.length > 0", timeout_s=3)
        
        # Check if speech recognition is active
        stt_active = await cdp.eval(
            """(() => {
                const buttons = Array.from(document.querySelectorAll('button'));
                const micBtn = buttons.find(b => 
                    b.querySelector('svg[data-icon="microphone"]') ||
                    b.querySelector('.mic-icon')
                );
                if (!micBtn) return false;
                return micBtn.classList.contains('recording') ||
                       micBtn.classList.contains('listening');
            })()""",
            await_promise=False
        )
        
        if stt_active:
            print("Speech-to-text is active/listening")
        else:
            print("Microphone button clicked but may not be recording")
    else:
        print("Could not click microphone button")
else:
    print("Skipping speech-to-text test - input not found")
```

**Expected Result:** Speech-to-text is activated and shows listening state.

**Bug Detection Points:**
- Microphone not activating
- Speech recognition not starting
- Visual state not updating

**Regression Notes:**
- Verify microphone permission is handled
- Check that speech recognition works
- Verify visual feedback is provided

---

### Step 8: Look for Text-to-Speech Controls
```python
# Look for text-to-speak/play button
tts_button_exists = await cdp.eval(
    """(() => {
        const buttons = Array.from(document.querySelectorAll('button'));
        const ttsBtn = buttons.find(b => 
            /speak|hablar|play|reproducir/i.test(b.innerText) ||
            b.getAttribute('aria-label')?.includes('speak') ||
            b.querySelector('svg[data-icon="speaker"]') ||
            b.querySelector('.speaker-icon')
        );
        return ttsBtn !== null;
    })()""",
    await_promise=False
)

if tts_button_exists:
    print("Text-to-speak button found")
else:
    print("Text-to-speak button not found - TTS may not be available")
```

**Expected Result:** Text-to-speak button is visible (if TTS is available).

**Bug Detection Points:**
- TTS button not visible
- TTS not accessible

**Regression Notes:**
- Verify TTS is available when configured
- Check that TTS button is accessible

---

### Step 9: Build a Message for TTS
```python
# Select a few symbols to build a message
for i in range(3):
    symbol_clicked = await cdp.eval(
        f"""((index) => {{
            const symbols = Array.from(document.querySelectorAll('.symbol-cell, .board-symbol, [data-testid*="symbol"]'));
            const symbolIndex = index % symbols.length;
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
        print(f"Added symbol {i+1} to message")
    else:
        print(f"Could not add symbol {i+1}")

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

print(f"Built message for TTS: {built_message}")
```

**Expected Result:** A message is built by selecting symbols.

**Bug Detection Points:**
- Symbols not responding to clicks
- Message not building correctly
- Symbols not appearing in order

**Regression Notes:**
- Verify message building works correctly
- Check that symbol order is maintained

---

### Step 10: Test Text-to-Speech (if available)
```python
if tts_button_exists:
    # Click the speak/play button
    tts_clicked = await cdp.eval(
        """(() => {
            const buttons = Array.from(document.querySelectorAll('button'));
            const ttsBtn = buttons.find(b => 
                /speak|hablar|play|reproducir/i.test(b.innerText) ||
                b.getAttribute('aria-label')?.includes('speak') ||
                b.querySelector('svg[data-icon="speaker"]') ||
                b.querySelector('.speaker-icon')
            );
            if (ttsBtn) {
                ttsBtn.click();
                return true;
            }
            return false;
        })()""",
        await_promise=False
    )
    
    if tts_clicked:
        # Wait for TTS to play
        await cdp.wait_for_js("document.body && document.body.innerText.length > 0", timeout_s=3)
        
        # Check if TTS is playing
        tts_playing = await cdp.eval(
            """(() => {
                const buttons = Array.from(document.querySelectorAll('button'));
                const ttsBtn = buttons.find(b => 
                    /speak|hablar|play|reproducir/i.test(b.innerText) ||
                    b.getAttribute('aria-label')?.includes('speak') ||
                    b.querySelector('svg[data-icon="speaker"]') ||
                    b.querySelector('.speaker-icon')
                );
                if (!ttsBtn) return false;
                return ttsBtn.classList.contains('playing') ||
                       ttsBtn.disabled === true;
            })()""",
            await_promise=False
        )
        
        if tts_playing:
            print("Text-to-speech is playing")
        else:
            print("TTS button clicked but may not be playing")
    else:
        print("Could not click TTS button")
else:
    print("Skipping TTS test - button not found")
```

**Expected Result:** Text-to-speech plays the built message.

**Bug Detection Points:**
- TTS not playing
- Audio not outputting
- Button state not updating

**Regression Notes:**
- Verify TTS integration works correctly
- Check that audio plays without errors
- Verify TTS uses correct language

---

### Step 11: Look for Voice Settings
```python
# Look for voice settings button or menu
voice_settings_exists = await cdp.eval(
    """(() => {
        const buttons = Array.from(document.querySelectorAll('button'));
        const settingsBtn = buttons.find(b => 
            /settings|configuraci/i.test(b.innerText) ||
            b.getAttribute('aria-label')?.includes('settings') ||
            b.querySelector('svg[data-icon="settings"]') ||
            b.querySelector('.settings-icon')
        );
        return settingsBtn !== null;
    })()""",
    await_promise=False
)

if voice_settings_exists:
    print("Voice settings button found")
else:
    print("Voice settings button not found")
```

**Expected Result:** Voice settings button is visible (if available).

**Bug Detection Points:**
- Settings button not visible
- Settings not accessible

**Regression Notes:**
- Verify settings are accessible
- Check that settings button is in correct location

---

### Step 12: Navigate to Settings Page
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

**Expected Result:** Settings page loads successfully with the heading visible.

**Bug Detection Points:**
- Page not loading or showing error
- Loading spinner stuck
- Settings heading missing

**Regression Notes:**
- Verify navigation after route changes
- Check that student can access settings page

---

### Step 13: View Voice/Audio Settings
```python
# Look for voice or audio settings section
voice_settings_section = await cdp.eval(
    """(() => {
        const headings = Array.from(document.querySelectorAll('h2, h3, .section-title'));
        return headings.find(h => 
            /voice|voz|audio|speech/i.test(h.innerText)
        );
    })()""",
    await_promise=False
)

if voice_settings_section:
    # Get voice settings options
    voice_options = await cdp.eval(
        """(() => {
            const section = document.querySelector('.voice-settings, .audio-settings, [data-section*="voice"]');
            if (!section) return [];
            
            const inputs = Array.from(section.querySelectorAll('input, select'));
            return inputs.map(input => {
                const labelEl = input.closest('.form-group')?.querySelector('label');
                return {
                    name: input.name || input.id || '',
                    type: input.type || input.tagName.toLowerCase(),
                    label: labelEl ? labelEl.innerText.trim() : '',
                    value: input.value || ''
                };
            });
        })()""",
        await_promise=False
    )
    
    print(f"Found {len(voice_options)} voice/audio settings:")
    for option in voice_options:
        print(f"  - {option['label']}: {option['value']}")
else:
    print("Voice/audio settings section not found")
```

**Expected Result:** Voice/audio settings are displayed (if available).

**Bug Detection Points:**
- Voice settings not loading
- Settings not displaying correctly
- Settings not editable

**Regression Notes:**
- Verify voice settings are loaded correctly
- Check that settings can be modified

---

### Step 14: Test Voice Settings Modification (if available)
```python
if voice_settings_section and len(voice_options) > 0:
    # Try to modify the first voice setting
    setting_modified = await cdp.eval(
        """(() => {
            const section = document.querySelector('.voice-settings, .audio-settings, [data-section*="voice"]');
            if (!section) return false;
            
            const inputs = Array.from(section.querySelectorAll('input, select'));
            if (inputs.length === 0) return false;
            
            const input = inputs[0];
            if (input.type === 'checkbox') {
                input.click();
                return true;
            } else if (input.tagName === 'SELECT') {
                const options = Array.from(input.options);
                if (options.length > 1) {
                    input.selectedIndex = (input.selectedIndex + 1) % options.length;
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                    return true;
                }
            } else if (input.type === 'range') {
                input.value = Math.min(parseInt(input.value) + 10, parseInt(input.max) || 100);
                input.dispatchEvent(new Event('input', { bubbles: true }));
                return true;
            }
            return false;
        })()""",
        await_promise=False
    )
    
    if setting_modified:
        print("Voice setting modified")
    else:
        print("Could not modify voice setting")
else:
    print("Skipping voice settings modification - section not found")
```

**Expected Result:** Voice settings can be modified (if available).

**Bug Detection Points:**
- Settings not responding to changes
- Settings not saving
- Settings not validating correctly

**Regression Notes:**
- Verify settings are saved correctly
- Check that settings persist across sessions

---

### Step 15: Save Settings Changes (if modified)
```python
if voice_settings_section:
    # Look for save button
    save_button_exists = await cdp.eval(
        """(() => {
            const buttons = Array.from(document.querySelectorAll('button[type="submit"]'));
            const saveBtn = buttons.find(b => /save|guardar/i.test(b.innerText));
            return saveBtn !== null;
        })()""",
        await_promise=False
    )
    
    if save_button_exists:
        # Click the save button
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
        
        if success_message:
            print("Settings saved successfully")
        else:
            print("Settings save completed but no success message found")
    else:
        print("No save button found - settings may auto-save")
else:
    print("Skipping settings save - section not found")
```

**Expected Result:** Settings are saved successfully with a confirmation message.

**Bug Detection Points:**
- Save button not working
- Settings not persisting
- Success message not displaying

**Regression Notes:**
- Verify settings are saved to database
- Check that success message is localized

---

### Step 16: Logout as Student
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
- Verify no orphaned voice settings remain
- Check that microphone permissions are properly handled

## Edge Cases to Consider
1. **No Microphone Access:** Testing behavior when microphone is denied
2. **No TTS Provider:** Testing behavior when TTS is not configured
3. **No STT Provider:** Testing behavior when STT is not configured
4. **Multiple Languages:** Testing voice features with different languages
5. **Voice Settings Limits:** Testing boundary values for voice settings
6. **Concurrent Voice Usage:** Multiple users using voice features simultaneously
7. **Network Issues:** Testing behavior during slow network conditions
8. **Audio Errors:** Testing behavior when audio playback fails

## Success Criteria
- Student can access communication page
- Student can open a communication board
- Voice mode toggle is visible (if available)
- Voice mode can be enabled (if available)
- Speech-to-text input is visible (if STT is available)
- Speech-to-text can be activated (if available)
- Text-to-speak button is visible (if TTS is available)
- Student can build messages with symbols
- Text-to-speech can play messages (if TTS is available)
- Voice settings are accessible (if available)
- Voice settings can be modified (if available)
- Settings can be saved (if modified)
- All UI elements are responsive and accessible
- Proper error handling for missing features
- Session management works correctly (login/logout)

## Related Files
- `src/api/routers/providers.py` - Provider configuration API endpoints
- `src/api/routers/settings.py` - Settings API endpoints
- `src/frontend/src/components/board/CommunicationToolbar.tsx` - Communication toolbar UI
- `src/frontend/src/components/voice/VoiceMode.tsx` - Voice mode UI
- `src/frontend/src/components/SettingsManager.tsx` - Settings UI
- `src/aac_app/providers/local_speech_provider.py` - Local speech provider
- `src/aac_app/providers/local_tts_provider.py` - Local TTS provider
- `scripts/cdp_harness.py` - CDP harness for automation
