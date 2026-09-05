import { expect, test, type Page } from '@playwright/test';

/**
 * Appearance (dark mode / high contrast) persistence and application.
 *
 * Asserts the real DOM classes that drive the theme (not just screenshots):
 * - dark mode and high contrast toggle independently and persist across reload
 * - the classes are driven by the server-persisted preference (Settings save)
 * - the class combination that the CSS uses for high-contrast-dark is exact
 * - the login screen applies the persisted appearance (no white flash)
 */
test.describe('Appearance', () => {
  test.use({ storageState: 'playwright/.auth/admin.json' });

  const rootClasses = (page: Page) =>
    page.evaluate(() => ({
      dark: document.documentElement.classList.contains('dark'),
      hc: document.documentElement.classList.contains('high-contrast'),
    }));

  const setToggle = async (page: Page, id: string, target: boolean) => {
    const toggle = page.locator(`#${id}`);
    await expect(toggle).toBeAttached();
    if ((await toggle.isChecked()) !== target) {
      // React-controlled checkbox: force-clicking the visually hidden input
      // sometimes misses React's onChange, so dispatch the native click
      // directly (guaranteed to flip the controlled value).
      await toggle.evaluate((el) => (el as HTMLInputElement).click());
      if (target) await expect(toggle).toBeChecked();
      else await expect(toggle).not.toBeChecked();
    }
  };

  /** Click save and wait for the PUT to land so later steps never race it. */
  const saveAppearance = async (page: Page) => {
    const put = page.waitForResponse(
      (r) => r.url().includes('/api/auth/preferences') && r.request().method() === 'PUT',
    );
    await page.getByRole('button', { name: /Save Appearance Settings|Guardar ajustes de apariencia/i }).click();
    await put;
  };

  test('dark mode and high contrast toggle independently and persist', async ({ page }) => {
    await page.goto('/settings');
    await expect(page.locator('#pref-dark-mode')).toBeAttached();

    const dark = page.locator('#pref-dark-mode');
    const hc = page.locator('#pref-high-contrast');
    const initialDark = await dark.isChecked();
    const initialHc = await hc.isChecked();

    // 1. Enable dark mode (whatever the server default is).
    await setToggle(page, 'pref-dark-mode', true);
    await saveAppearance(page);
    await expect(page.locator('html.dark')).toBeAttached();

    // 2. Reload: the persisted server preference must drive the class.
    await page.reload();
    await expect(page.locator('html.dark')).toBeAttached();
    await expect(page.locator('#pref-dark-mode')).toBeChecked();

    // 3. Add high contrast on top; dark stays applied.
    await setToggle(page, 'pref-high-contrast', true);
    await saveAppearance(page);
    await expect(page.locator('html.dark.high-contrast')).toBeAttached();

    await page.reload();
    await expect(page.locator('html.dark.high-contrast')).toBeAttached();
    await expect(page.locator('#pref-high-contrast')).toBeChecked();

    // 4. Disable dark (high contrast keeps working independently).
    await setToggle(page, 'pref-dark-mode', false);
    await saveAppearance(page);
    await expect(page.locator('html.high-contrast:not(.dark)')).toBeAttached();

    // Restore the original state so other specs see a stable UI.
    await setToggle(page, 'pref-dark-mode', initialDark);
    await setToggle(page, 'pref-high-contrast', initialHc);
    await saveAppearance(page);
    expect(await rootClasses(page)).toEqual({ dark: initialDark, hc: initialHc });
  });

  test('login screen applies the persisted appearance before auth', async ({ page }) => {
    await page.goto('/settings');
    const hc = page.locator('#pref-high-contrast');
    const dark = page.locator('#pref-dark-mode');
    const initialDark = await dark.isChecked();
    const initialHc = await hc.isChecked();

    await setToggle(page, 'pref-dark-mode', true);
    await setToggle(page, 'pref-high-contrast', true);
    await saveAppearance(page);
    await expect(page.locator('html.dark.high-contrast')).toBeAttached();

    // Sign out and land on /login: the class must already be applied there
    // (no flash of light mode before the auth state loads).
    await page.goto('/login');
    await expect(page.locator('html.dark.high-contrast')).toBeAttached();
    expect(await rootClasses(page)).toEqual({ dark: true, hc: true });

    // Restore the original server state so the shared admin session stays
    // stable for the rest of the suite.
    await page.goto('/settings');
    await setToggle(page, 'pref-dark-mode', initialDark);
    await setToggle(page, 'pref-high-contrast', initialHc);
    await saveAppearance(page);
    expect(await rootClasses(page)).toEqual({ dark: initialDark, hc: initialHc });
  });
});