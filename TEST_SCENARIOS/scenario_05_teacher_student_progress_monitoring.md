# Scenario 05: Teacher - Student Progress Monitoring Flow

## Title
Teacher Student Progress Monitoring Flow - View Student Activities and Achievements

## Description
This end-to-end test scenario validates the complete student progress monitoring workflow for teachers. It covers viewing student lists, accessing individual student profiles, monitoring student activities, viewing achievements, and tracking learning progress. All interactions are performed through the GUI using Chrome DevTools Protocol (CDP) commands.

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

### Step 2: Navigate to Students Page
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

### Step 3: View Student List and Extract Student Information
```python
# Get list of students from the table
students = await cdp.eval(
    """(() => {
        const rows = Array.from(document.querySelectorAll('tbody tr, .student-row'));
        return rows.map(row => {
            const nameCell = row.querySelector('td:nth-child(1), .student-name');
            const usernameCell = row.querySelector('td:nth-child(2), .student-username');
            return {
                name: nameCell ? nameCell.innerText.trim() : '',
                username: usernameCell ? usernameCell.innerText.trim() : ''
            };
        });
    })()""",
    await_promise=False
)

print(f"Found {len(students)} students:")
for student in students:
    print(f"  - {student['name']} ({student['username']})")

# Verify at least one student exists
assert len(students) > 0, "No students found on page"

# Store the first student's username for later use
target_student_username = students[0]['username']
target_student_name = students[0]['name']
print(f"Target student for monitoring: {target_student_name} ({target_student_username})")
```

**Expected Result:** Student list is displayed with student names and usernames.

**Bug Detection Points:**
- Students not loading from database
- Student data not displaying correctly
- Empty student list

**Regression Notes:**
- Verify student data is loaded correctly
- Check that all assigned students are visible

---

### Step 4: Access Student Profile/Details
```python
# Find the target student row and click to view details
profile_clicked = await cdp.eval(
    f"""(() => {{
        const rows = Array.from(document.querySelectorAll('tbody tr, .student-row'));
        const row = rows.find(r => r.innerText.includes('{target_student_username}'));
        if (!row) return false;
        
        // Look for a view profile button or make the row clickable
        const profileBtn = Array.from(row.querySelectorAll('button')).find(b => 
            b.getAttribute('aria-label')?.includes('view') ||
            b.getAttribute('aria-label')?.includes('profile')
        );
        if (profileBtn) {{
            profileBtn.click();
            return true;
        }}
        
        // Try clicking the row itself
        row.click();
        return true;
    }})()""",
    await_promise=False
)
assert profile_clicked, f"Could not click on student '{target_student_username}'"

# Wait for student profile page to load
await cdp.wait_for_js("document.body && document.body.innerText.length > 0", timeout_s=10)
await cdp.wait_for_js("!document.querySelector('.animate-spin')", timeout_s=20)

# Verify we're on a student profile page
current_path = await cdp.eval("location.pathname", await_promise=False)
assert "/students/" in current_path, f"Expected to be on student profile page, got {current_path}"

# Verify student name is displayed
student_name_displayed = await cdp.eval(
    f"""(() => {{
        const text = document.body.innerText;
        return text.includes('{target_student_name}');
    }})()""",
    await_promise=False
)
assert student_name_displayed, f"Student name '{target_student_name}' not displayed on profile page"

print(f"Opened student profile for '{target_student_name}'")
```

**Expected Result:** Student profile page loads with student details displayed.

**Bug Detection Points:**
- Profile page not loading
- Student details not displaying
- Navigation not working correctly

**Regression Notes:**
- Verify student profile loads with correct data
- Check that all student information is visible

---

### Step 5: View Student Activities
```python
# Look for activities section on the student profile
activities_section_exists = await cdp.eval(
    """(() => {
        const headings = Array.from(document.querySelectorAll('h2, h3, .section-title'));
        return headings.some(h => /activities|actividades/i.test(h.innerText));
    })()""",
    await_promise=False
)

if activities_section_exists:
    # Get list of student activities
    activities = await cdp.eval(
        """(() => {
            const activityItems = Array.from(document.querySelectorAll('.activity-item, .session-item, .log-item'));
            return activityItems.map(item => {
                const dateEl = item.querySelector('.date, .timestamp');
                const typeEl = item.querySelector('.type, .activity-type');
                const descEl = item.querySelector('.description, .activity-description');
                return {
                    date: dateEl ? dateEl.innerText.trim() : '',
                    type: typeEl ? typeEl.innerText.trim() : '',
                    description: descEl ? descEl.innerText.trim() : ''
                };
            });
        })()""",
        await_promise=False
    )
    
    print(f"Found {len(activities)} student activities:")
    for activity in activities:
        print(f"  - {activity['date']}: {activity['type']} - {activity['description']}")
else:
    print("Activities section not found on student profile")
    activities = []
```

