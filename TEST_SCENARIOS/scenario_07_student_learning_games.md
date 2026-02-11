# Scenario 07: Student - Learning Games Flow

## Title
Student Learning Games Flow - Complete Learning Activities, Earn Achievements

## Description
This end-to-end test scenario validates the complete learning games workflow for students. It covers viewing learning topics, starting learning activities, completing games, and earning achievements. All interactions are performed through the GUI using Chrome DevTools Protocol (CDP) commands.

## Prerequisites
- Application running at `http://localhost:8086`
- Student user credentials available (set via environment variables `AAC_STUDENT_USERNAME` and `AAC_STUDENT_PASSWORD`)
- Chrome browser with remote debugging enabled on port 9222
- At least one learning activity/game exists in the system

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

### Step 2: Navigate to Learning Page
```python
# Navigate to learning page via sidebar or direct URL
await cdp.goto("http://localhost:8086/learning")
await cdp.wait_for_js("document.body && document.body.innerText.length > 0", timeout_s=10)

# Wait for loading spinner to disappear
await cdp.wait_for_js("!document.querySelector('.animate-spin')", timeout_s=20)

# Verify we're on the learning page
current_path = await cdp.eval("location.pathname", await_promise=False)
assert current_path == "/learning", f"Expected /learning, got {current_path}"

# Verify learning page heading is visible
learning_heading = await cdp.eval(
    """(() => {
        const headings = Array.from(document.querySelectorAll('h1, h2'));
        return headings.find(h => /learning|aprendizaje/i.test(h.innerText));
    })()""",
    await_promise=False
)
assert learning_heading, "Learning page heading not found"
```

**Expected Result:** Learning page loads successfully with the heading visible.

**Bug Detection Points:**
- Page not loading or showing error
- Loading spinner stuck
- Learning heading missing

**Regression Notes:**
- Verify navigation after route changes
- Check that student can access learning page

---

### Step 3: View Available Learning Topics
```python
# Get list of available learning topics/games
topics = await cdp.eval(
    """(() => {
        const topicCards = Array.from(document.querySelectorAll('.topic-card, .learning-game, .activity-card'));
        return topicCards.map(card => {
            const nameEl = card.querySelector('h3, h4, .topic-name');
            const descEl = card.querySelector('.description, .topic-description');
            const progressEl = card.querySelector('.progress, .completion-rate');
            return {
                name: nameEl ? nameEl.innerText.trim() : '',
                description: descEl ? descEl.innerText.trim() : '',
                progress: progressEl ? progressEl.innerText.trim() : ''
            };
        });
    })()""",
    await_promise=False
)

print(f"Found {len(topics)} learning topics:")
for topic in topics:
    print(f"  - {topic['name']}: {topic['progress']}")

# Verify at least one topic is available
assert len(topics) > 0, "No learning topics found on learning page"

# Store the first topic's name for later use
target_topic_name = topics[0]['name']
print(f"Target topic for testing: {target_topic_name}")
```

**Expected Result:** Available learning topics are displayed with names and progress.

**Bug Detection Points:**
- Topics not loading from database
- Topic cards not rendering
- Empty topic list

**Regression Notes:**
- Verify topics are loaded correctly
- Check that progress is calculated correctly
- Verify topic metadata is accurate

---

### Step 4: Start a Learning Activity
```python
# Find and click on the target topic
topic_clicked = await cdp.eval(
    f"""(() => {{
        const cards = Array.from(document.querySelectorAll('.topic-card, .learning-game, .activity-card'));
        const card = cards.find(c => c.innerText.includes('{target_topic_name}'));
        if (!card) return false;
        
        // Click on the topic card
        card.click();
        return true;
    }})()""",
    await_promise=False
)
assert topic_clicked, f"Could not click on topic '{target_topic_name}'"

# Wait for activity to load
await cdp.wait_for_js("document.body && document.body.innerText.length > 0", timeout_s=10)
await cdp.wait_for_js("!document.querySelector('.animate-spin')", timeout_s=20)

# Verify we're on the activity page
current_path = await cdp.eval("location.pathname", await_promise=False)
assert "/learning/" in current_path or "/activity/" in current_path, f"Expected to be on activity page, got {current_path}"

# Verify activity name is displayed
activity_name_displayed = await cdp.eval(
    f"""(() => {{
        const text = document.body.innerText;
        return text.includes('{target_topic_name}');
    }})()""",
    await_promise=False
)
assert activity_name_displayed, f"Activity name '{target_topic_name}' not displayed"

print(f"Started learning activity '{target_topic_name}'")
```

