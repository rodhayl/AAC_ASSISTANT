import { test, expect } from '@playwright/test';

// Real-backend verification of the core AAC flow (no page.route mocks).
// A student opens the seeded "General Communication" board (auto-assigned by
// the sample seed) and builds a sentence, so symbol selection -> sentence
// construction is exercised end-to-end against the production API.
test.describe('Communication', () => {
  test.use({ storageState: 'playwright/.auth/student.json' });

  test('student opens the seeded board and builds a sentence', async ({ page }) => {
    await page.goto('/communication');

    const board = page.getByRole('button', { name: /General Communication/ }).first();
    await expect(board).toBeVisible();
    await board.click();

    const grid = page.locator('.grid');
    await expect(grid).toBeVisible();

    // Any seeded symbol button exposes the stable accessible action name.
    const symbolButtons = grid.getByRole('button', { name: /Add .* to sentence/ });
    await expect(symbolButtons.first()).toBeVisible();

    const firstSymbol = symbolButtons.first();
    const name = await firstSymbol.getAttribute('aria-label');
    const label = name?.match(/Add (.*) to sentence/)?.[1];
    expect(label).toBeTruthy();

    await firstSymbol.press('Enter');

    const strip = page.getByTestId('sentence-strip');
    await expect(strip).toBeVisible();
    await expect(strip.locator('span').filter({ hasText: label! })).toBeVisible();
  });
});