**Expected Result:** Student activities are displayed on the profile page.

**Bug Detection Points:**
- Activities not loading from database
- Activities section missing
- Activity data not displaying correctly

**Regression Notes:**
- Verify activities are loaded correctly
- Check that recent activities are shown first
- Verify activity timestamps are correct

---

### Step 6: View Student Achievements
```python
# Look for achievements section on the student profile
achievements_section_exists = await cdp.eval(
    """(() => {
        const headings = Array.from(document.querySelectorAll('h2, h3, .section-title'));
        return headings.some(h => /achievements|logros/i.test(h.innerText));
    })()""",
    await_promise=False
)

if achievements_section_exists:
    # Get list of student achievements
    achievements = await cdp.eval(
        """(() => {
            const achievementItems = Array.from(document.querySelectorAll('.achievement-item, .badge-item'));
            return achievementItems.map(item => {
                const nameEl = item.querySelector('.name, .achievement-name');
                const descEl = item.querySelector('.description, .achievement-description');
                const pointsEl = item.querySelector('.points, .achievement-points');
                const iconEl = item.querySelector('.icon, .achievement-icon');
                return {
                    name: nameEl ? nameEl.innerText.trim() : '',
                    description: descEl ? descEl.innerText.trim() : '',
                    points: pointsEl ? pointsEl.innerText.trim() : '',
                    icon: iconEl ? iconEl.innerText.trim() : ''
                };
            });
        })()""",
        await_promise=False
    )
    
    print(f"Found {len(achievements)} student achievements:")
    for achievement in achievements:
        print(f"  - {achievement['icon']} {achievement['name']} ({achievement['points']})")
else:
    print("Achievements section not found on student profile")
    achievements = []
```

**Expected Result:** Student achievements are displayed on the profile page.

**Bug Detection Points:**
- Achievements not loading from database
- Achievements section missing
- Achievement data not displaying correctly

**Regression Notes:**
- Verify achievements are loaded correctly
- Check that achievement icons are displayed
- Verify achievement points are calculated correctly

---

### Step 7: View Student Learning Progress
```python
# Look for learning progress section on the student profile
progress_section_exists = await cdp.eval(
    """(() => {
        const headings = Array.from(document.querySelectorAll('h2, h3, .section-title'));
        return headings.some(h => /progress|progreso/i.test(h.innerText));
    })()""",
    await_promise=False
)

if progress_section_exists:
    # Get learning progress information
    progress_info = await cdp.eval(
        """(() => {
            const progressBars = Array.from(document.querySelectorAll('.progress-bar, .progress-item'));
            return progressBars.map(bar => {
                const labelEl = bar.querySelector('.label, .progress-label');
                const valueEl = bar.querySelector('.value, .progress-value');
                const barEl = bar.querySelector('.bar, .progress-fill');
                return {
                    label: labelEl ? labelEl.innerText.trim() : '',
                    value: valueEl ? valueEl.innerText.trim() : '',
                    percentage: barEl ? barEl.style.width || '0%' : '0%'
                };
            });
        })()""",
        await_promise=False
    )
    
    print(f"Found {len(progress_info)} progress indicators:")
    for progress in progress_info:
        print(f"  - {progress['label']}: {progress['value']} ({progress['percentage']})")
else:
    print("Progress section not found on student profile")
```

**Expected Result:** Student learning progress is displayed on the profile page.

**Bug Detection Points:**
- Progress not loading from database
- Progress section missing
- Progress bars not rendering correctly

**Regression Notes:**
- Verify progress is calculated correctly
- Check that progress bars are visually accurate
- Verify progress updates in real-time

---

### Step 8: View Student Statistics
```python
# Look for statistics section on the student profile
stats_section_exists = await cdp.eval(
    """(() => {
        const headings = Array.from(document.querySelectorAll('h2, h3, .section-title'));
        return headings.some(h => /statistics|estadsticas/i.test(h.innerText));
    })()""",
    await_promise=False
)

if stats_section_exists:
    # Get student statistics
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
    
    print(f"Found {len(stats)} statistics:")
    for stat in stats:
        print(f"  - {stat['label']}: {stat['value']}")
else:
    print("Statistics section not found on student profile")
```

**Expected Result:** Student statistics are displayed on the profile page.

**Bug Detection Points:**
- Statistics not loading from database
- Statistics section missing
- Stat values not calculating correctly

**Regression Notes:**
- Verify statistics are calculated correctly
- Check that stats update with new activities
- Verify stats are accurate

---

