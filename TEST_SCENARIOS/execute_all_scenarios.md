# Execute All Test Scenarios - Chrome DevTools Protocol (CDP) Only

## Overview

This prompt instructs an LLM to execute all 10 end-to-end test scenarios located in the `TEST_SCENARIOS` folder using **ONLY** Chrome DevTools Protocol (CDP). No scripting, no workarounds, no API calls - all interactions must be performed through the GUI using CDP commands.

## Test Scenarios to Execute

Execute the following 10 scenarios in order:

| # | Scenario File | Description | Dependencies |
|---|--------------|-------------|--------------|
| 1 | `scenario_01_admin_user_management.md` | Admin User Management Flow | **MUST BE RUN FIRST** - Creates teacher and student users |
| 2 | `scenario_02_admin_system_settings.md` | Admin System Settings | None |
| 3 | `scenario_03_teacher_board_creation_sharing.md` | Teacher Board Creation and Sharing | ⚠️ Requires teacher user from Scenario 01 |
| 4 | `scenario_04_teacher_learning_mode_configuration.md` | Teacher Learning Mode Configuration | ⚠️ Requires teacher user from Scenario 01 |
| 5 | `scenario_05_teacher_student_progress_monitoring.md` | Teacher Student Progress Monitoring | ⚠️ Requires teacher and student users from Scenario 01 |
| 6 | `scenario_06_student_communication_board_usage.md` | Student Communication Board Usage | ⚠️ Requires student user from Scenario 01 |
| 7 | `scenario_07_student_learning_games.md` | Student Learning Games | ⚠️ Requires student user from Scenario 01 |
| 8 | `scenario_08_student_voice_mode.md` | Student Voice Mode | ⚠️ Requires student user from Scenario 01 |
| 9 | `scenario_09_cross_role_board_collaboration.md` | Cross-Role Board Collaboration | ⚠️ Requires teacher and student users from Scenario 01 |
| 10 | `scenario_10_cross_role_achievement_system.md` | Cross-Role Achievement System | ⚠️ Requires teacher and student users from Scenario 01 |

> 🔴 **CRITICAL**: Scenario 01 (Admin User Management) **MUST** be run first to create the teacher and student users. If Scenario 01 fails, scenarios 3-10 cannot be executed properly because they depend on the users created in Scenario 01.

---

## Prerequisites

Before executing any test scenarios, ensure the following:

### Admin Credentials (Pre-configured)

The following admin credentials are **pre-configured** in the system and must be used for admin-level operations:

| Field     | Value      |
|-----------|------------|
| **Username** | `admin1`   |
| **Password** | `Admin123` |

> ⚠️ **IMPORTANT**: These credentials are pre-configured in the database. Do NOT attempt to create a new admin user - use these existing credentials.

### Environment Setup

1. **Application Running**: The AAC Assistant application must be running at `http://localhost:8086`
   - Start the application using the appropriate startup script
   - Verify the application is accessible by navigating to `http://localhost:8086` in a browser

2. **Chrome DevTools Protocol Available**: Chrome browser with remote debugging enabled
   - Start Chrome with remote debugging: `chrome.exe --remote-debugging-port=9222`
   - Verify CDP is accessible by checking `http://localhost:9222/json/version`

3. **Clean Database State**: For accurate testing, start with a clean database
   - Optionally run database reset scripts if available
   - Ensure no test users from previous runs interfere

### User Creation Requirements

**Teacher and student users are NOT pre-configured.** The admin must create these users through the GUI before running scenarios that require those roles:

| User Type | Suggested Username | Suggested Password |
|-----------|-------------------|-------------------|
| Teacher   | `teacher1`        | `Teacher123`      |
| Student   | `student1`        | `Student123`      |

> 📋 **User Creation Instructions**:
> 1. Log in with the admin credentials (`admin1` / `Admin123`)
> 2. Navigate to the user management section
> 3. Create a teacher user using the GUI (e.g., username: `teacher1`, password: `Teacher123`)
> 4. Create a student user using the GUI (e.g., username: `student1`, password: `Student123`)
> 5. All user creation must be done through Chrome DevTools GUI interactions only - no API calls or database inserts

### Required Tools

- Chrome DevTools Protocol (CDP) client library
- Access to the Chrome DevTools MCP server tools
- File system access for creating result files

