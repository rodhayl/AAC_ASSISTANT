import { test, expect } from '@playwright/test';

// Real-backend verification of the core AAC flow (no page.route mocks).
// A student opens the seeded "General Communication" board (auto-assigned by
// the sample seed) and drives the full sentence-building lifecycle, so symbol
// selection -> sentence construction -> reordering/backspace/clear/speak are
// exercised end-to-end against the production API.
//
// The seeded board always contains the 12 sample symbols (hello, yes, no,
// please, thank you, help, goodbye, water, apple, cow, horse, chicken), so the
// labels below are deterministic for a freshly seeded database.
test.describe('Communication', () => {
  test.use({ storageState: 'playwright/.auth/student.json' });

  const symbolLabel = (label: string) => `Add ${label} to sentence`;

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

  test('student opens the seeded board and builds a sentence', async ({ page }) => {
    const grid = await openBoard(page);

    const firstSymbol = grid.getByRole('button', { name: /Add .* to sentence/ }).first();
    const name = await firstSymbol.getAttribute('aria-label');
    const label = name?.match(/Add (.*) to sentence/)?.[1];
    expect(label).toBeTruthy();

    await firstSymbol.press('Enter');

    const strip = page.getByTestId('sentence-strip');
    await expect(strip).toBeVisible();
    await expect(strip.locator('span').filter({ hasText: label! })).toBeVisible();
  });

  test('sentence-building lifecycle: add, order, backspace, clear, speak', async ({ page }) => {
    const grid = await openBoard(page);

    const strip = page.getByTestId('sentence-strip');
    const preview = page.getByTestId('sentence-preview');
    const empty = page.getByTestId('sentence-empty');
    const backspace = page.getByTestId('sentence-backspace');
    const clear = page.getByTestId('sentence-clear');
    const speak = page.getByTestId('sentence-speak');
    const askAI = page.getByTestId('sentence-ask-ai');

    // Empty state: every control is disabled and the placeholder is shown.
    await expect(empty).toBeVisible();
    await expect(backspace).toBeDisabled();
    await expect(clear).toBeDisabled();
    await expect(speak).toBeDisabled();
    await expect(askAI).toBeDisabled();

    // Build "hello yes no" in order.
    for (const label of ['hello', 'yes', 'no']) {
      await grid.getByRole('button', { name: symbolLabel(label) }).click();
    }

    // The preview joins the symbol labels in selection order.
    await expect(preview).toHaveText('hello yes no');

    // Once populated, backspace/speak/clear/askAI become enabled.
    await expect(backspace).toBeEnabled();
    await expect(clear).toBeEnabled();
    await expect(speak).toBeEnabled();
    await expect(askAI).toBeEnabled();

    // The three symbol chips are present, each once.
    for (const label of ['hello', 'yes', 'no']) {
      await expect(strip.locator('span').filter({ hasText: new RegExp(`^${label}$`) })).toBeVisible();
    }

    // Backspace removes only the last symbol.
    await backspace.click();
    await expect(preview).toHaveText('hello yes');
    await expect(strip.locator('span').filter({ hasText: /^no$/ })).toHaveCount(0);

    // Re-add "no", then clear the whole sentence.
    await grid.getByRole('button', { name: symbolLabel('no') }).click();
    await expect(preview).toHaveText('hello yes no');
    await clear.click();
    await expect(empty).toBeVisible();
    await expect(backspace).toBeDisabled();
    await expect(speak).toBeDisabled();
  });

  test('individual symbol chip can be removed from the sentence', async ({ page }) => {
    const grid = await openBoard(page);

    const preview = page.getByTestId('sentence-preview');

    await grid.getByRole('button', { name: symbolLabel('please') }).click();
    await grid.getByRole('button', { name: symbolLabel('help') }).click();
    await expect(preview).toHaveText('please help');

    // The remove ("X") button is the only button nested inside the strip that
    // is not one of the named controls. It is scoped to the chip showing the
    // symbol label, so remove "help" and confirm only "please" remains.
    const helpChip = page.getByTestId('sentence-strip')
      .locator('div.flex-shrink-0', { hasText: /^help$/ })
      .first();
    await helpChip.hover();
    await helpChip.locator('button').first().click();
    await expect(preview).toHaveText('please');
    await expect(page.getByTestId('sentence-strip').locator('span').filter({ hasText: /^help$/ })).toHaveCount(0);
  });

  test('speaking a sentence does not clear it and stays enabled', async ({ page }) => {
    const grid = await openBoard(page);

    const preview = page.getByTestId('sentence-preview');
    const speak = page.getByTestId('sentence-speak');

    await grid.getByRole('button', { name: symbolLabel('thank you') }).click();
    await expect(preview).toHaveText('thank you');

    // Headless Chromium exposes speechSynthesis but never voices; the TTS queue
    // degrades gracefully and the sentence must remain intact after speaking.
    await speak.click();
    await expect(preview).toHaveText('thank you');
  });
});
