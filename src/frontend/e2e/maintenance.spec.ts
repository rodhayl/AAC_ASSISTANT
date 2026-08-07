import { test, expect, type Page } from '@playwright/test';

/**
 * Browser-level regression coverage for the maintenance fixes:
 *
 * 1. Settings cache (src/api/deps/settings.py): `get_setting_value` must
 *    return the configured DB value — never a stale cached default. After
 *    `PUT /api/providers/stt/model` invalidates the cache, a fresh page load
 *    must show the configured model, not the process default. (The transient
 *    read-failure nuance is covered at unit level by
 *    tests/test_dependencies_settings_cache.py; this spec locks in the
 *    observable end-to-end contract.)
 *
 * 2. JWT guard (src/aac_app/utils/jwt_utils.py): the strict decode path must
 *    reject forged tokens server-side. A tampered signature must produce a
 *    401 and bounce the user to the login page instead of granting access.
 */

const adminUsername = process.env.E2E_ADMIN_USERNAME || 'admin1';
const adminPassword = process.env.E2E_ADMIN_PASSWORD || 'Admin123';

const SUPPORTED_STT_MODELS = ['tiny', 'base', 'small', 'medium', 'large-v3'];

test.describe('Maintenance: settings cache regression', () => {
  test.use({ storageState: 'playwright/.auth/admin.json' });

  let originalModel = '';

  const waitForSttSave = (page: Page) =>
    page.waitForResponse(
      res =>
        res.url().includes('/api/providers/stt/model') &&
        res.request().method() === 'PUT',
      { timeout: 15000 },
    );

  test.afterEach(async ({ page }) => {
    // Best-effort restore: a mid-test failure must not leave the live DB
    // configured to a different speech-to-text model for other specs/users.
    if (!originalModel) return;
    try {
      await page.goto('/settings');
      const select = page.locator('#stt-model');
      await expect(select).toBeEnabled({ timeout: 10000 });
      if ((await select.inputValue()) !== originalModel) {
        const saved = waitForSttSave(page);
        await select.selectOption(originalModel);
        expect((await saved).status()).toBe(200);
      }
    } catch {
      // Restore is best-effort; the test itself asserts the primary path.
    }
  });

  test('configured STT model wins over cached default after a reload', async ({ page }) => {
    await page.goto('/settings');

    // The select is disabled until voice status (and its model list) loads.
    const select = page.locator('#stt-model');
    await expect(select).toBeEnabled({ timeout: 15000 });

    originalModel = await select.inputValue();
    expect(SUPPORTED_STT_MODELS).toContain(originalModel);

    // Pick a different supported model deterministically. Saving is automatic
    // on change: wait for the PUT to complete (locale-independent), then for
    // the refreshed voice-status to render the new value in the select.
    const targetModel = originalModel === 'tiny' ? 'base' : 'tiny';
    const saved = waitForSttSave(page);
    await select.selectOption(targetModel);
    expect((await saved).status()).toBe(200);
    await expect(select).toHaveValue(targetModel);

    // A fresh page load must show the configured value. If the settings cache
    // were poisoned with the default (the bug being guarded against), the
    // reload would revert to the default instead of the saved model.
    await page.reload();
    await expect(select).toBeEnabled({ timeout: 15000 });
    await expect(select).toHaveValue(targetModel);

    // Restore the original value and confirm the same persistence contract.
    const restored = waitForSttSave(page);
    await select.selectOption(originalModel);
    expect((await restored).status()).toBe(200);
    await page.reload();
    await expect(select).toBeEnabled({ timeout: 15000 });
    await expect(select).toHaveValue(originalModel);
  });
});

test.describe('Maintenance: JWT guard regression', () => {
  test('forged token signature is rejected and the user is bounced to login', async ({ page }) => {
    const pageErrors: string[] = [];
    page.on('pageerror', err => pageErrors.push(String(err)));

    let saw401 = false;
    page.on('response', res => {
      if (res.status() === 401) saw401 = true;
    });

    // Establish a genuinely fresh, valid session regardless of storage-state
    // age, so the token we tamper with is guaranteed unexpired.
    await page.goto('/login');
    await page.evaluate(() => {
      localStorage.clear();
      localStorage.setItem('i18nextLng', 'en');
      localStorage.setItem('aac_assistant_locale', 'en');
    });
    await page.reload();
    await page.locator('#username').fill(adminUsername);
    await page.locator('#password').fill(adminPassword);
    await page.locator('button[type="submit"]').click();
    await page.waitForURL('/', { timeout: 15000 });

    // Corrupt only the signature segment of the persisted access token. The
    // payload still decodes client-side (exp is valid), so the app must rely
    // on the server's signature verification to reject the request.
    const forged = await page.evaluate(() => {
      const raw = localStorage.getItem('auth-storage');
      if (!raw) return false;
      const stored = JSON.parse(raw) as { state?: { token?: string } };
      const token = stored.state?.token;
      if (!token) return false;
      const parts = token.split('.');
      if (parts.length !== 3) return false;
      parts[2] = 'A'.repeat(Math.max(parts[2]?.length ?? 64, 64));
      stored.state.token = parts.join('.');
      localStorage.setItem('auth-storage', JSON.stringify(stored));
      return true;
    });
    expect(forged).toBe(true);

    await page.reload();

    // The forged token must be rejected server-side (401) and the app must
    // land on the login page without crashing.
    await expect(page).toHaveURL(/\/login(?:[/?#]|$)/, { timeout: 20000 });
    await expect(page.locator('button[type="submit"]')).toBeVisible();
    expect(saw401).toBe(true);
    expect(pageErrors).toHaveLength(0);
  });
});
