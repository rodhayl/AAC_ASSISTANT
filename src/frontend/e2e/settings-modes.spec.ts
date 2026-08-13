import { test, expect } from '@playwright/test';

test.describe('Learning Modes Settings', () => {
  test.use({ storageState: 'playwright/.auth/admin.json' });

  const openForm = async (page: import('@playwright/test').Page) => {
    await page.goto('/settings');
    await page.getByRole('button', { name: /Add New Learning Mode/i }).click();
  };

  test('should allow creating a new learning mode', async ({ page }) => {
    await openForm(page);

    await page.getByPlaceholder('e.g. Daily Conversation').fill('New Mode');
    await page.getByPlaceholder('e.g. daily_conversation').fill('new_mode');
    await page.getByPlaceholder('Brief description for the user').fill('New Desc');
    await page.getByPlaceholder('Instructions for the AI on how to behave in this mode...').fill('New Prompt');

    await page.getByRole('button', { name: 'Save Mode' }).click();

    await expect(page.getByText('Mode created successfully')).toBeVisible();
    // The freshly created mode is listed (name appears in the row).
    await expect(page.getByText('New Mode', { exact: true })).toBeVisible();
  });

  test('should allow editing a custom learning mode', async ({ page }) => {
    // Create a custom mode first so the edit flow has a real row to target.
    await openForm(page);
    await page.getByPlaceholder('e.g. Daily Conversation').fill('Edit Target');
    await page.getByPlaceholder('e.g. daily_conversation').fill('edit_target');
    await page.getByPlaceholder('Brief description for the user').fill('Desc');
    await page.getByPlaceholder('Instructions for the AI on how to behave in this mode...').fill('Prompt');
    await page.getByRole('button', { name: 'Save Mode' }).click();
    await expect(page.getByText('Mode created successfully')).toBeVisible();

    const row = page.locator('div.border.border-gray-200').filter({ hasText: 'Edit Target' }).first();
    await expect(row).toBeVisible();
    await row.getByRole('button', { name: 'Edit Edit Target' }).click();

    await page.getByPlaceholder('e.g. Daily Conversation').fill('Edit Target Updated');
    await page.getByPlaceholder('Brief description for the user').fill('Desc Updated');

    // The key is immutable on edit.
    await expect(page.getByPlaceholder('e.g. daily_conversation')).toBeDisabled();

    await page.getByRole('button', { name: 'Save Mode' }).click();
    await expect(page.getByText('Mode updated successfully')).toBeVisible();
  });
});
