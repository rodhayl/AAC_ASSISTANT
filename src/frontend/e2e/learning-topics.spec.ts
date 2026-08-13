import { test, expect } from '@playwright/test';

test.describe('Learning Page - Boards and Topics', () => {
    test.use({ storageState: 'playwright/.auth/admin.json' });

    test.beforeEach(async ({ page }) => {
        // Only LLM-backed question generation is mocked. Boards, learning
        // modes, history, and session persistence all hit the real backend.
        await page.route('**/api/learning/*/ask', async route => {
            await route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({
                    success: true,
                    question_id: 1,
                    question_text: 'Mock question',
                    choices: ['Choice A', 'Choice B', 'Choice C'],
                    correct_answer_index: 0
                })
            });
        });
    });

    test('should allow selecting board and topic and starting a session', async ({ page }) => {
        await page.goto('/learning');

        const sidebarTitle = page.getByRole('heading', { name: /Boards & Topics|Tableros y Temas/i });
        if (!await sidebarTitle.isVisible()) {
            const expandBtn = page.locator('button[title="Expand sidebar"]');
            if (await expandBtn.isVisible()) {
                await expandBtn.click();
            }
        }
        await expect(sidebarTitle).toBeVisible();

        // --- Select the seeded demo board (real backend data) + a common topic ---
        const boardSelect = page.locator('#comp-board-select');
        const topicSelect = page.locator('#comp-topic-select');

        await expect(boardSelect).toBeVisible();
        await boardSelect.selectOption({ label: 'General Communication' });

        await expect(topicSelect).toBeVisible();
        // "daily" is one of the client-side common topics.
        await topicSelect.selectOption({ value: 'daily' });

        const saveBtn = page.getByRole('button', { name: /Save Topic|Guardar tema/i });
        await saveBtn.click();

        // The saved topic lists the translated topic and the real board name.
        const listArea = page.locator('.space-y-2').last();
        await expect(listArea.getByText(/Daily Routines|Rutinas Diarias/i).first()).toBeVisible();
        await expect(listArea.getByText('General Communication').first()).toBeVisible();

        // --- Custom context + custom topic (client-side) ---
        await boardSelect.selectOption({ value: 'custom' });
        await expect(boardSelect).toHaveValue('custom');
        const contextInput = boardSelect.locator('xpath=following-sibling::input');
        await expect(contextInput).toBeVisible();
        await contextInput.fill('My Custom Context');

        await topicSelect.selectOption({ value: 'custom' });
        await expect(topicSelect).toHaveValue('custom');
        const topicInput = topicSelect.locator('xpath=following-sibling::input');
        await expect(topicInput).toBeVisible();
        await topicInput.fill('My Custom Topic');

        await saveBtn.click();
        await expect(listArea.getByText('My Custom Topic').first()).toBeVisible();
        await expect(listArea.getByText('My Custom Context').first()).toBeVisible();

        // --- Start a real session (DB-backed; no LLM call until the auto-ask) ---
        const startBtn = page.getByRole('button', { name: /Start Session|Iniciar sesión/i });
        await expect(startBtn).toBeVisible();
        const startRequest = page.waitForRequest((request) =>
            request.url().includes('/api/learning/start') && request.method() === 'POST',
        );
        await startBtn.click();
        await startRequest;
        await expect(page.getByTestId('learning-session-active')).toBeVisible();
    });
});
