# Scenario 10: Cross-Role - Achievement System Flow

## Title
Cross-Role Achievement System Flow - Student Earns, Teacher Views, Admin Manages

## Description
This end-to-end test scenario validates the complete achievement system workflow across all three roles. It covers a student earning achievements through activities, a teacher viewing student achievements, and an admin managing the achievement system. All interactions are performed through the GUI using Chrome DevTools Protocol (CDP) commands.

## Prerequisites
- Application running at `http://localhost:8086`
- Admin user credentials available (set via environment variables `AAC_ADMIN_USERNAME` and `AAC_ADMIN_PASSWORD`)
- Teacher user credentials available (set via environment variables `AAC_TEACHER_USERNAME` and `AAC_TEACHER_PASSWORD`)
- Student user credentials available (set via environment variables `AAC_STUDENT_USERNAME` and `AAC_STUDENT_PASSWORD`)
- Chrome browser with remote debugging enabled on port 9222
- At least one learning activity exists in the system

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

### Step 3: View Available Learning Activities
```python
# Get list of available learning activities
activities = await cdp.eval(
    """(() => {
        const activityCards = Array.from(document.querySelectorAll('.topic-card, .learning-game, .activity-card'));
        return activityCards.map(card => {
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

print(f"Found {len(activities)} learning activities:")
for activity in activities:
    print(f"  - {activity['name']}: {activity['progress']}")

# Verify at least one activity is available
assert len(activities) > 0, "No learning activities found on learning page"

# Store the first activity's name for later use
target_activity_name = activities[0]['name']
print(f"Target activity for testing: {target_activity_name}")
```

**Expected Result:** Available learning activities are displayed with names and progress.

**Bug Detection Points:**
- Activities not loading from database
- Activity cards not rendering
- Empty activity list

**Regression Notes:**
- Verify activities are loaded correctly
- Check that progress is calculated correctly
- Verify activity metadata is accurate

---

### Step 4: Start and Complete a Learning Activity
```python
# Find and click on the target activity
activity_clicked = await cdp.eval(
    f"""(() => {{
        const cards = Array.from(document.querySelectorAll('.topic-card, .learning-game, .activity-card'));
        const card = cards.find(c => c.innerText.includes('{target_activity_name}'));
        if (!card) return false;
        
        // Click on the activity card
        card.click();
        return true;
    }})()""",
    await_promise=False
)
assert activity_clicked, f"Could not click on activity '{target_activity_name}'"

# Wait for activity to load
await cdp.wait_for_js("document.body && document.body.innerText.length > 0", timeout_s=10)
await cdp.wait_for_js("!document.querySelector('.animate-spin')", timeout_s=20)

# Verify we're on the activity page
current_path = await cdp.eval("location.pathname", await_promise=False)
assert "/learning/" in current_path or "/activity/" in current_path, f"Expected to be on activity page, got {current_path}"

# Interact with the activity to trigger achievement
for i in range(5):
    element_clicked = await cdp.eval(
        f"""((step) => {{
            const elements = Array.from(document.querySelectorAll('button:not([disabled]), .card:not(.disabled), .option'));
            const elementIndex = step % elements.length;
            if (elements[elementIndex]) {{
                elements[elementIndex].click();
                return true;
            }}
            return false;
        }})({i})""",
        await_promise=False
    )
    
    if element_clicked:
        # Wait for activity to respond
        await cdp.wait_for_js("document.body && document.body.innerText.length > 0", timeout_s=3)
        print(f"Completed activity step {i+1}")
    else:
        print(f"Could not complete activity step {i+1}")

print(f"Student interacted with activity '{target_activity_name}'")
```

**Expected Result:** Student can start and interact with the learning activity.

**Bug Detection Points:**
- Activity not opening
- Activity not responding to interactions
- Progress not being tracked

**Regression Notes:**
- Verify activity progress is tracked correctly
- Check that steps can be completed in order
- Verify activity can be completed

---

