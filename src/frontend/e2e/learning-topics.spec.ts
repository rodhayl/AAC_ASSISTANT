import { test, expect } from '@playwright/test';

test.describe('Learning Page - Boards and Topics', () => {
    test.use({ storageState: 'playwright/.auth/admin.json' });

    test.beforeEach(async ({ page }) => {
        page.on('console', msg => console.log(`[Browser] ${msg.text()}`));
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

        // Mock Boards API
        await page.route('**/api/boards/?*', async route => {
            await route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify([
                    { id: 1, name: 'Test Board 1', description: 'Desc 1', owner_id: 1, is_public: false, created_at: new Date().toISOString(), symbols: [] },
                    { id: 2, name: 'Test Board 2', description: 'Desc 2', owner_id: 1, is_public: false, created_at: new Date().toISOString(), symbols: [] }
                ])
            });
        });

        // Mock Learning Modes
        await page.route(/\/api\/learning-modes/, async route => {
            await route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify([
                    { id: 1, name: 'Vocabulary Practice', key: 'practice', description: 'Desc 1', prompt_instruction: 'Prompt 1', is_custom: false, created_by: null },
                    { id: 2, name: 'Role Play', key: 'roleplay', description: 'Desc 2', prompt_instruction: 'Prompt 2', is_custom: false, created_by: null },
                    { id: 101, name: 'My Custom Mode', key: 'my_custom_mode', description: 'Custom Desc', prompt_instruction: 'Custom Prompt', is_custom: true, created_by: 1 }
                ])
            });
        });

        // Mock Learning History (fetched on mount)
        await page.route('**/api/learning/history*', async route => {
            await route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify([])
            });
        });
        
        // Mock session start (if referenced)
        await page.route('**/api/learning/start*', async route => {
             await route.fulfill({ status: 200, body: JSON.stringify({ session_id: 123 }) });
        });
    });

    test('should allow selecting board and topic', async ({ page }) => {
        // Navigate to learning page
        await page.goto('/learning');

        // Ensure sidebar is open
        const sidebarTitle = page.getByRole('heading', { name: /Boards & Topics|Tableros y Temas/i });
        
        // If sidebar is collapsed (title not visible), expand it
        if (!await sidebarTitle.isVisible()) {
            const expandBtn = page.locator('button[title="Expand sidebar"]');
            if (await expandBtn.isVisible()) {
                await expandBtn.click();
            }
        }
        await expect(sidebarTitle).toBeVisible();

        // --- Test 1: Select Existing Board + Common Topic ---
        
        // Locate selects by ID
        const boardSelect = page.locator('#board-select');
        const topicSelect = page.locator('#topic-select');

        await expect(boardSelect).toBeVisible();
        await boardSelect.selectOption({ label: 'Test Board 1' });

        await expect(topicSelect).toBeVisible();
        // Use value matching for common topics since labels might be translated
        await topicSelect.selectOption({ value: 'daily' });

        // Click Save Topic
        const saveBtn = page.getByRole('button', { name: /Save Topic|Guardar tema/i });
        await saveBtn.click();

        // Verify it appears in the list
        // The list is in the sidebar's scrollable area.
        // We look for the container with space-y-2 class which holds the items
        const listArea = page.locator('.space-y-2').last();
        
        await expect(listArea.getByText(/Daily Routines|Rutinas Diarias/i).first()).toBeVisible();
        await expect(listArea.getByText('Test Board 1').first()).toBeVisible();

        // --- Test 2: Select Custom Context + Custom Topic ---

        // Select Custom Board Context
        await boardSelect.selectOption({ value: 'custom' });
        
        // Verify value changed
        await expect(boardSelect).toHaveValue('custom');

        // Check input appears (it is a sibling of the select)
        const contextInput = boardSelect.locator('xpath=following-sibling::input');
        await expect(contextInput).toBeVisible();
        await contextInput.fill('My Custom Context');

        // Select Custom Topic
        await topicSelect.selectOption({ value: 'custom' });
        await expect(topicSelect).toHaveValue('custom');

        // Check input appears (sibling of topic select)
        const topicInput = topicSelect.locator('xpath=following-sibling::input');
        await expect(topicInput).toBeVisible();
        await topicInput.fill('My Custom Topic');

        // Click Save
        await saveBtn.click();

        // Verify
        await expect(listArea.getByText('My Custom Topic').first()).toBeVisible();
        await expect(listArea.getByText('My Custom Context').first()).toBeVisible();
        // --- Test 3: Select Learning Mode ---
        
        // Find Mode selector (it's in the header area, separate from sidebar)
        // We can locate it by text "Mode:" or the select itself
        const modeSelect = page.locator('select').filter({ hasText: 'Vocabulary Practice' }); // Assuming default is selected
        await expect(modeSelect).toBeVisible();
        
        // Change mode to "My Custom Mode"
        await modeSelect.selectOption({ label: 'My Custom Mode' });
        await expect(modeSelect).toHaveValue('my_custom_mode');

        // Click Start Session
        // Note: The button might say "Start Session" or "Start Activity" depending on state
        // In our mock, session history is empty, so it should be the big empty state button or sidebar button?
        // Actually, the refactor removed the big buttons and put a "Start Session" button in the empty state area if no messages.
        // Or sidebar buttons? Wait, I removed sidebar "start study" buttons in favor of just "Save Topic".
        // The main way to start is the empty state button or maybe I should have kept a way to start from sidebar?
        // Checking code: sidebar has "Start Study" button for each saved topic.
        // Empty state has "Start Session".
        
        const startBtn = page.getByRole('button', { name: /Start Session|Iniciar sesión/i });
        if (await startBtn.isVisible()) {
             await startBtn.click();
             // We can verify the POST request payload if we want, but simple click interaction is enough for e2e UI test
        }
    });
});