---

## Execution Instructions

### Test Execution Flow

> 🔴 **CRITICAL EXECUTION ORDER**:
> 
> 1. **Scenario 01 MUST be executed first** - This scenario creates the teacher and student users required by all subsequent scenarios
> 2. **If Scenario 01 fails** - Scenarios 3-10 cannot be run properly because they require the users created in Scenario 01
> 3. **User creation is done via GUI only** - All user creation must be performed through Chrome DevTools GUI interactions, not via API calls or database inserts
> 
> **Execution Flow Diagram**:
> ```
> Scenario 01 (Admin User Management)
>     ├── Admin logs in with: admin1 / Admin123
>     ├── Admin creates teacher user: teacher1 / Teacher123
>     └── Admin creates student user: student1 / Student123
>              │
>              ▼
> Scenarios 02-10 can now run using the users created above
> ```

### Step 1: Create Results Folder

Create a results folder with today's date in the format `results-YYYY-MM-DD`:

```
Folder name: results-2026-02-11 (use current date)
Location: Same directory as TEST_SCENARIOS folder
```

**Instructions:**
1. Get the current date in YYYY-MM-DD format
2. Create the folder if it doesn't exist
3. All result files will be saved to this folder

### Step 2: Execute Each Scenario

For each of the 10 scenarios:

1. **Read the scenario file** from `TEST_SCENARIOS/scenario_XX_*.md`
2. **Follow the test steps exactly** as documented
3. **Use ONLY Chrome DevTools Protocol commands** to interact with the application
4. **Document all actions and results** in a result file

### Step 3: Create Result File for Each Scenario

For each scenario executed, create a result file in the results folder with the following naming convention:

```
File name: result_scenario_XX_name.md
Example: result_scenario_01_admin_user_management.md
```

---

## Result File Template

Each result file must follow this exact format:

```markdown
# Test Result: Scenario XX - [Scenario Name]

## Test Information

- **Scenario Number**: XX
- **Scenario Name**: [Full scenario name from the scenario file]
- **Execution Date**: [YYYY-MM-DD HH:MM:SS UTC]
- **Test Duration**: [Total time taken to execute]
- **Tester**: [LLM/CDP Automated Test]
- **Test Method**: Chrome DevTools Protocol (CDP) - GUI Only

---

## Test Summary

- **Overall Status**: ✅ PASS / ❌ FAIL / ⚠️ PARTIAL
- **Steps Executed**: [Number] / [Total steps in scenario]
- **Bugs Found**: [Number]
- **Critical Issues**: [Number]
- **Performance Issues**: [Number]

---

## Prerequisites Check

- [ ] Application running at http://localhost:8086
- [ ] Chrome DevTools Protocol accessible
- [ ] Admin credentials available (admin1 / Admin123)
- [ ] Database in clean state (if applicable)
- [ ] For Scenarios 3-10: Teacher and student users created in Scenario 01

---

## Steps Executed

### Step 1: [Step Title from Scenario]

**CDP Commands Used:**
```python
[List all CDP commands executed for this step]
```

**Expected Result:**
[Copy expected result from scenario file]

**Actual Result:**
[Describe what actually happened]

**Status**: ✅ PASS / ❌ FAIL

**Notes/Observations:**
[Any additional observations, timing information, or deviations]

---

### Step 2: [Step Title from Scenario]

[Repeat for each step in the scenario]

---

## Bugs and Issues Found

### Bug #1: [Brief Description]

**Severity**: Critical / High / Medium / Low

**Location**: [Page/Component where bug occurred]

**Steps to Reproduce:**
1. [Step 1]
2. [Step 2]
3. [Step 3]

**Expected Behavior:**
[What should happen]

**Actual Behavior:**
[What actually happened]

**Error Messages:**
```
[Copy any error messages or stack traces]
```

**Evidence:**
- [ ] Screenshot captured (filename: screenshot_bug_1.png)
- [ ] Console errors logged
- [ ] Network request failures logged

**How to Test the Fix:**
1. [Step 1 to verify fix]
2. [Step 2 to verify fix]
3. [Step 3 to verify fix]

---

### Bug #2: [Brief Description]

[Repeat for each bug found]

---

## Performance Observations

- [ ] Page load times recorded
- [ ] Slow API responses noted
- [ ] UI rendering delays observed
- [ ] Memory usage patterns (if observable)

**Performance Issues:**
1. [Issue 1 description with timing data]
2. [Issue 2 description with timing data]

---

## Accessibility Issues

- [ ] Missing ARIA labels
- [ ] Keyboard navigation issues
- [ ] Screen reader compatibility issues
- [ ] Color contrast problems

**Accessibility Issues Found:**
1. [Issue 1 description]
2. [Issue 2 description]

---

## Deviations from Expected Steps

[List any steps that could not be executed as documented and explain why]

1. [Deviation 1]: [Reason]
2. [Deviation 2]: [Reason]

---

## Screenshots and Evidence

### Screenshot 1: [Description]
- **File**: screenshot_1.png
- **Context**: [What the screenshot shows]
- **Timestamp**: [When captured]

### Screenshot 2: [Description]
- **File**: screenshot_2.png
- **Context**: [What the screenshot shows]
- **Timestamp**: [When captured]

---

## Console Errors and Warnings

### Error 1:
```
[Error message]
```
- **Timestamp**: [When occurred]
- **Context**: [What action triggered it]

### Warning 1:
```
[Warning message]
```
- **Timestamp**: [When occurred]
- **Context**: [What action triggered it]

---

## Network Request Issues

### Failed Request 1:
- **URL**: [Request URL]
- **Method**: [GET/POST/PUT/DELETE]
- **Status Code**: [HTTP status]
- **Error**: [Error message]
- **Context**: [What action triggered it]

---

## Cleanup Performed

[List cleanup actions taken after the test]

- [ ] Logged out of application
- [ ] Cleared browser data (cookies, localStorage, sessionStorage)
- [ ] Closed browser tabs/pages
- [ ] Reset test data (if applicable)

---

## Recommendations

1. [Recommendation 1 based on test results]
2. [Recommendation 2 based on test results]
3. [Recommendation 3 based on test results]

---

## Conclusion

[Summary of the test execution, overall assessment, and next steps]

**Test Completed At**: [YYYY-MM-DD HH:MM:SS UTC]
```