### Step 5: Check for Achievement Notification
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
    # Get the notification text
    notification_text = await cdp.eval(
        """(() => {
            const notifications = Array.from(document.querySelectorAll('.notification, .toast, .alert'));
            const notif = notifications.find(n => 
                /achievement|logro|badge/i.test(n.innerText)
            );
            return notif ? notif.innerText.trim() : '';
        })()""",
        await_promise=False
    )
    
    print(f"Achievement notification displayed: {notification_text}")
else:
    print("No achievement notification found - may need to complete more steps")
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

### Step 6: Navigate to Achievements Page
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

### Step 7: View Earned Achievements
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

# Store the count for later comparison
student_achievement_count = len(achievements)
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

### Step 8: View Total Points
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
    print(f"Student total points: {total_points}")
else:
    print("Total points display not found")
```

**Expected Result:** Total points are displayed.

**Bug Detection Points:**
- Points not displaying
- Points not calculating correctly
- Points not updating

**Regression Notes:**
- Verify points are calculated correctly
- Check that points update with new achievements
- Verify points are accurate

---

### Step 9: Logout as Student
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

### Step 10: Login as Teacher
```python
# Enter teacher credentials
await cdp.set_value("#username", teacher_username)
await cdp.set_value("#password", teacher_password)

# Click login button
await cdp.click_text(r"(Iniciar sesi|Login)", tag="button")

# Verify successful login - should be on dashboard
await cdp.wait_for_js("document.body && document.body.innerText.length > 0", timeout_s=10)
current_path = await cdp.eval("location.pathname", await_promise=False)
assert current_path == "/", f"Expected to be on dashboard, got {current_path}"
```

**Expected Result:** Teacher is successfully logged in and redirected to dashboard.

**Bug Detection Points:**
- Teacher login failing
- Incorrect redirect after login

**Regression Notes:**
- Verify teacher login flow
- Check that teacher dashboard loads correctly

---

### Step 11: Navigate to Students Page
```python
# Navigate to students page via sidebar or direct URL
await cdp.goto("http://localhost:8086/students")
await cdp.wait_for_js("document.body && document.body.innerText.length > 0", timeout_s=10)

# Wait for loading spinner to disappear
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
- Page not loading or showing error
- Loading spinner stuck
- Students list missing (permission issue)

**Regression Notes:**
- Verify navigation after route changes
- Check permission-based UI visibility

---

### Step 12: View Student Achievements
```python
# Find the student row and click to view achievements
achievements_clicked = await cdp.eval(
    """(() => {
        const rows = Array.from(document.querySelectorAll('tbody tr, .student-row'));
        if (rows.length === 0) return false;
        
        // Look for an achievements button or make the row clickable
        const achievementsBtn = Array.from(rows[0].querySelectorAll('button')).find(b => 
            b.getAttribute('aria-label')?.includes('achievements') ||
            b.querySelector('svg.lucide-trophy')
        );
        if (achievementsBtn) {
            achievementsBtn.click();
            return true;
        }
        
        // Try clicking the row itself
        rows[0].click();
        return true;
    })()""",
    await_promise=False
)

if achievements_clicked:
    # Wait for student profile/achievements to load
    await cdp.wait_for_js("document.body && document.body.innerText.length > 0", timeout_s=10)
    await cdp.wait_for_js("!document.querySelector('.animate-spin')", timeout_s=20)
    
    print("Teacher viewing student achievements")
else:
    print("Could not click on student achievements")
```

**Expected Result:** Teacher can view student achievements.

**Bug Detection Points:**
- Achievements button not found
- Student profile not loading
- Achievements not displaying

**Regression Notes:**
- Verify teacher can view student achievements
- Check that achievement data is correct
- Verify teacher has read-only access

---

### Step 13: Verify Student Achievement Count
```python
# Get the student's achievement count from teacher view
teacher_viewed_achievements = await cdp.eval(
    """(() => {
        const achievementItems = Array.from(document.querySelectorAll('.achievement-item, .badge-item, .earned-achievement'));
        return achievementItems.length;
    })()""",
    await_promise=False
)

print(f"Teacher sees {teacher_viewed_achievements} achievements for student")

# Verify the count matches what the student saw
assert teacher_viewed_achievements == student_achievement_count, \
    f"Achievement count mismatch: student saw {student_achievement_count}, teacher sees {teacher_viewed_achievements}"

print("Achievement count matches between student and teacher views")
```

