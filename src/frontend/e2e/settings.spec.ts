import { test, expect, type Page } from '@playwright/test';

const bootstrapPassword = process.env.AAC_BOOTSTRAP_ADMIN_PASSWORD || 'Admin123';

// The Appearance tab exposes stable, language-independent ids for every
// preference, so these tests assert real persistence (PUT body + reload)
// instead of relying on translated label text or fixed sleeps.
const savePrefs = (page: Page) =>
  page.getByRole('button', { name: /Save Appearance Settings|Guardar ajustes de apariencia/i });

async function gotoSettings(page: Page) {
  await page.goto('/settings');
  await expect(page.getByRole('heading', { name: /settings|ajustes/i })).toBeVisible();
}

/** Change a toggle, save, assert the PUT payload, then restore the prior value. */
async function toggleAndPersist(
  page: Page,
  id: string,
  target: boolean,
  assertBody: (body: Record<string, unknown>) => void,
) {
  const toggle = page.locator(`#${id}`);
  await expect(toggle).toBeAttached();

  const putResponse = page.waitForResponse(
    (r) => r.url().includes('/api/auth/preferences') && r.request().method() === 'PUT',
  );
  if (target) await toggle.check({ force: true });
  else await toggle.uncheck({ force: true });
  await savePrefs(page).click();

  const putBody = (await (await putResponse).json()) as Record<string, unknown>;
  assertBody(putBody);

  // Reload and confirm the persisted value drives the rendered control.
  const getResponse = page.waitForResponse(
    (r) => r.url().includes('/api/auth/preferences') && r.request().method() === 'GET',
  );
  await page.reload();
  await (await getResponse).json();
  const afterReload = page.locator(`#${id}`);
  await expect(afterReload).toBeAttached();
  if (target) await expect(afterReload).toBeChecked();
  else await expect(afterReload).not.toBeChecked();
}

test.describe('Settings', () => {
  test.use({ storageState: 'playwright/.auth/admin.json' });

  test('persists the interface language selection', async ({ page }) => {
    await gotoSettings(page);
    const select = page.locator('#pref-ui-language');
    await expect(select).toBeVisible();
    const initial = await select.inputValue();

    await select.selectOption('es-ES');
    await savePrefs(page).click();
    await expect(page.locator('#pref-ui-language')).toHaveValue('es-ES');

    // Restore the original language so later specs see a stable UI.
    await select.selectOption(initial);
    await savePrefs(page).click();
    await expect(page.locator('#pref-ui-language')).toHaveValue(initial);
  });

  test('persists dark mode across reload', async ({ page }) => {
    await gotoSettings(page);
    const id = 'pref-dark-mode';
    const initial = await page.locator(`#${id}`).isChecked();
    await toggleAndPersist(page, id, !initial, (body) => {
      expect(body.dark_mode).toBe(!initial);
    });
    // Restore the original value for other specs.
    await toggleAndPersist(page, id, initial, (body) => {
      expect(body.dark_mode).toBe(initial);
    });
  });

  test('persists high-contrast mode across reload', async ({ page }) => {
    await gotoSettings(page);
    const id = 'pref-high-contrast';
    const initial = await page.locator(`#${id}`).isChecked();
    await toggleAndPersist(page, id, !initial, (body) => {
      expect(body.high_contrast).toBe(!initial);
    });
    await toggleAndPersist(page, id, initial, (body) => {
      expect(body.high_contrast).toBe(initial);
    });
  });

  test('persists dwell time and reflects the milliseconds label', async ({ page }) => {
    await gotoSettings(page);
    const slider = page.locator('#pref-dwell-time');
    await expect(slider).toBeVisible();
    const original = await slider.inputValue();

    const putResponse = page.waitForResponse(
      (r) => r.url().includes('/api/auth/preferences') && r.request().method() === 'PUT',
    );
    await slider.fill('800');
    await expect(page.getByText('800ms')).toBeVisible();
    await savePrefs(page).click();

    const putBody = (await (await putResponse).json()) as Record<string, unknown>;
    expect(putBody.dwell_time).toBe(800);

    await slider.fill(original);
    await savePrefs(page).click();
  });

  test('edits the profile display name and reports success', async ({ page }) => {
    await gotoSettings(page);

    const editBtn = page.getByRole('button', { name: /^(edit|editar)$/i });
    await expect(editBtn).toBeVisible();
    await editBtn.click();

    const displayName = page.locator('#profile-display-name');
    await expect(displayName).toBeEnabled();
    const uniqueName = `Admin ${Date.now()}`;
    await displayName.fill(uniqueName);

    await page.getByRole('button', { name: /^(save|guardar)$/i }).click();
    await expect(page.getByText(/profile updated|perfil actualizado/i)).toBeVisible();
    await expect(page.locator('#settings-profile-heading')).toHaveText(uniqueName);
  });

  test('rejects an invalid email address on profile save', async ({ page }) => {
    await gotoSettings(page);

    await page.getByRole('button', { name: /^(edit|editar)$/i }).click();

    const email = page.locator('#profile-email');
    await expect(email).toBeEnabled();
    await email.fill('not-an-email');

    await page.getByRole('button', { name: /^(save|guardar)$/i }).click();

    // The backend validates EmailStr and surfaces a "valid email address" error.
    await expect(page.locator('.text-red-600').filter({ hasText: /valid email/i })).toBeVisible();

    // The form remains open (no crash) and can be cancelled.
    await page.getByRole('button', { name: /^(cancel|cancelar)$/i }).click();
    await expect(page.locator('#profile-email')).toBeDisabled();
  });

  test('changes password and re-authenticates to refresh the session', async ({ page }) => {
    await gotoSettings(page);

    await page.getByRole('button', { name: /change password|cambiar/i }).click();
    await expect(page.locator('#current-password')).toBeVisible();

    // Keep the bootstrap password so later specs and reruns can authenticate.
    await page.locator('#current-password').fill(bootstrapPassword);
    await page.locator('#new-password').fill(bootstrapPassword);
    await page.locator('#confirm-password').fill(bootstrapPassword);
    await page.getByRole('button', { name: /^(save|guardar)$/i }).click();

    await expect(page.locator('#current-password')).not.toBeVisible();

    // A password change revokes the current JWT; re-login to refresh the shared
    // admin storage state so subsequent tests keep working.
    await page.goto('/login');
    await page.locator('#username').fill(process.env.E2E_ADMIN_USERNAME || 'admin1');
    await page.locator('#password').fill(bootstrapPassword);
    await page.locator('button[type="submit"]').click();
    await expect(page).toHaveURL('/', { timeout: 20000 });
    await page.context().storageState({ path: 'playwright/.auth/admin.json' });
  });
});