---

## CDP Commands Reference

When executing scenarios, use the following Chrome DevTools Protocol commands:

### Navigation
- `navigate_page(url)` - Navigate to a URL
- `list_pages()` - List all open pages
- `select_page(pageId)` - Select a page for interaction
- `close_page(pageId)` - Close a page

### Page Interaction
- `take_snapshot()` - Get a text snapshot of the page
- `take_screenshot()` - Capture a screenshot
- `wait_for(text, timeout)` - Wait for text to appear
- `evaluate_script(function)` - Execute JavaScript

### Element Interaction
- `click(uid)` - Click on an element
- `fill(uid, value)` - Fill an input field
- `fill_form(elements)` - Fill multiple form elements
- `hover(uid)` - Hover over an element
- `drag(from_uid, to_uid)` - Drag an element

### Console and Network
- `list_console_messages()` - List console messages
- `get_console_message(msgid)` - Get a specific console message
- `list_network_requests()` - List network requests
- `get_network_request(reqid)` - Get a specific network request

### Emulation
- `emulate(viewport, colorScheme, networkConditions, etc.)` - Emulate device conditions
- `resize_page(width, height)` - Resize the page

### Performance
- `performance_start_trace(reload, autoStop)` - Start performance trace
- `performance_stop_trace()` - Stop performance trace
- `performance_analyze_insight(insightSetId, insightName)` - Analyze performance insights

---

## Important Rules

### MUST DO:
1. ✅ Use ONLY Chrome DevTools Protocol commands for all interactions
2. ✅ Test through the GUI only - no direct API calls
3. ✅ Follow each scenario step-by-step as documented
4. ✅ Document all CDP commands used in the result file
5. ✅ Capture screenshots for bugs and critical issues
6. ✅ Record all error messages and stack traces
7. ✅ Note any UI elements that are missing or not working
8. ✅ Document performance issues or slow responses
9. ✅ Record accessibility issues if encountered
10. ✅ Create a result file for each scenario in the results folder

