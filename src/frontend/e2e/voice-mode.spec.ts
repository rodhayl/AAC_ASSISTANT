import { test, expect } from '@playwright/test';

// Voice-mode toggling persists through the real preferences API
// (`PUT`/`GET /api/auth/preferences`), not a mocked route.
async function toggleAndSave(page: import('@playwright/test').Page) {
  await page.goto('/settings');

  // The checkbox id is stable regardless of the active UI language.
  const toggle = page.locator('#pref-voice-mode-enabled');
  await expect(toggle).toBeVisible();

  const initial = await toggle.isChecked();
  const target = !initial;
  if (target) await toggle.check({ force: true });
  else await toggle.uncheck({ force: true });
  // Wait for React to commit the controlled input before saving, otherwise
  // the save handler can read the previous value from its stale closure.
  if (target) await expect(toggle).toBeChecked();
  else await expect(toggle).not.toBeChecked();

  // Save and assert the backend persisted the exact value we asked for.
  const putResponse = page.waitForResponse(
    (r) => r.url().includes('/api/auth/preferences') && r.request().method() === 'PUT',
  );
  await page.getByRole('button', { name: /Save Preferences|Guardar preferencias/i }).click();
  const putBody = await (await putResponse).json();
  expect(putBody.voice_mode_enabled).toBe(target);

  // Reload and wait for the preferences GET to resolve before asserting the
  // UI, so the check does not race the async preference load.
  const getResponse = page.waitForResponse(
    (r) => r.url().includes('/api/auth/preferences') && r.request().method() === 'GET',
  );
  await page.reload();
  const getBody = await (await getResponse).json();
  expect(getBody.voice_mode_enabled).toBe(target);

  const afterReload = page.locator('#pref-voice-mode-enabled');
  await expect(afterReload).toBeVisible();
  if (target) await expect(afterReload).toBeChecked();
  else await expect(afterReload).not.toBeChecked();
}

test.describe('Voice Mode - Student', () => {
  test.use({ storageState: 'playwright/.auth/student.json' });

  test('Student can toggle their own voice mode persistence', async ({ page }) => {
    await toggleAndSave(page);
  });
});

test.describe('Voice Mode - Admin', () => {
  test.use({ storageState: 'playwright/.auth/admin.json' });

  test('Admin can toggle their own voice mode persistence', async ({ page }) => {
    await toggleAndSave(page);
  });
});
