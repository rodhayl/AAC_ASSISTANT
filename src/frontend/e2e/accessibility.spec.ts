import { test, expect } from '@playwright/test';

// Dependency-free accessibility checks for the core AAC flow. These verify that
// the primary input paths work without a pointer, which is a hard requirement
// for users with motor impairments. They do not claim WCAG conformance.

function parseCssDurationsToMs(durationStr: string): number[] {
  return durationStr.split(',').map((part) => {
    const trimmed = part.trim();
    if (trimmed.endsWith('ms')) {
      return parseFloat(trimmed);
    }
    if (trimmed.endsWith('s')) {
      return parseFloat(trimmed) * 1000;
    }
    return parseFloat(trimmed) || 0;
  });
}

test.describe('Accessibility: keyboard operation', () => {
  test.use({ storageState: 'playwright/.auth/student.json' });

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

    // Read the rendered labels: the app localizes symbols to the student's
    // UI language, so this must not hardcode English.
    const buttons = grid.getByRole('button', { name: /Add .* to sentence/ });
    const first = await buttons.nth(0).getAttribute('aria-label');
    const second = await buttons.nth(1).getAttribute('aria-label');
    const firstLabel = first?.match(/Add (.*) to sentence/)?.[1];
    const secondLabel = second?.match(/Add (.*) to sentence/)?.[1];
    expect(firstLabel).toBeTruthy();
    expect(secondLabel).toBeTruthy();

    await buttons.nth(0).click();
    await buttons.nth(1).click();
    await expect(page.getByTestId('sentence-preview')).toHaveText(`${firstLabel} ${secondLabel}`);

    // Backspace is a real button: it must accept focus and activate on Enter.
    const backspace = page.getByTestId('sentence-backspace');
    await backspace.focus();
    await expect(backspace).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(page.getByTestId('sentence-preview')).toHaveText(firstLabel!);

    // Clear is likewise keyboard-operable.
    const clear = page.getByTestId('sentence-clear');
    await clear.focus();
    await expect(clear).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(page.getByTestId('sentence-empty')).toBeVisible();
  });

  test('respects prefers-reduced-motion media query on visual elements in the browser', async ({ page }) => {
    // 1. Emulate normal motion preference as baseline
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    await page.goto('/communication');
    await expect(page.locator('main#main-content')).toBeVisible();

    const baselineMatches = await page.evaluate(
      () => window.matchMedia('(prefers-reduced-motion: reduce)').matches
    );
    expect(baselineMatches).toBe(false);

    // 2. Measure baseline body transition duration (application default: 0.3s)
    const baselineDurationsRaw = await page.evaluate(
      () => window.getComputedStyle(document.body).transitionDuration
    );
    const baselineDurationsMs = parseCssDurationsToMs(baselineDurationsRaw);
    expect(baselineDurationsMs.length).toBeGreaterThan(0);
    expect(baselineDurationsMs.some((ms) => ms > 0.01)).toBe(true);

    // 3. Switch to reduced motion preference
    await page.emulateMedia({ reducedMotion: 'reduce' });
    const reducedMatches = await page.evaluate(
      () => window.matchMedia('(prefers-reduced-motion: reduce)').matches
    );
    expect(reducedMatches).toBe(true);

    // 4. Measure body transition duration under reduced motion (restricted to <= 0.01ms)
    const reducedDurationsRaw = await page.evaluate(
      () => window.getComputedStyle(document.body).transitionDuration
    );
    const reducedDurationsMs = parseCssDurationsToMs(reducedDurationsRaw);
    expect(reducedDurationsMs.length).toBeGreaterThan(0);
    expect(reducedDurationsMs.every((ms) => ms <= 0.01)).toBe(true);
  });
});