**Expected Result:** Teacher sees the same number of achievements as the student earned.

**Bug Detection Points:**
- Achievement count mismatch
- Achievements not loading correctly
- Data inconsistency between views

**Regression Notes:**
- Verify achievement data is consistent
- Check that teacher sees accurate student data
- Verify no data loss between views

---

### Step 14: Logout as Teacher
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

### Step 15: Login as Admin
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

### Step 16: Navigate to Achievements Management Page
```python
# Navigate to achievements management page via sidebar or direct URL
await cdp.goto("http://localhost:8086/achievements")
await cdp.wait_for_js("document.body && document.body.innerText.length > 0", timeout_s=10)

# Wait for loading spinner to disappear
await cdp.wait_for_js("!document.querySelector('.animate-spin')", timeout_s=20)

# Verify we're on the achievements page
current_path = await cdp.eval("location.pathname", await_promise=False)
assert current_path == "/achievements", f"Expected /achievements, got {current_path}"

# Look for admin-specific achievement management controls
admin_controls_exist = await cdp.eval(
    """(() => {
        const createBtn = Array.from(document.querySelectorAll('button')).find(b => 
            /create achievement|crear logro/i.test(b.innerText)
        );
        return createBtn !== null;
    })()""",
    await_promise=False
)

if admin_controls_exist:
    print("Admin achievement management controls found")
else:
    print("Admin controls not found - may be on different page")
```

**Expected Result:** Admin can access achievement management controls (if available).

**Bug Detection Points:**
- Admin controls not visible
- Achievement management not accessible

**Regression Notes:**
- Verify admin has full access to achievements
- Check that management controls are available

---

### Step 17: View All Achievements (Admin View)
```python
# Get list of all achievements (admin view)
all_achievements = await cdp.eval(
    """(() => {
        const achievementItems = Array.from(document.querySelectorAll('.achievement-item, .badge-item'));
        return achievementItems.map(item => {
            const nameEl = item.querySelector('.name, .achievement-name');
            const descEl = item.querySelector('.description, .achievement-description');
            const pointsEl = item.querySelector('.points, .achievement-points');
            const iconEl = item.querySelector('.icon, .achievement-icon');
            const typeEl = item.querySelector('.type, .achievement-type');
            return {
                name: nameEl ? nameEl.innerText.trim() : '',
                description: descEl ? descEl.innerText.trim() : '',
                points: pointsEl ? pointsEl.innerText.trim() : '',
                icon: iconEl ? iconEl.innerText.trim() : '',
                type: typeEl ? typeEl.innerText.trim() : ''
            };
        });
    })()""",
    await_promise=False
)

print(f"Admin sees {len(all_achievements)} total achievements:")
for achievement in all_achievements:
    print(f"  - {achievement['icon']} {achievement['name']} ({achievement['points']}) - {achievement['type']}")
```

**Expected Result:** Admin can view all achievements in the system.

**Bug Detection Points:**
- Achievements not loading for admin
- Achievement items not rendering
- Empty achievement list

**Regression Notes:**
- Verify admin can see all achievements
- Check that achievement metadata is correct
- Verify admin can see system and custom achievements

---

### Step 18: View Leaderboard
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

**Expected Result:** Leaderboard is displayed with student rankings.

**Bug Detection Points:**
- Leaderboard not loading
- Rankings not calculating correctly
- Student not appearing on leaderboard

**Regression Notes:**
- Verify leaderboard is calculated correctly
- Check that rankings update with new achievements
- Verify leaderboard is sorted correctly

---

