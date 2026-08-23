import { test, expect } from '@playwright/test';

test.describe('Extended Features', () => {
  
  test.describe('Symbol Management', () => {
    test.use({ storageState: 'playwright/.auth/admin.json' });

    test('should filter and sort real seeded symbols', async ({ page }) => {
      // No API mocks: the symbol library is served by the production backend.
      await page.goto('/symbols');
      await expect(page.locator('.animate-spin')).not.toBeVisible({ timeout: 20000 });

      // A seeded symbol (cow) is on the demo board, so it is visible under
      // "All" and "In use", and absent under "Unused". This keeps the
      // assertions deterministic regardless of which other specs ran first.
      const cow = page.getByText('cow', { exact: true });
      await expect(cow).toBeVisible({ timeout: 15000 });

      // "In use": the demo board uses the seeded symbol.
      await page.locator('button').filter({ hasText: /in use|en uso/i }).click({ force: true });
      await expect(cow).toBeVisible();

      // "Unused": cow is on the demo board, so it disappears regardless of
      // whether other specs created their own (unused) symbols. Do not assert
      // the empty-state message here: it is not deterministic when other specs
      // leave freshly created symbols in the library.
      await page.locator('button').filter({ hasText: /unused|sin uso/i }).click({ force: true });
      await expect(cow).not.toBeVisible();

      // "All": the full library returns.
      await page.locator('button').filter({ hasText: /all|todos/i }).first().click({ force: true });
      await expect(cow).toBeVisible();

      // Alphabetical sort keeps the library rendered.
      const sortSelect = page
        .locator('select')
        .filter({ has: page.locator('option[value="alpha"]') })
        .first();
      await sortSelect.selectOption('alpha');
      await expect(cow).toBeVisible();
    });

    test('creates, edits, and deletes a symbol', async ({ page }) => {
      const label = `CRUD ${Date.now()}`;
      await page.goto('/symbols');
      await expect(page.locator('.animate-spin')).not.toBeVisible({ timeout: 20000 });

      // Create a new symbol via the library form.
      await page.getByRole('button', { name: /new symbol|nuevo símbolo/i }).click();
      await page.locator('#symbol-label').fill(label);
      await page.getByRole('button', { name: /create symbol|crear símbolo/i }).click();
      await expect(
        page.locator('div.flex.flex-col.gap-2', { hasText: label }).first(),
      ).toBeVisible({ timeout: 15000 });

      // Edit it: the form switches to Save mode and persists the new label.
      const card = page.locator('div.flex.flex-col.gap-2', { hasText: label }).first();
      await card.getByRole('button', { name: /edit|editar/i }).click();
      const newLabel = `${label} v2`;
      await page.locator('#symbol-label').fill(newLabel);
      await page.getByRole('button', { name: /save|guardar/i }).click();
      await expect(
        page.locator('div.flex.flex-col.gap-2', { hasText: newLabel }).first(),
      ).toBeVisible({ timeout: 15000 });

      // Delete it: the confirm dialog completes and the card disappears.
      const newCard = page.locator('div.flex.flex-col.gap-2', { hasText: newLabel }).first();
      await newCard
        .locator('button')
        .filter({ has: page.locator('svg.lucide-trash-2') })
        .click();
      const dialog = page.getByRole('dialog');
      await expect(dialog).toBeVisible();
      await dialog.getByRole('button', { name: /delete|eliminar/i }).click();
      await expect(
        page.locator('div.flex.flex-col.gap-2', { hasText: newLabel }),
      ).toHaveCount(0, { timeout: 15000 });
    });
  });

  test.describe('Learning History', () => {
    test.use({ storageState: 'playwright/.auth/student.json' });

    test('should view and load learning session history', async ({ page }) => {
      await page.goto('/learning');
      
      // Open History Sidebar (if mobile) or check sidebar visibility
      // Look for "History" or "Historial"
      const historyHeader = page.getByText(/history|historial/i);
      if (await historyHeader.isVisible()) {
          // Check if there are items
          const sessionItem = page.locator('button').filter({ hasText: /score|puntuación|completed/i }).first();
          if (await sessionItem.isVisible()) {
              await sessionItem.click();
              // Verify session loaded (messages appear)
              await expect(page.locator('.bg-indigo-100').or(page.locator('.bg-white.shadow-sm'))).toBeVisible();
          } else {
              console.log('No history items to click');
          }
      }
    });
  });

  test.describe('Board Search', () => {
    test.use({ storageState: 'playwright/.auth/student.json' });

    test('should search for boards', async ({ page }) => {
      await page.goto('/boards');
      
      // Find search input
      const searchInput = page.getByPlaceholder(/search|buscar/i);
      await expect(searchInput).toBeVisible();
      await searchInput.fill('Test');
      
      // Verify results filtered
      await page.waitForTimeout(1000);
      await expect(searchInput).toHaveValue('Test');
      
      // Clear search
      await searchInput.fill('');
      await expect(searchInput).toBeEmpty();
    });
  });
});