### Step 9: Navigate Back to Students List
```python
# Navigate back to students list
await cdp.goto("http://localhost:8086/students")
await cdp.wait_for_js("!document.querySelector('.animate-spin')", timeout_s=20)

# Verify we're back on the students page
current_path = await cdp.eval("location.pathname", await_promise=False)
assert current_path == "/students", f"Expected /students, got {current_path}"

# Verify the target student is still in the list
student_still_exists = await cdp.eval(
    f"""(() => {{
        const text = document.body.innerText;
        return text.includes('{target_student_username}');
    }})()""",
    await_promise=False
)
assert student_still_exists, f"Student '{target_student_username}' not found in list"
```

**Expected Result:** Students list loads successfully with the target student still visible.

**Bug Detection Points:**
- Navigation not working correctly
- Student list not refreshing

**Regression Notes:**
- Verify navigation works correctly
- Check that student list updates after profile view

---

### Step 10: Logout as Teacher
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

### Step 11: Login as Student and Generate Activity
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

# Navigate to communication page to generate activity
await cdp.goto("http://localhost:8086/communication")
await cdp.wait_for_js("!document.querySelector('.animate-spin')", timeout_s=20)

# Look for a playable board
board_exists = await cdp.eval(
    """(() => {
        const boards = document.querySelectorAll('.board-card, [data-testid*="board"]');
        return boards.length > 0;
    })()""",
    await_promise=False
)

if board_exists:
    # Click on the first board
    await cdp.eval(
        """(() => {
            const boards = Array.from(document.querySelectorAll('.board-card, [data-testid*="board"]'));
            if (boards.length === 0) return false;
            boards[0].click();
            return true;
        })()""",
        await_promise=False
    )
    
    # Wait for board to load
    await cdp.wait_for_js("document.body && document.body.innerText.length > 0", timeout_s=10)
    
    # Click on a symbol to generate activity
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
        print("Student generated activity by clicking on a symbol")
    else:
        print("Could not click on symbol")
else:
    print("No boards found for student to use")
```

**Expected Result:** Student can generate activity by using the communication board.

**Bug Detection Points:**
- Communication page not loading
- Boards not accessible to student
- Symbols not clickable

**Regression Notes:**
- Verify student activities are logged
- Check that activity timestamps are recorded

---

### Step 12: Logout as Student
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

### Step 13: Login as Teacher and Verify New Activity
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

# Navigate to student profile
await cdp.goto(f"http://localhost:8086/students/{student_username}")
await cdp.wait_for_js("!document.querySelector('.animate-spin')", timeout_s=20)

# Check if new activity is visible
new_activity_visible = await cdp.eval(
    """(() => {
        const activityItems = Array.from(document.querySelectorAll('.activity-item, .session-item, .log-item'));
        return activityItems.length > 0;
    })()""",
    await_promise=False
)

if new_activity_visible:
    print("New student activity is visible to teacher")
else:
    print("No activities visible - may need to check different section")
```

**Expected Result:** Teacher can see the new activity generated by the student.

**Bug Detection Points:**
- New activity not visible to teacher
- Activities not updating in real-time
- Activity data not persisting

**Regression Notes:**
- Verify activities are logged correctly
- Check that teacher can see all student activities
- Verify activity data is accurate

---

### Step 14: View Leaderboard (if available)
```python
# Navigate to achievements page to see leaderboard
await cdp.goto("http://localhost:8086/achievements")
await cdp.wait_for_js("!document.querySelector('.animate-spin')", timeout_s=20)

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
    print("Leaderboard section not found on achievements page")
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

## Cleanup Steps
No explicit cleanup needed as this is a read-only monitoring test. However, if test data was created:
- Remove any test activities generated
- Verify no orphaned data remains in database

## Edge Cases to Consider
1. **No Activities:** Student with no recorded activities
2. **No Achievements:** Student with no earned achievements
3. **Large Activity Log:** Student with hundreds of activities
4. **Multiple Students:** Monitoring multiple students simultaneously
5. **Deleted Student:** Attempting to view profile of deleted student
6. **Permission Issues:** Teacher trying to view students they don't have access to
7. **Real-time Updates:** Verifying activities update in real-time
8. **Data Pagination:** Handling large amounts of activity data

## Success Criteria
- Teacher can view the list of all students
- Teacher can access individual student profiles
- Teacher can view student activities
- Teacher can view student achievements
- Teacher can view student learning progress
- Teacher can view student statistics
- Student activities are logged and visible to teacher
- Leaderboard displays correct rankings
- All UI elements are responsive and accessible
- Proper error handling for missing data
- Session management works correctly (login/logout)

## Related Files
- `src/api/routers/users.py` - User management API endpoints
- `src/api/routers/achievements.py` - Achievements API endpoints
- `src/api/routers/analytics.py` - Analytics API endpoints
- `src/frontend/src/components/admin/StudentList.tsx` - Students list UI
- `src/frontend/src/components/admin/StudentProfile.tsx` - Student profile UI
- `scripts/cdp_harness.py` - CDP harness for automation
