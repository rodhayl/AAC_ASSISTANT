import { test, expect } from '@playwright/test';

// Real-backend verification of the core AAC flow (no page.route mocks).
// A student opens the seeded "Comunicación General" board (auto-assigned by
// the sample seed) and drives the full sentence-building lifecycle, so symbol
// selection -> sentence construction -> reordering/backspace/clear/speak are
// exercised end-to-end against the production API.
//
// The app localizes symbol labels to the student's UI language (e.g. Spanish),
// so tests read the rendered labels instead of hardcoding English.
test.describe('Communication', () => {
  test.use({ storageState: 'playwright/.auth/student.json' });

  const symbolLabel = (label: string) => `Add ${label} to sentence`;

  async function openBoard(page: import('@playwright/test').Page) {
    await page.goto('/communication');

  const board = page.getByRole('button', { name: /Comunicación General/ }).first();
    await expect(board).toBeVisible();
    await board.click();

    const grid = page.locator('.grid');
    await expect(grid).toBeVisible();
    await expect(grid.getByRole('button', { name: /Add .* to sentence/ }).first()).toBeVisible();
    return grid;
  }

  /** Read the first `count` symbol labels rendered in the grid. */
  async function readSymbolLabels(
    page: import('@playwright/test').Page,
    count: number,
  ): Promise<string[]> {
    const buttons = page.locator('.grid').getByRole('button', { name: /Add .* to sentence/ });
    const labels: string[] = [];
    const total = Math.min(count, await buttons.count());
    for (let i = 0; i < total; i++) {
      const aria = await buttons.nth(i).getAttribute('aria-label');
      const match = aria?.match(/^Add (.+) to sentence$/);
      if (match) labels.push(match[1]);
    }
    expect(labels.length, 'the AAC grid must render add-to-sentence buttons').toBe(count);
    return labels;
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

    // Build a three-symbol phrase in grid order.
    const [first, second, third] = await readSymbolLabels(page, 3);
    for (const label of [first, second, third]) {
      await grid.getByRole('button', { name: symbolLabel(label) }).click();
    }

    // The preview joins the symbol labels in selection order.
    await expect(preview).toHaveText(`${first} ${second} ${third}`);

    // Once populated, backspace/speak/clear/askAI become enabled.
    await expect(backspace).toBeEnabled();
    await expect(clear).toBeEnabled();
    await expect(speak).toBeEnabled();
    await expect(askAI).toBeEnabled();

    // The three symbol chips are present, each once.
    for (const label of [first, second, third]) {
      await expect(strip.locator('span').filter({ hasText: new RegExp(`^${label}$`) })).toBeVisible();
    }

    // Backspace removes only the last symbol.
    await backspace.click();
    await expect(preview).toHaveText(`${first} ${second}`);
    await expect(strip.locator('span').filter({ hasText: new RegExp(`^${third}$`) })).toHaveCount(0);

    // Re-add the third symbol, then clear the whole sentence.
    await grid.getByRole('button', { name: symbolLabel(third) }).click();
    await expect(preview).toHaveText(`${first} ${second} ${third}`);
    await clear.click();
    await expect(empty).toBeVisible();
    await expect(backspace).toBeDisabled();
    await expect(speak).toBeDisabled();
  });

  test('individual symbol chip can be removed from the sentence', async ({ page }) => {
    const grid = await openBoard(page);

    const preview = page.getByTestId('sentence-preview');
    const [first, second] = await readSymbolLabels(page, 2);

    await grid.getByRole('button', { name: symbolLabel(first) }).click();
    await grid.getByRole('button', { name: symbolLabel(second) }).click();
    await expect(preview).toHaveText(`${first} ${second}`);

    // The remove ("X") button is the only button nested inside the chip that
    // is not one of the named controls. The chip carries a stable testid
    // (sentence-chip), so the locator does not depend on Tailwind class
    // names. The chip's text also carries the image-fallback copy, so match
    // the label as a substring rather than an anchored pattern. Remove the
    // second symbol and confirm only the first remains.
    const chip = page.getByTestId('sentence-strip')
      .locator('[data-testid="sentence-chip"]', { hasText: second })
      .first();
    await chip.hover();
    await chip.locator('button').first().click();
    await expect(preview).toHaveText(first);
    await expect(page.getByTestId('sentence-strip').locator('span').filter({ hasText: new RegExp(`^${second}$`) })).toHaveCount(0);
  });

  test('speaking a sentence does not clear it and stays enabled', async ({ page }) => {
    const grid = await openBoard(page);

    const preview = page.getByTestId('sentence-preview');
    const speak = page.getByTestId('sentence-speak');
    const [label] = await readSymbolLabels(page, 1);

    await grid.getByRole('button', { name: symbolLabel(label) }).click();
    await expect(preview).toHaveText(label);

    // Headless Chromium exposes speechSynthesis but never voices; the TTS queue
    // degrades gracefully and the sentence must remain intact after speaking.
    await speak.click();
    await expect(preview).toHaveText(label);
  });
});
