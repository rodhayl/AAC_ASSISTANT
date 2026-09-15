import { test, expect } from '@playwright/test';

import { ensureDemoBoard } from './demo-fixture';

// The board picker needs the demo board to exist; the fixture builds it through
// the API, so no seeded sample data is required.
test.describe('Learning Page - Boards and Topics', () => {
    test.use({ storageState: 'playwright/.auth/admin.json' });

    test.beforeEach(async ({ page }) => {
        await ensureDemoBoard(page.request);
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
    await boardSelect.selectOption({ label: 'Comunicación General' });

        await expect(topicSelect).toBeVisible();
        // "daily" is one of the client-side common topics.
        await topicSelect.selectOption({ value: 'daily' });

        const saveBtn = page.getByRole('button', { name: /Save Topic|Guardar tema/i });
        await saveBtn.click();

        // The saved topic lists the translated topic and the real board name.
        // Scope to the sidebar list: the page has other, unrelated stacked
        // containers, so a bare `.space-y-2` match pointed at the wrong one.
        const listArea = page.getByTestId('saved-topics-list');
        await expect(listArea.getByText(/Daily Routines|Rutinas Diarias/i).first()).toBeVisible();
    await expect(listArea.getByText('Comunicación General').first()).toBeVisible();

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
        // Saved topics start from their own "Start study" action; the page-level
        // start button was replaced by the topic picker.
        const startBtn = listArea
            .getByRole('button', { name: /Start study|Comenzar estudio|Start Session|Iniciar sesión/i })
            .first();
        await expect(startBtn).toBeVisible();
        const startRequest = page.waitForRequest((request) =>
            request.url().includes('/api/learning/start') && request.method() === 'POST',
        );
        await startBtn.click();
        await startRequest;
        await expect(page.getByTestId('learning-session-active')).toBeVisible();
    });
});