**Expected Result:** Learning activity opens successfully with the activity name displayed.

**Bug Detection Points:**
- Activity not opening
- Activity page not loading correctly
- Activity name not displayed

**Regression Notes:**
- Verify activity loads with correct data
- Check that student has access to the activity
- Verify activity state is initialized

---

### Step 5: View Activity Instructions
```python
# Look for activity instructions
instructions_visible = await cdp.eval(
    """(() => {
        const instructionsEl = document.querySelector('.instructions, .activity-instructions, .game-rules');
        return instructionsEl !== null;
    })()""",
    await_promise=False
)

if instructions_visible:
    # Get the instructions text
    instructions_text = await cdp.eval(
        """(() => {
            const instructionsEl = document.querySelector('.instructions, .activity-instructions, .game-rules');
            return instructionsEl ? instructionsEl.innerText.trim() : '';
        })()""",
        await_promise=False
    )
    
    print(f"Activity instructions: {instructions_text[:100]}...")  # Show first 100 chars
else:
    print("No instructions section found on activity page")
```

**Expected Result:** Activity instructions are displayed (if available).

**Bug Detection Points:**
- Instructions not loading
- Instructions not visible to student

**Regression Notes:**
- Verify instructions are loaded correctly
- Check that instructions are clear and helpful

---

### Step 6: Interact with Learning Activity
```python
# Look for interactive elements in the activity
interactive_elements = await cdp.eval(
    """(() => {
        // Look for buttons, cards, or other interactive elements
        const buttons = Array.from(document.querySelectorAll('button:not([disabled]), .card:not(.disabled), .option'));
        return buttons.map(btn => {
            const textEl = btn.querySelector('.text, .label, button');
            return {
                tag: btn.tagName.toLowerCase(),
                text: textEl ? textEl.innerText.trim() : btn.innerText.trim(),
                clickable: btn.tagName === 'BUTTON' || btn.getAttribute('role') === 'button'
            };
        });
    })()""",
    await_promise=False
)

print(f"Found {len(interactive_elements)} interactive elements:")
for element in interactive_elements[:5]:  # Show first 5 elements
    print(f"  - {element['tag']}: {element['text']}")

# Click on the first interactive element
if len(interactive_elements) > 0:
    element_clicked = await cdp.eval(
        """(() => {
            const elements = Array.from(document.querySelectorAll('button:not([disabled]), .card:not(.disabled), .option'));
            if (elements.length === 0) return false;
            elements[0].click();
            return true;
        })()""",
        await_promise=False
    )
    
    if element_clicked:
        # Wait for activity to respond
        await cdp.wait_for_js("document.body && document.body.innerText.length > 0", timeout_s=5)
        
        print("Interacted with learning activity")
    else:
        print("Could not click on interactive element")
else:
    print("No interactive elements found in activity")
```

**Expected Result:** Student can interact with the learning activity.

**Bug Detection Points:**
- Interactive elements not responding
- Activity not updating after interaction
- Elements not clickable

**Regression Notes:**
- Verify activity interactions work correctly
- Check that feedback is provided
- Verify progress is tracked

---