### MUST NOT DO:
1. ❌ Do NOT use scripting languages (Python, JavaScript, etc.) to bypass the GUI
2. ❌ Do NOT make direct API calls to the backend
3. ❌ Do NOT use database queries to modify data
4. ❌ Do NOT skip steps unless absolutely necessary (document why)
5. ❌ Do NOT modify the application code during testing
6. ❌ Do NOT use workarounds or hacks to bypass bugs
7. ❌ Do NOT assume elements exist - verify with snapshots
8. ❌ Do NOT ignore error messages - document all of them

---

## Error Handling

### If a Test Step Fails:

1. **Document the failure** in the result file with:
   - The exact step that failed
   - Error messages received
   - Screenshot of the failure state
   - Console errors at the time of failure

2. **Attempt recovery** if possible:
   - Take a snapshot to understand current state
   - Try alternative approaches using CDP only
   - Document all recovery attempts

3. **Decision point**:
   - If the failure is critical and prevents continuing → Stop the scenario and mark as FAILED
   - If the failure is non-critical → Continue with remaining steps and mark as PARTIAL

### If a Scenario Fails Completely:

1. Mark the scenario as ❌ FAIL in the result file
2. Document all issues found
3. **Continue to the next scenario** - do not stop the entire test suite
4. Note dependencies between scenarios (if any)

### If the Application Crashes:

1. Document the crash with:
   - Timestamp
   - Last action performed
   - Error messages
   - Screenshot (if possible)

2. Attempt to restart the application
3. If restart is successful, continue with the next scenario
4. If restart fails, stop testing and document the critical failure

---

## Cleanup Between Scenarios

After completing each scenario, perform the following cleanup:

1. **Logout** of the current user session
2. **Clear browser data**:
   - Cookies
   - Local storage
   - Session storage
   - Cache (optional)
3. **Close unnecessary browser tabs** (keep only the main application tab)
4. **Take a final snapshot** to verify clean state
5. **Wait 2-3 seconds** before starting the next scenario

**CDP Commands for Cleanup:**
```python
# Navigate to logout
await cdp.goto("http://localhost:8086/logout")

# Clear browser data
await cdp.clear_origin_data("http://localhost:8086")

# Verify clean state
await cdp.goto("http://localhost:8086/login")
await cdp.wait_for_selector("#username", timeout_s=10)
```

---

## Validation Checkpoints

After each scenario, validate:

- [ ] Result file created in the correct folder
- [ ] Result file follows the template format
- [ ] All steps documented with CDP commands
- [ ] Screenshots captured for bugs (if any)
- [ ] Cleanup performed successfully
- [ ] Ready for next scenario

---

## Expected Output Structure

After executing all 10 scenarios, the results folder should contain:

```
results-YYYY-MM-DD/
├── result_scenario_01_admin_user_management.md
├── result_scenario_02_admin_system_settings.md
├── result_scenario_03_teacher_board_creation_sharing.md
├── result_scenario_04_teacher_learning_mode_configuration.md
├── result_scenario_05_teacher_student_progress_monitoring.md
├── result_scenario_06_student_communication_board_usage.md
├── result_scenario_07_student_learning_games.md
├── result_scenario_08_student_voice_mode.md
├── result_scenario_09_cross_role_board_collaboration.md
├── result_scenario_10_cross_role_achievement_system.md
└── screenshots/
    ├── scenario_01_bug_1.png
    ├── scenario_01_screenshot_1.png
    ├── scenario_02_bug_1.png
    └── ... (additional screenshots as needed)
```

---

## Execution Checklist

Before starting execution:

- [ ] Application is running at http://localhost:8086
- [ ] Chrome DevTools Protocol is accessible
- [ ] Admin credentials are available (admin1 / Admin123)
- [ ] Results folder created with today's date
- [ ] All 10 scenario files are accessible
- [ ] CDP tools are available and functional
- [ ] **Scenario 01 will be run first to create teacher and student users**

During execution:

- [ ] Execute scenarios in order (1-10)
- [ ] **Scenario 01 MUST create teacher and student users via GUI**
- [ ] Follow each step exactly as documented
- [ ] Use ONLY CDP commands
- [ ] Document all actions and results
- [ ] Capture screenshots for issues
- [ ] Perform cleanup between scenarios
- [ ] **Verify users exist before running Scenarios 3-10**

After execution:

- [ ] All 10 result files created
- [ ] Result files follow the template
- [ ] All bugs documented with reproduction steps
- [ ] Screenshots saved for critical issues
- [ ] Summary of test execution available

