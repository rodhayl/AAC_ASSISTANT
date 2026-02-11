import { test, expect } from '@playwright/test';

test.describe('Learning Modes Settings', () => {
  test.use({ storageState: 'playwright/.auth/admin.json' });

  test.beforeEach(async ({ page }) => {
    // Mock Auth Me to ensure we are admin
    await page.route('**/api/auth/me', async route => {
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
                id: 1,
                username: 'admin',
                user_type: 'admin',
                display_name: 'Admin User',
                settings: { ui_language: 'en' }
            })
        });
    });

    // Mock initial modes
    await page.route('**/api/learning-modes/', async route => {
       await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
              { id: 1, name: 'Vocabulary Practice', key: 'practice', description: 'Learn new words', prompt_instruction: 'Default Prompt', is_custom: false, created_by: null }
          ])
       });
    });
  });

  test('should display existing learning modes', async ({ page }) => {
    await page.goto('/settings');
    await expect(page.getByRole('heading', { name: 'Learning Modes' })).toBeVisible();
    await expect(page.getByText('Vocabulary Practice')).toBeVisible();
    await expect(page.getByText('System Default')).toBeVisible();
  });

  test('should allow creating a new learning mode', async ({ page }) => {
    let created = false;
    
    // Use regex to be robust
    await page.route(/\/api\/learning-modes/, async route => {
        const method = route.request().method();
        console.log(`[Mock] ${method} ${route.request().url()}`);
        
        if (method === 'POST') {
             created = true;
             console.log('[Mock] Setting created = true');
             const data = route.request().postDataJSON();
             await route.fulfill({
                 status: 200,
                 contentType: 'application/json',
                 body: JSON.stringify({
                     id: 101,
                     ...data,
                     is_custom: true,
                     created_by: 1,
                     created_at: new Date().toISOString()
                 })
             });
        } else if (method === 'GET') {
            console.log(`[Mock] GET request. Created: ${created}`);
            if (!created) { // First fetch on mount
                 await route.fulfill({
                    status: 200,
                    contentType: 'application/json',
                    body: JSON.stringify([
                        { id: 1, name: 'Vocabulary Practice', key: 'practice', description: 'Learn new words', prompt_instruction: 'Default Prompt', is_custom: false, created_by: null }
                    ])
                 });
            } else { // Subsequent fetches (after save)
                await route.fulfill({
                    status: 200,
                    contentType: 'application/json',
                    body: JSON.stringify([
                        { id: 1, name: 'Vocabulary Practice', key: 'practice', description: 'Learn new words', prompt_instruction: 'Default Prompt', is_custom: false, created_by: null },
                        { id: 101, name: 'New Mode', key: 'new_mode', description: 'New Desc', prompt_instruction: 'New Prompt', is_custom: true, created_by: 1 }
                    ])
                 });
            }
        } else {
            await route.continue();
        }
    });

    await page.goto('/settings');
    
    // Click Add New
    await page.getByRole('button', { name: /Add New Learning Mode/i }).click();
    
    // Fill Form
    await page.getByPlaceholder('e.g. Daily Conversation').fill('New Mode');
    await page.getByPlaceholder('e.g. daily_conversation').fill('new_mode');
    await page.getByPlaceholder('Brief description').fill('New Desc');
    await page.getByPlaceholder('Instructions for the AI').fill('New Prompt');
    
    // Save
    await page.getByRole('button', { name: 'Save Mode' }).click();
    
    // Verify success
    await expect(page.getByText('Mode created successfully')).toBeVisible();
    await expect(page.getByText('New Mode', { exact: true })).toBeVisible();
  });

  test('should allow editing a custom learning mode', async ({ page }) => {
     // Mock initial modes with a custom one
    await page.route('**/api/learning-modes/', async route => {
       await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
              { id: 101, name: 'My Mode', key: 'my_mode', description: 'Desc', prompt_instruction: 'Prompt', is_custom: true, created_by: 1 }
          ])
       });
    });

    // Mock PUT
    await page.route('**/api/learning-modes/101', async route => {
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
                id: 101, name: 'My Mode Updated', key: 'my_mode', description: 'Desc Updated', prompt_instruction: 'Prompt Updated', is_custom: true, created_by: 1
            })
        });
    });

    await page.goto('/settings');
    
    // Use .first() to be safe against the strict mode error
    const modeRow = page.locator('div.border.border-gray-200').filter({ hasText: 'My Mode' }).first();
    await expect(modeRow).toBeVisible();
    
    const editBtn = modeRow.locator('button').first();
    await expect(editBtn).toBeVisible();
    await editBtn.click();
    
    // Edit Form
    await page.getByPlaceholder('e.g. Daily Conversation').fill('My Mode Updated');
    await page.getByPlaceholder('Brief description').fill('Desc Updated');
    
    // Key should be disabled
    await expect(page.getByPlaceholder('e.g. daily_conversation')).toBeDisabled();

    // Save
    await page.getByRole('button', { name: 'Save Mode' }).click();
    
    // Verify success
    await expect(page.getByText('Mode updated successfully')).toBeVisible();
  });
});
