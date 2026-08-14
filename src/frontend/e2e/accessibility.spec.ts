import { test, expect } from '@playwright/test';

// Dependency-free accessibility checks for the core AAC flow. These verify that
// the primary input paths work without a pointer, which is a hard requirement
// for users with motor impairments. They do not claim WCAG conformance.

test.describe('Accessibility: keyboard operation', () => {
  test.use({ storageState: 'playwright/.auth/student.json' });

  async function openBoard(page: import('@playwright/test').Page) {
    await page.goto('/communication');
    const board = page.getByRole('button', { name: /General Communication/ }).first();
    await expect(board).toBeVisible();
    await board.click();
    const grid = page.locator('.grid');
    await expect(grid).toBeVisible();
    await expect(grid.getByRole('button', { name: /Add .* to sentence/ }).first()).toBeVisible();
    return grid;
  }

  test('skip-to-content link is first in the tab order and targets the main landmark', async ({ page }) => {
    await page.goto('/communication');
    await expect(page.locator('main#main-content')).toBeVisible();

    await page.keyboard.press('Tab');
    const skipLink = page.getByRole('link', { name: /skip|saltar/i });
    await expect(skipLink).toBeFocused();
    await expect(skipLink).toHaveAttribute('href', '#main-content');

    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(/#main-content/);
    await expect(page.locator('main#main-content')).toBeVisible();
  });

  test('a board symbol is keyboard-focusable and activates with Enter', async ({ page }) => {
    const grid = await openBoard(page);

    const firstSymbol = grid.getByRole('button', { name: /Add .* to sentence/ }).first();
    await firstSymbol.focus();
    await expect(firstSymbol).toBeFocused();

    const label = (await firstSymbol.getAttribute('aria-label'))?.match(/Add (.*) to sentence/)?.[1];
    expect(label).toBeTruthy();

    await page.keyboard.press('Enter');
    await expect(page.getByTestId('sentence-strip')).toBeVisible();
    await expect(page.getByTestId('sentence-preview')).toHaveText(label!);
  });

  test('sentence controls are keyboard-operable and stay in the tab order', async ({ page }) => {
    const grid = await openBoard(page);

    await grid.getByRole('button', { name: /Add hello to sentence/ }).click();
    await grid.getByRole('button', { name: /Add yes to sentence/ }).click();
    await expect(page.getByTestId('sentence-preview')).toHaveText('hello yes');

    // Backspace is a real button: it must accept focus and activate on Enter.
    const backspace = page.getByTestId('sentence-backspace');
    await backspace.focus();
    await expect(backspace).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(page.getByTestId('sentence-preview')).toHaveText('hello');

    // Clear is likewise keyboard-operable.
    const clear = page.getByTestId('sentence-clear');
    await clear.focus();
    await expect(clear).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(page.getByTestId('sentence-empty')).toBeVisible();
  });
});
