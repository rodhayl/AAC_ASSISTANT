
import { test, expect, request } from '@playwright/test';

// --- Student Tests ---
test.describe('Voice Mode - Student', () => {
  test.use({ storageState: 'playwright/.auth/student.json' });

  test.beforeEach(async ({ page }) => {
      // Shared state for the mock
      let userSettings = { ui_language: 'en', voice_mode_enabled: true };

      // Mock Auth Me (GET)
      await page.route('**/api/auth/me', async route => {
          if (route.request().method() === 'GET') {
              await route.fulfill({
                  status: 200,
                  contentType: 'application/json',
                  body: JSON.stringify({
                      id: 2,
                      username: 'student',
                      user_type: 'student',
                      display_name: 'Student User',
                      settings: userSettings
                  })
              });
          } else {
              await route.continue();
          }
      });
      
      // Mock Auth Preferences (GET)
      await page.route('**/api/auth/preferences', async route => {
          if (route.request().method() === 'GET') {
              await route.fulfill({
                  status: 200,
                  contentType: 'application/json',
                  body: JSON.stringify(userSettings)
              });
          } else {
              await route.continue();
          }
      });

      // Mock Auth Preferences (PUT) - Update settings
      await page.route('**/api/auth/preferences', async route => {
          if (route.request().method() === 'PUT') {
              const data = route.request().postDataJSON();
              userSettings = { ...userSettings, ...data }; // Update state
              await route.fulfill({
                  status: 200,
                  contentType: 'application/json',
                  body: JSON.stringify(userSettings)
              });
          } else {
             await route.fallback();
          }
      });
  });

  test('Student can toggle their own voice mode persistence', async ({ page }) => {
    await page.goto('/settings');
    
    // 1. Check initial state
    const toggle = page.getByLabel(/voice mode|modo de voz/i);
    // Ensure initial state matches mock (true)
    await expect(toggle).toBeChecked({ timeout: 10000 });
    
    const isChecked = await toggle.isChecked();
    const targetState = !isChecked; // Flip it
    
    // 2. Toggle
    if (targetState) {
        await toggle.check({ force: true });
    } else {
        await toggle.uncheck({ force: true });
    }
    
    // 3. Save
    await page.getByRole('button', { name: /save preferences|guardar preferencias/i }).click();
    await expect(page.getByText(/Saved|Guardado/i).first()).toBeVisible();
    
    // 4. Reload page to verify persistence
    await page.reload();
    await expect(toggle).toBeVisible(); // Check locator validity
    
    // 5. Verify
    if (targetState) {
        await expect(toggle).toBeChecked();
    } else {
        await expect(toggle).not.toBeChecked();
    }
    
    // 6. Navigate away and back
    await page.goto('/dashboard');
    await page.goto('/settings');
    
    if (targetState) {
        await expect(toggle).toBeChecked();
    } else {
        await expect(toggle).not.toBeChecked();
    }
  });
});

// --- Admin Tests ---
test.describe('Voice Mode - Admin', () => {
  test.use({ storageState: 'playwright/.auth/admin.json' });

  test.beforeEach(async ({ page }) => {
      // Shared state
      let userSettings = { ui_language: 'en', voice_mode_enabled: true };

      // Mock Auth Me (GET)
      await page.route('**/api/auth/me', async route => {
          if (route.request().method() === 'GET') {
              await route.fulfill({
                  status: 200,
                  contentType: 'application/json',
                  body: JSON.stringify({
                      id: 1,
                      username: 'admin',
                      user_type: 'admin',
                      display_name: 'Admin User',
                      settings: userSettings
                  })
              });
          } else {
              await route.continue();
          }
      });
      
      // Mock Auth Preferences (GET)
      await page.route('**/api/auth/preferences', async route => {
          if (route.request().method() === 'GET') {
              await route.fulfill({
                  status: 200,
                  contentType: 'application/json',
                  body: JSON.stringify(userSettings)
              });
          } else {
              await route.continue();
          }
      });
      
      // Mock Auth Preferences (PUT)
      await page.route('**/api/auth/preferences', async route => {
          if (route.request().method() === 'PUT') {
              const data = route.request().postDataJSON();
              userSettings = { ...userSettings, ...data };
              await route.fulfill({
                  status: 200,
                  contentType: 'application/json',
                  body: JSON.stringify(userSettings)
              });
          } else {
             await route.fallback();
          }
      });
      
      // Mock Users List (for /students page)
      await page.route('**/api/users/*', async route => {
          if (route.request().method() === 'GET') {
              // Return list of students
              await route.fulfill({
                  status: 200,
                  contentType: 'application/json',
                  body: JSON.stringify({
                      items: [
                          { id: 2, username: 'student1', display_name: 'Student One', user_type: 'student', settings: { voice_mode_enabled: true } }
                      ],
                      total: 1,
                      page: 1,
                      size: 50
                  })
              });
          } else if (route.request().method() === 'PUT') {
              // Update user settings
              const data = route.request().postDataJSON();
              await route.fulfill({
                  status: 200,
                  contentType: 'application/json',
                  body: JSON.stringify({
                      id: 2,
                      username: 'student1',
                      display_name: 'Student One',
                      user_type: 'student',
                      settings: { voice_mode_enabled: data.settings?.voice_mode_enabled }
                  })
              });
          } else {
              await route.continue();
          }
      });
  });

  test('Admin can toggle their own voice mode persistence', async ({ page }) => {
    await page.goto('/settings');
    const toggle = page.getByLabel(/voice mode|modo de voz/i);
    await expect(toggle).toBeChecked({ timeout: 10000 });
    
    const isChecked = await toggle.isChecked();
    const targetState = !isChecked; 
    
    if (targetState) await toggle.check({ force: true }); else await toggle.uncheck({ force: true });
    
    await page.getByRole('button', { name: /save preferences|guardar preferencias/i }).click();
    await expect(page.getByText(/Saved|Guardado/i).first()).toBeVisible();
    
    await page.reload();
    if (targetState) await expect(toggle).toBeChecked(); else await expect(toggle).not.toBeChecked();
  });

  test('Admin can toggle student voice mode', async ({ page }) => {
    await page.goto('/students');
    
    // Click Preferences (Volume/Speaker icon) for the first student
    const preferencesBtn = page.getByRole('button', { name: /preferences/i }).first();
    await preferencesBtn.click();
    
    // Locate modal
    const modal = page.locator('div').filter({ hasText: 'Preferences for' }).last(); 
    await expect(modal).toBeVisible();
    
    // Checkbox is not labeled with 'for' attribute, so get by role
    const toggle = modal.getByRole('checkbox');
    const isChecked = await toggle.isChecked();
    const targetState = !isChecked;
    
    if (targetState) await toggle.check({ force: true }); else await toggle.uncheck({ force: true });
    
    await modal.getByRole('button', { name: /save/i }).click();
    await expect(modal).toBeHidden();
    
    // Re-open to verify
    await preferencesBtn.click();
    await expect(modal).toBeVisible();
    
    // Wait for data load
    await expect(modal.locator('.animate-spin')).toBeHidden();
    
    if (targetState) await expect(toggle).toBeChecked(); else await expect(toggle).not.toBeChecked();
  });
});