### Step 7: Complete Multiple Activity Steps
```python
# Try to complete a few more steps in the activity
for i in range(3):
    # Look for clickable elements
    element_clicked = await cdp.eval(
        f"""((step) => {{
            const elements = Array.from(document.querySelectorAll('button:not([disabled]), .card:not(.disabled), .option'));
            // Try to click a different element each time
            const elementIndex = step % elements.length;
            if (elements[elementIndex]) {{
                elements[elementIndex].click();
                return true;
            }}
            return false;
        }})({i + 1})""",
        await_promise=False
    )
    
    if element_clicked:
        # Wait for activity to respond
        await cdp.wait_for_js("document.body && document.body.innerText.length > 0", timeout_s=3)
        
        print(f"Completed activity step {i+1}")
    else:
        print(f"Could not complete activity step {i+1}")
```

**Expected Result:** Student can complete multiple steps in the learning activity.

**Bug Detection Points:**
- Activity steps not progressing
- Activity not responding to interactions
- Progress not being tracked

**Regression Notes:**
- Verify activity progress is tracked correctly
- Check that steps can be completed in order
- Verify activity can be completed

---

### Step 8: View Activity Progress
```python
# Look for progress indicator in the activity
progress_visible = await cdp.eval(
    """(() => {
        const progressEl = document.querySelector('.progress-bar, .activity-progress, .completion-indicator');
        return progressEl !== null;
    })()""",
    await_promise=False
)

if progress_visible:
    # Get the progress value
    progress_value = await cdp.eval(
        """(() => {
            const progressEl = document.querySelector('.progress-bar, .activity-progress, .completion-indicator');
            if (!progressEl) return '';
            
            const valueEl = progressEl.querySelector('.value, .progress-text');
            const barEl = progressEl.querySelector('.bar, .progress-fill');
            return {
                text: valueEl ? valueEl.innerText.trim() : '',
                percentage: barEl ? barEl.style.width || '0%' : '0%'
            };
        })()""",
        await_promise=False
    )
    
    print(f"Activity progress: {progress_value['text']} ({progress_value['percentage']})")
else:
    print("No progress indicator found in activity")
```

**Expected Result:** Activity progress is displayed (if available).

**Bug Detection Points:**
- Progress not displaying
- Progress not updating correctly
- Progress bar not rendering

**Regression Notes:**
- Verify progress is calculated correctly
- Check that progress updates in real-time
- Verify progress is visually accurate

---

### Step 9: Complete the Activity (if possible)
```python
# Look for a complete/finish button
complete_button_exists = await cdp.eval(
    """(() => {
        const buttons = Array.from(document.querySelectorAll('button'));
        const completeBtn = buttons.find(b => 
            /complete|completar|finish|terminar|done|listo/i.test(b.innerText)
        );
        return completeBtn !== null;
    })()""",
    await_promise=False
)

if complete_button_exists:
    # Click the complete button
    await cdp.click_text(r"complete|completar|finish|terminar|done|listo", tag="button")
    
    # Wait for completion to process
    await cdp.wait_for_js("document.body && document.body.innerText.length > 0", timeout_s=10)
    await cdp.wait_for_js("!document.querySelector('.animate-spin')", timeout_s=20)
    
    print("Activity completed")
else:
    print("Complete button not found - activity may require more steps")
```

**Expected Result:** If available, the activity can be completed.

**Bug Detection Points:**
- Complete button not working
- Completion not processing
- Activity not marking as complete

**Regression Notes:**
- Verify completion is saved to database
- Check that achievements are awarded
- Verify progress is updated

---

### Step 10: Check for Achievement Notification
```python
# Look for achievement notification or toast
achievement_notification = await cdp.eval(
    """(() => {
        const notifications = Array.from(document.querySelectorAll('.notification, .toast, .alert'));
        return notifications.find(n => 
            /achievement|logro|badge/i.test(n.innerText)
        );
    })()""",
    await_promise=False
)

if achievement_notification:
    print("Achievement notification displayed!")
else:
    print("No achievement notification found")
```

**Expected Result:** If an achievement is earned, a notification is displayed.

**Bug Detection Points:**
- Achievement notification not showing
- Notification not displaying correctly
- Achievement not being awarded

