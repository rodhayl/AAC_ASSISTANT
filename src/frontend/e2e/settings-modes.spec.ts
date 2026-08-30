import { test, expect } from '@playwright/test';

test.describe('Learning Modes Settings', () => {
  test.use({ storageState: 'playwright/.auth/admin.json' });

  const openForm = async (page: import('@playwright/test').Page) => {
    await page.goto('/settings');
    await page.getByRole('button', { name: /Add New Learning Mode|Añadir nuevo modo/i }).click();
  };

  test('should allow creating a new learning mode', async ({ page }) => {
    const suffix = Date.now();
    const name = `New Mode ${suffix}`;
    const key = `new_mode_${suffix}`;

    await openForm(page);

    await page.locator('#learning-mode-name').fill(name);
    await page.locator('#learning-mode-key').fill(key);
    await page.locator('#learning-mode-description').fill('New Desc');
    await page.locator('#mode-prompt-instruction').fill('New Prompt');

    await page.getByRole('button', { name: /Save Mode|Guardar modo/i }).click();

    await expect(page.getByText(/Mode created successfully|Modo creado correctamente/i)).toBeVisible();
    // The freshly created mode is listed (name appears in the row).
    await expect(page.getByText(name, { exact: true })).toBeVisible();
  });

  test('should allow editing a custom learning mode', async ({ page }) => {
    const suffix = Date.now();
    const name = `Edit Target ${suffix}`;
    const key = `edit_target_${suffix}`;
    const updatedName = `${name} Updated`;

    // Create a custom mode first so the edit flow has a real row to target.
    await openForm(page);
    await page.locator('#learning-mode-name').fill(name);
    await page.locator('#learning-mode-key').fill(key);
    await page.locator('#learning-mode-description').fill('Desc');
    await page.locator('#mode-prompt-instruction').fill('Prompt');
    await page.getByRole('button', { name: /Save Mode|Guardar modo/i }).click();
    await expect(page.getByText(/Mode created successfully|Modo creado correctamente/i)).toBeVisible();

    const row = page.locator('div.border.border-border').filter({ hasText: name }).first();
    await expect(row).toBeVisible();
    await row.getByRole('button', { name: new RegExp(`(?:Edit|Editar) ${name}`, 'i') }).click();

    await page.locator('#learning-mode-name').fill(updatedName);
    await page.locator('#learning-mode-description').fill('Desc Updated');

    // The key is immutable on edit.
    await expect(page.locator('#learning-mode-key')).toBeDisabled();

    await page.getByRole('button', { name: /Save Mode|Guardar modo/i }).click();
    await expect(page.getByText(/Mode updated successfully|Modo actualizado correctamente/i)).toBeVisible();
  });
});
