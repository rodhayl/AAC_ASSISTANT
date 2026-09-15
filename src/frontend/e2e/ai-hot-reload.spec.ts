import { test, expect } from '@playwright/test';

test.describe('AI Configuration Hot Reload', () => {
  test.use({ storageState: 'playwright/.auth/admin.json' });

  test('should update LLM provider and reflect in learning session without restart', async ({ page }) => {
    // 1. Go to Settings and ensure we are using Ollama (or set a known state)
    await page.goto('/settings');
    
    await page.getByText('Ollama', { exact: true }).first().click();
    const saveBtn = page.locator('button').filter({ hasText: /save|guardar/i }).last();
    await saveBtn.click();
    
    // 2. Start a learning session from the topic picker (the page-level start
    // button was removed; without a session the message below was never sent,
    // which made the final assertion pass vacuously).
    await page.goto('/learning');
    const topicCard = page.locator('[data-testid^="topic-card-"]').first();
    await expect(topicCard).toBeVisible({ timeout: 15000 });
    await topicCard.click();
    await expect(page.getByTestId('learning-session-active')).toBeVisible({ timeout: 15000 });

    // Send a message
    const input = page.getByPlaceholder(/type|escribe/i).last();
    await input.fill('Hello check provider');
    await page.locator('button[type="submit"]').first().click();
    
    // 3. Change provider to OpenRouter
    await page.goto('/settings');
    await page.getByText('OpenRouter', { exact: true }).first().click();
    
    // Fill fake key if empty
    const keyInput = page.locator('input[type="password"]').or(page.locator('input[placeholder*="sk-or"]')).first();
    if (await keyInput.isVisible() && await keyInput.inputValue() === '') {
        await keyInput.fill('sk-or-test-fake-key');
    }
    
    await saveBtn.click();
    
    // 4. Go back to Learning (the in-flight session is resumed, so the chat
    // input is available without starting another session).
    await page.goto('/learning');
    await expect(input).toBeVisible({ timeout: 15000 });

    // Send a message
    await input.fill('Hello test hot reload');
    await page.locator('button[type="submit"]').first().click();
    
    // 5. Verify behavior: the hot-reloaded provider is the broken one, so the
    // send must surface a failure (the chat panel renders errors as role=alert)
    // and must not silently succeed. Asserting only "the input still has text"
    // passed even when no request was sent at all.
    await expect(page.getByRole('alert')).toBeVisible({ timeout: 30000 });
    
    // Cleanup: Revert to Ollama
    await page.goto('/settings');
    await page.getByText('Ollama', { exact: true }).first().click();
    await saveBtn.click();
  });
});