**Regression Notes:**
- Verify achievement notifications work correctly
- Check that notifications are dismissible
- Verify achievement is saved to database

---

### Step 11: Navigate Back to Learning Page
```python
# Navigate back to learning page
await cdp.goto("http://localhost:8086/learning")
await cdp.wait_for_js("!document.querySelector('.animate-spin')", timeout_s=20)

# Verify we're back on the learning page
current_path = await cdp.eval("location.pathname", await_promise=False)
assert current_path == "/learning", f"Expected /learning, got {current_path}"

# Check if the target topic's progress has updated
topic_progress_updated = await cdp.eval(
    """(() => {
        const cards = Array.from(document.querySelectorAll('.topic-card, .learning-game, .activity-card'));
        return cards.map(card => {
            const nameEl = card.querySelector('h3, h4, .topic-name');
            const progressEl = card.querySelector('.progress, .completion-rate');
            return {
                name: nameEl ? nameEl.innerText.trim() : '',
                progress: progressEl ? progressEl.innerText.trim() : ''
            };
        });
    })()""",
    await_promise=False
)

print(f"Updated topic progress:")
for topic in topic_progress_updated:
    if topic['name'] == target_topic_name:
        print(f"  - {topic['name']}: {topic['progress']}")
```

**Expected Result:** Learning page loads with updated progress for the completed activity.

**Bug Detection Points:**
- Progress not updating
- Page not refreshing correctly
- Progress not persisting

**Regression Notes:**
- Verify progress is saved correctly
- Check that progress updates are visible
- Verify progress is accurate

---

### Step 12: Navigate to Achievements Page
```python
# Navigate to achievements page via sidebar or direct URL
await cdp.goto("http://localhost:8086/achievements")
await cdp.wait_for_js("document.body && document.body.innerText.length > 0", timeout_s=10)

# Wait for loading spinner to disappear
await cdp.wait_for_js("!document.querySelector('.animate-spin')", timeout_s=20)

# Verify we're on the achievements page
current_path = await cdp.eval("location.pathname", await_promise=False)
assert current_path == "/achievements", f"Expected /achievements, got {current_path}"

# Verify achievements page heading is visible
achievements_heading = await cdp.eval(
    """(() => {
        const headings = Array.from(document.querySelectorAll('h1, h2'));
        return headings.find(h => /achievements|logros/i.test(h.innerText));
    })()""",
    await_promise=False
)
assert achievements_heading, "Achievements page heading not found"
```

**Expected Result:** Achievements page loads successfully with the heading visible.

**Bug Detection Points:**
- Page not loading or showing error
- Loading spinner stuck
- Achievements heading missing

**Regression Notes:**
- Verify navigation after route changes
- Check that student can access achievements page

---

### Step 13: View Earned Achievements
```python
# Get list of earned achievements
achievements = await cdp.eval(
    """(() => {
        const achievementItems = Array.from(document.querySelectorAll('.achievement-item, .badge-item, .earned-achievement'));
        return achievementItems.map(item => {
            const nameEl = item.querySelector('.name, .achievement-name');
            const descEl = item.querySelector('.description, .achievement-description');
            const pointsEl = item.querySelector('.points, .achievement-points');
            const iconEl = item.querySelector('.icon, .achievement-icon');
            const dateEl = item.querySelector('.date, .earned-date');
            return {
                name: nameEl ? nameEl.innerText.trim() : '',
                description: descEl ? descEl.innerText.trim() : '',
                points: pointsEl ? pointsEl.innerText.trim() : '',
                icon: iconEl ? iconEl.innerText.trim() : '',
                date: dateEl ? dateEl.innerText.trim() : ''
            };
        });
    })()""",
    await_promise=False
)

print(f"Found {len(achievements)} earned achievements:")
for achievement in achievements:
    print(f"  - {achievement['icon']} {achievement['name']} ({achievement['points']}) - {achievement['date']}")
```

**Expected Result:** Earned achievements are displayed with details.

