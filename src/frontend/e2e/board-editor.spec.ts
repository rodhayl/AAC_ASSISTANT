import { test, expect } from '@playwright/test';

// Real-backend board editor verification: create a board, add a symbol from
// the local symbol library, and remove it again. No page.route mocks and no
// swallowed assertions.
test.describe('Board Editor', () => {
  test.use({ storageState: 'playwright/.auth/student.json' });

  test('adds and removes a symbol from a new board', async ({ page }) => {
    await page.goto('/boards');
    await expect(page.locator('.animate-spin')).not.toBeVisible({ timeout: 20000 });

    // 1. Create a fresh board.
    const boardName = `Editor Test ${Date.now()}`;
    await page.getByRole('button', { name: /new board|nuevo|create board|crear/i }).first().click({ force: true });
    await page.getByLabel(/board name|nombre/i).fill(boardName);
    await page.getByRole('button', { name: /create|crear/i }).click();

    // 2. Open the board in the editor.
    await page.getByPlaceholder(/search|buscar/i).fill(boardName);
    await expect(page.getByText(boardName, { exact: true })).toBeVisible({ timeout: 30000 });
    await page.getByText(boardName, { exact: true }).click();
    await page.waitForURL(/\/boards\/\d+/);

    // 3. Open the symbol picker from an empty cell and add a seeded symbol.
    await page.getByRole('button', { name: 'Add symbol' }).first().click();
    const search = page.locator('#symbol-picker-search');
    await expect(search).toBeVisible();
    await search.fill('cow');
    await page.getByRole('button', { name: /cow/i }).first().click();

    // 4. The symbol now renders inside the grid cell.
    await expect(page.locator('.grid').getByText('cow', { exact: true })).toBeVisible({ timeout: 10000 });

    // 5. Remove it again (the control is revealed on hover).
    const symbolCard = page.locator('.grid').locator('div.group').filter({ hasText: 'cow' }).first();
    await symbolCard.hover();
    await symbolCard.getByRole('button', { name: 'Remove symbol' }).click();
    await expect(page.locator('.grid').getByText('cow', { exact: true })).not.toBeVisible({ timeout: 10000 });

    // Clearing a board is destructive: it must ask for confirmation and
    // cancelling must preserve the symbol.
    await page.getByRole('button', { name: 'Add symbol' }).first().click();
    await page.locator('#symbol-picker-search').fill('cow');
    await page.getByRole('button', { name: /cow/i }).first().click();
    await expect(page.locator('.grid').getByText('cow', { exact: true })).toBeVisible();

    // The editor UI is localized to the student's language; match the clear
    // button and its confirmation dialog across English and Spanish.
    const clearBoardButton = page.getByRole('button', { name: /clear board|limpiar tablero/i });
    await clearBoardButton.click();
    const clearDialog = page.getByRole('dialog', { name: /remove all symbols|eliminar todos los símbolos/i });
    await expect(clearDialog).toBeVisible();
    await clearDialog.getByRole('button', { name: /cancel|cancelar/i }).click();
    await expect(clearDialog).not.toBeVisible();
    await expect(page.locator('.grid').getByText('cow', { exact: true })).toBeVisible();

    await clearBoardButton.click();
    await page.getByRole('dialog', { name: /remove all symbols|eliminar todos los símbolos/i })
      .getByRole('button', { name: /clear board|limpiar tablero/i }).click();
    await expect(page.locator('.grid').getByText('cow', { exact: true })).not.toBeVisible({ timeout: 10000 });
  });
});