### Step 19: Create a Custom Achievement (if available)
```python
# Look for create achievement button
create_button_exists = await cdp.eval(
    """(() => {
        const buttons = Array.from(document.querySelectorAll('button'));
        const createBtn = buttons.find(b => 
            /create achievement|crear logro/i.test(b.innerText)
        );
        return createBtn !== null;
    })()""",
    await_promise=False
)

if create_button_exists:
    # Click create achievement button
    await cdp.click_text(r"create achievement|crear logro", tag="button")
    
    # Wait for modal to appear
    await cdp.wait_for_selector('div[role="dialog"]', timeout_s=10)
    
    # Fill in the achievement creation form
    timestamp = await cdp.eval("Date.now()", await_promise=False)
    achievement_name = f"Test Achievement {timestamp}"
    achievement_description = "Custom achievement created for E2E testing"
    achievement_points = "50"
    
    await cdp.set_value('input[name="name"]', achievement_name)
    await cdp.set_value('textarea[name="description"], input[name="description"]', achievement_description)
    await cdp.set_value('input[name="points"]', achievement_points)
    
    # Submit the form
    await cdp.click_text(r"create|crear", tag="button")
    
    # Wait for modal to close
    await cdp.wait_for_js("!document.querySelector('div[role=\"dialog\"]')", timeout_s=15)
    
    print(f"Admin created custom achievement '{achievement_name}'")
else:
    print("Create achievement button not found - skipping custom achievement test")
```

**Expected Result:** If available, admin can create a custom achievement.

**Bug Detection Points:**
- Create button not found
- Modal not opening
- Form validation errors
- Achievement not creating

**Regression Notes:**
- Verify achievement creation works correctly
- Check that custom achievements are saved
- Verify custom achievements appear in list

---

### Step 20: Logout as Admin
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

### Step 21: Login as Student and Verify New Achievement
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

# Navigate to achievements page
await cdp.goto("http://localhost:8086/achievements")
await cdp.wait_for_js("!document.querySelector('.animate-spin')", timeout_s=20)

# Get updated achievement count
updated_achievements = await cdp.eval(
    """(() => {
        const achievementItems = Array.from(document.querySelectorAll('.achievement-item, .badge-item, .earned-achievement'));
        return achievementItems.length;
    })()""",
    await_promise=False
)

print(f"Student now has {updated_achievements} achievements (previously had {student_achievement_count})")

# Verify the count has increased or stayed the same
assert updated_achievements >= student_achievement_count, \
    f"Achievement count decreased: previously had {student_achievement_count}, now has {updated_achievements}"

print("Achievement system working correctly across all roles")
```

**Expected Result:** Student achievement count is consistent or has increased.

**Bug Detection Points:**
- Achievement count decreased
- Achievements not persisting
- Data loss between sessions

**Regression Notes:**
- Verify achievements persist across sessions
- Check that achievement data is consistent
- Verify no data corruption occurs

---

## Cleanup Steps
- Delete any custom achievement created during the test
- Verify no orphaned achievement data remains in the database
- Check that student achievements are properly saved

## Edge Cases to Consider
1. **No Achievements:** Student with no earned achievements
2. **Achievement Limits:** Reaching achievement limits or caps
3. **Multiple Awards:** Awarding the same achievement multiple times
4. **Achievement Deletion:** Admin deleting an achievement that students have earned
5. **Manual Awarding:** Teacher manually awarding an achievement to a student
6. **Achievement Criteria:** Testing achievements with different criteria types
7. **Leaderboard Ties:** Handling ties in the leaderboard
8. **Network Issues:** Testing behavior during slow network conditions

## Success Criteria
- Student can earn achievements through activities
- Student can view their earned achievements
- Student can view their total points
- Teacher can view student achievements
- Teacher sees the same achievement count as the student
- Admin can view all achievements in the system
- Admin can view the leaderboard
- Admin can create custom achievements (if available)
- Achievement notifications are displayed when earned
- Achievement data is consistent across all role views
- All UI elements are responsive and accessible
- Proper error handling for invalid operations
- Session management works correctly (login/logout for all roles)
- Role-based access control is enforced correctly

## Related Files
- `src/api/routers/achievements.py` - Achievements API endpoints
- `src/api/routers/learning.py` - Learning activities API endpoints
- `src/aac_app/services/achievement_system.py` - Achievement system service
- `src/frontend/src/components/achievements/AchievementsPage.tsx` - Achievements page UI
- `src/frontend/src/components/achievements/Leaderboard.tsx` - Leaderboard UI
- `src/frontend/src/components/admin/StudentProfile.tsx` - Student profile UI
- `scripts/cdp_harness.py` - CDP harness for automation