**Bug Detection Points:**
- Achievements not loading from database
- Achievement items not rendering
- Empty achievement list

**Regression Notes:**
- Verify achievements are loaded correctly
- Check that achievement icons are displayed
- Verify achievement dates are correct

---

### Step 14: View Total Points
```python
# Look for total points display
total_points = await cdp.eval(
    """(() => {
        const pointsEl = document.querySelector('.total-points, .points-summary, .score-display');
        if (!pointsEl) return '';
        return pointsEl.innerText.trim();
    })()""",
    await_promise=False
)

if total_points:
    print(f"Total points: {total_points}")
else:
    print("Total points display not found")
```

**Expected Result:** Total points are displayed (if available).

**Bug Detection Points:**
- Points not displaying
- Points not calculating correctly
- Points not updating

**Regression Notes:**
- Verify points are calculated correctly
- Check that points update with new achievements
- Verify points are accurate

---

### Step 15: View Leaderboard (if available)
```python
# Look for leaderboard section
leaderboard_exists = await cdp.eval(
    """(() => {
        const headings = Array.from(document.querySelectorAll('h2, h3, .section-title'));
        return headings.some(h => /leaderboard|clasificaci/i.test(h.innerText));
    })()""",
    await_promise=False
)

if leaderboard_exists:
    # Get leaderboard entries
    leaderboard = await cdp.eval(
        """(() => {
            const entries = Array.from(document.querySelectorAll('.leaderboard-entry, .ranking-item'));
            return entries.map(entry => {
                const rankEl = entry.querySelector('.rank, .position');
                const nameEl = entry.querySelector('.name, .student-name');
                const pointsEl = entry.querySelector('.points, .score');
                return {
                    rank: rankEl ? rankEl.innerText.trim() : '',
                    name: nameEl ? nameEl.innerText.trim() : '',
                    points: pointsEl ? pointsEl.innerText.trim() : ''
                };
            });
        })()""",
        await_promise=False
    )
    
    print(f"Found {len(leaderboard)} leaderboard entries:")
    for entry in leaderboard:
        print(f"  - {entry['rank']}. {entry['name']}: {entry['points']}")
else:
    print("Leaderboard section not found")
```

**Expected Result:** Leaderboard is displayed with student rankings (if available).

**Bug Detection Points:**
- Leaderboard not loading
- Rankings not calculating correctly
- Student not appearing on leaderboard

**Regression Notes:**
- Verify leaderboard is calculated correctly
- Check that rankings update with new points
- Verify leaderboard is sorted correctly

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
- Verify no orphaned activity progress remains
- Check that achievements are properly saved

## Edge Cases to Consider
1. **No Activities:** Student with no available learning activities
2. **Incomplete Activity:** Student starting but not completing an activity
3. **Multiple Completions:** Completing the same activity multiple times
4. **Achievement Limits:** Reaching achievement limits or caps
5. **Network Issues:** Testing behavior during slow network conditions
6. **Activity Timeout:** Activity timing out during completion
7. **Zero Progress:** Activity with no progress tracking
8. **Large Leaderboard:** Many students on the leaderboard

## Success Criteria
- Student can view available learning topics
- Student can start a learning activity
- Student can interact with the activity
- Student can complete activity steps
- Student can complete the activity (if possible)
- Achievement notifications are displayed when earned
- Activity progress is updated
- Student can view earned achievements
- Student can view total points
- Leaderboard displays correct rankings (if available)
- All UI elements are responsive and accessible
- Proper error handling for missing data
- Session management works correctly (login/logout)

## Related Files
- `src/api/routers/learning.py` - Learning activities API endpoints
- `src/api/routers/achievements.py` - Achievements API endpoints
- `src/frontend/src/components/learning/LearningPage.tsx` - Learning page UI
- `src/frontend/src/components/learning/LearningActivity.tsx` - Learning activity UI
- `src/frontend/src/components/achievements/AchievementsPage.tsx` - Achievements page UI
- `scripts/cdp_harness.py` - CDP harness for automation