// --- Teacher Tests ---
test.describe('Voice Mode - Teacher', () => {
  test.use({ storageState: 'playwright/.auth/admin.json' });

  test('Teacher can toggle their own voice mode', async ({ page }) => {
    // API Helper to create teacher using Admin's token from browser context
    const teacherUsername = `teacher_vm_${Date.now()}`;
    const teacherPassword = 'Teacher123!';
    
    // Get token from browser localStorage
    await page.goto('/'); // Ensure we are on a page to access localStorage
    const token = await page.evaluate(() => {
        const auth = localStorage.getItem('auth-storage');
        if (auth) {
            const parsed = JSON.parse(auth);
            return parsed.state?.token;
        }
        return null;
    });
    
    // Create new API context with token
    const apiContext = await request.newContext({
        baseURL: 'http://localhost:8086',
        extraHTTPHeaders: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
        }
    });
    
    // Step 1: Create user via Admin API
    const createRes = await apiContext.post('/api/auth/admin/create-user', {
        data: {
            username: teacherUsername,
            password: teacherPassword,
            confirm_password: teacherPassword,
            display_name: 'Test Teacher',
            user_type: 'teacher',
            email: `${teacherUsername}@test.com`
        }
    });
    
    // If admin create endpoint works
    if (!createRes.ok()) {
         console.log('Admin Create User failed:', await createRes.text());
         // Fallback to Register + Promote
         const regRes = await apiContext.post('/api/auth/register', {
            data: {
                username: teacherUsername,
                password: teacherPassword,
                display_name: 'Test Teacher',
                email: `${teacherUsername}@test.com`
            }
        });
        expect(regRes.ok()).toBeTruthy();
        const newUser = await regRes.json();
        
        const updateRes = await apiContext.put(`/api/auth/users/${newUser.id}`, {
            data: { user_type: 'teacher' }
        });
        expect(updateRes.ok()).toBeTruthy();
    } else {
        expect(createRes.ok()).toBeTruthy();
    }
    
   // Step 3: Logout Admin and Login as Teacher
    await page.goto('/login');
    await page.evaluate(() => {
        localStorage.clear();
        localStorage.setItem('i18nextLng', 'en');
        localStorage.setItem('aac_assistant_locale', 'en');
    });
    await page.reload();
    
    await page.locator('#username').fill(teacherUsername);await page.locator('#password').fill(teacherPassword);
    await page.locator('button[type="submit"]').click();
    await page.waitForURL('/');
    
    // 4. Verify Teacher Settings (Self)
    await page.goto('/settings');
    // Checkbox might be labeled "Voice Mode" or "Modo de voz"
    const toggle = page.getByRole('checkbox').first();
    // Verify it is the right one by checking text near it
    await expect(page.locator('body')).toHaveText(/voice mode|modo de voz/i);
    
    const isChecked = await toggle.isChecked();// Toggle
    const targetState = !isChecked;
    // Click the label wrapper to ensure React event triggers
    await toggle.locator('..').click(); 
    
    // Verify immediate state change
    if (targetState) await expect(toggle).toBeChecked(); else await expect(toggle).not.toBeChecked();
    
    await page.getByRole('button', { name: /save|guardar/i }).click();
    await expect(page.getByText(/saved|guardado/i).first()).toBeVisible();
    await page.reload();
    
    if (targetState) await expect(toggle).toBeChecked(); else await expect(toggle).not.toBeChecked();
  });
});