---

## Example Execution Flow

### Scenario 1 Execution Example (MUST BE RUN FIRST):

1. **Read scenario file**: `TEST_SCENARIOS/scenario_01_admin_user_management.md`
2. **Create result file**: `results-2026-02-11/result_scenario_01_admin_user_management.md`
3. **Execute Step 1 - Admin Login**:
   - Use CDP to navigate to login page
   - Use CDP to fill in admin credentials: `admin1` / `Admin123`
   - Use CDP to click login button
   - Use CDP to verify successful login
   - Document all CDP commands used
   - Take screenshot if issues occur
4. **Execute Step 2 - Create Teacher User**:
   - Use CDP to navigate to user management section
   - Use CDP to create teacher user: `teacher1` / `Teacher123`
   - Use CDP to verify user created successfully
   - Document all CDP commands used
5. **Execute Step 3 - Create Student User**:
   - Use CDP to create student user: `student1` / `Student123`
   - Use CDP to verify user created successfully
   - Document all CDP commands used
6. **Continue** for all steps in the scenario
7. **Document bugs** if any found
8. **Perform cleanup**
9. **Save result file**
10. **Move to Scenario 2**

> ⚠️ **NOTE**: After Scenario 01 completes successfully, the following users should exist:
> - Admin: `admin1` (pre-configured)
> - Teacher: `teacher1` (created in Scenario 01)
> - Student: `student1` (created in Scenario 01)

---

## Troubleshooting

### Issue: CDP Connection Fails

**Symptoms**: Cannot connect to Chrome DevTools Protocol

**Solutions**:
1. Verify Chrome is running with remote debugging: `chrome.exe --remote-debugging-port=9222`
2. Check if port 9222 is available
3. Restart Chrome with remote debugging enabled
4. Verify no firewall is blocking the connection

### Issue: Application Not Responding

**Symptoms**: Pages don't load, timeouts occur

**Solutions**:
1. Check if the application is running: Navigate to http://localhost:8086
2. Check application logs for errors
3. Restart the application if needed
4. Verify database connection is working

### Issue: Elements Not Found

**Symptoms**: CDP commands fail because elements don't exist

**Solutions**:
1. Take a snapshot to see the actual page state
2. Verify the page has fully loaded
3. Check for loading spinners or async content
4. Use `wait_for` to ensure elements are present
5. Document the issue as a potential bug

### Issue: Unexpected Redirects

**Symptoms**: Application redirects to unexpected pages

**Solutions**:
1. Document the expected vs actual redirect
2. Check for authentication issues
3. Verify role-based permissions
4. Document as a bug if redirect is incorrect

---

## Final Notes

- **Accuracy over speed**: Take time to document everything thoroughly
- **Reproducibility**: Ensure bugs can be reproduced by following the documented steps
- **Evidence**: Capture screenshots and logs for all issues
- **Consistency**: Use the same format for all result files
- **Completeness**: Don't skip documentation - even successful tests should be fully documented

---

## Summary

This prompt provides comprehensive instructions for executing all 10 test scenarios using Chrome DevTools Protocol. The LLM should:

1. Create a results folder with today's date
2. **Execute Scenario 01 FIRST** to create teacher and student users using admin credentials (`admin1` / `Admin123`)
3. Execute remaining scenarios in order (2-10) using ONLY CDP commands
4. Create a detailed result file for each scenario following the provided template
5. Document all bugs, issues, and observations
6. Perform proper cleanup between scenarios
7. Continue execution even if individual scenarios fail (except Scenario 01 which is critical)

### Key Credentials Summary

| User Type | Username | Password | Notes |
|-----------|----------|----------|-------|
| Admin | `admin1` | `Admin123` | Pre-configured in system |
| Teacher | `teacher1` | `Teacher123` | Created by admin in Scenario 01 |
| Student | `student1` | `Student123` | Created by admin in Scenario 01 |

### Critical Dependencies

- **Scenario 01** → Creates teacher and student users
- **Scenarios 3-10** → Depend on users created in Scenario 01
- **If Scenario 01 fails** → Scenarios 3-10 cannot run properly

The goal is to provide thorough, reproducible test results that can be used to identify and fix bugs in the AAC Assistant application.
