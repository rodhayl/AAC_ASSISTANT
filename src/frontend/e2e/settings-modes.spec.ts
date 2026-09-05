import { test, expect } from '@playwright/test';

test.describe('Learning Modes Settings', () => {
  test.use({ storageState: 'playwright/.auth/admin.json' });

  const openForm = async (page: import('@playwright/test').Page) => {
    await page.goto('/settings');
    await page.getByRole('button', { name: /Add New Learning Mode|Añadir nuevo modo/i }).click();
  };

  test('should allow creating a new learning mode', async ({ page }) => {
    const suffix = Date.now();
    const name = `New Mode ${suffix}`;
    const key = `new_mode_${suffix}`;

    await openForm(page);

    await page.locator('#learning-mode-name').fill(name);
    await page.locator('#learning-mode-key').fill(key);
    await page.locator('#learning-mode-description').fill('New Desc');
    await page.locator('#mode-prompt-instruction').fill('New Prompt');

    await page.getByRole('button', { name: /Save Mode|Guardar modo/i }).click();

    await expect(page.getByText(/Mode created successfully|Modo creado correctamente/i)).toBeVisible();
    // The freshly created mode is listed in its row (the same name also
    // appears as an option in the default-mode combo).
    const row = page.locator('div.border.border-border').filter({ hasText: name }).first();
    await expect(row).toBeVisible();
  });

  test('should allow editing a custom learning mode', async ({ page }) => {
    const suffix = Date.now();
    const name = `Edit Target ${suffix}`;
    const key = `edit_target_${suffix}`;
    const updatedName = `${name} Updated`;

    // Create a custom mode first so the edit flow has a real row to target.
    await openForm(page);
    await page.locator('#learning-mode-name').fill(name);
    await page.locator('#learning-mode-key').fill(key);
    await page.locator('#learning-mode-description').fill('Desc');
    await page.locator('#mode-prompt-instruction').fill('Prompt');
    await page.getByRole('button', { name: /Save Mode|Guardar modo/i }).click();
    await expect(page.getByText(/Mode created successfully|Modo creado correctamente/i)).toBeVisible();

    const row = page.locator('div.border.border-border').filter({ hasText: name }).first();
    await expect(row).toBeVisible();
    await row.getByRole('button', { name: new RegExp(`(?:Edit|Editar) ${name}`, 'i') }).click();

    await page.locator('#learning-mode-name').fill(updatedName);
    await page.locator('#learning-mode-description').fill('Desc Updated');

    // The key is immutable on edit.
    await expect(page.locator('#learning-mode-key')).toBeDisabled();

    await page.getByRole('button', { name: /Save Mode|Guardar modo/i }).click();
    await expect(page.getByText(/Mode updated successfully|Modo actualizado correctamente/i)).toBeVisible();
  });

  test('applies the saved default mode when starting Learning', async ({ page }) => {
    const suffix = Date.now();
    const temporaryModeName = `E2E Default Mode ${suffix}`;
    const temporaryModeKey = `e2e_default_mode_${suffix}`;
    let originalMode = '';
    let temporaryModeCreated = false;

    await page.goto('/settings');
    const defaultMode = page.locator('#default-learning-mode');
    await expect(defaultMode).toBeVisible();
    originalMode = await defaultMode.inputValue();

    try {
      // Create a mode within this test so it remains independent from test
      // order and can always select a value different from the saved default.
      await page.getByRole('button', { name: /Add New Learning Mode|Añadir nuevo modo/i }).click();
      await page.locator('#learning-mode-name').fill(temporaryModeName);
      await page.locator('#learning-mode-key').fill(temporaryModeKey);
      await page.locator('#learning-mode-description').fill('Temporary E2E mode');
      await page.locator('#mode-prompt-instruction').fill('Temporary E2E prompt');
      await page.getByRole('button', { name: /Save Mode|Guardar modo/i }).click();
      await expect(page.getByText(/Mode created successfully|Modo creado correctamente/i)).toBeVisible();
      temporaryModeCreated = true;

      const saveResponsePromise = page.waitForResponse((response) =>
        response.request().method() === 'PUT' &&
        response.url().includes('/api/auth/preferences'),
      );
      await defaultMode.selectOption(temporaryModeKey);
      const saveResponse = await saveResponsePromise;
      expect(saveResponse.ok()).toBe(true);
      const savedPreferences = await saveResponse.json() as { default_learning_mode?: string };
      expect(savedPreferences.default_learning_mode).toBe(temporaryModeKey);
      await expect(defaultMode).toHaveValue(temporaryModeKey);
      await expect.poll(async () => page.evaluate(() => {
        try {
          const rawAuthState = localStorage.getItem('auth-storage');
          const authState = rawAuthState ? JSON.parse(rawAuthState) as {
            state?: { user?: { settings?: { default_learning_mode?: string } } };
          } : null;
          return authState?.state?.user?.settings?.default_learning_mode ?? null;
        } catch {
          return null;
        }
      })).toBe(temporaryModeKey);

      // Avoid a real LLM request while exercising the actual Learning page
      // and its session-start payload.
      let startPayload: Record<string, unknown> | undefined;
      await page.route('**/api/learning/start**', async (route) => {
        startPayload = route.request().postDataJSON() as Record<string, unknown>;
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            success: true,
            session_id: 990001,
            welcome_message: 'E2E default mode welcome',
          }),
        });
      });
      await page.route('**/api/learning/*/ask**', async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            success: true,
            question_id: 990001,
            question_text: 'E2E default mode question',
            choices: ['A', 'B'],
            correct_answer_index: 0,
          }),
        });
      });

      await page.goto('/learning');
      const startButton = page.getByTestId('learning-session-start');
      await expect(startButton).toBeVisible();
      await startButton.click();
      await expect(page.getByTestId('learning-session-active')).toBeVisible();
      expect(startPayload?.mode_key).toBe(temporaryModeKey);
    } finally {
      // Remove the temporary mode first; the backend repairs any default that
      // still points to it. Then restore the original preference directly so
      // cleanup does not depend on a React hydration race in the Settings UI.
      await page.goto('/settings');
      await expect(page.locator('#default-learning-mode')).toBeVisible();

      if (temporaryModeCreated) {
        const temporaryRow = page.locator('div.border.border-border').filter({ hasText: temporaryModeName }).first();
        if (await temporaryRow.count() > 0 && await temporaryRow.isVisible()) {
          await temporaryRow.getByRole('button', { name: new RegExp(`(?:Delete|Eliminar) ${temporaryModeName}`, 'i') }).click();
          const deleteDialog = page.getByRole('alertdialog');
          await expect(deleteDialog).toBeVisible();
          const deleteResponsePromise = page.waitForResponse((response) =>
            response.request().method() === 'DELETE' &&
            response.url().includes('/api/learning-modes/'),
          );
          await deleteDialog.getByRole('button', { name: /Delete|Eliminar/i }).click();
          const deleteResponse = await deleteResponsePromise;
          expect(deleteResponse.ok()).toBe(true);
          await expect(temporaryRow).not.toBeVisible();
        }
      }

      if (originalMode) {
        const restoreResult = await page.evaluate(async (modeKey) => {
          let token: string | null = null;
          try {
            const rawAuthState = localStorage.getItem('auth-storage');
            const authState = rawAuthState ? JSON.parse(rawAuthState) as { state?: { token?: string | null } } : null;
            token = authState?.state?.token ?? null;
          } catch {
            // The authenticated UI remains the source of truth if storage is malformed.
          }
          const response = await fetch('/api/auth/preferences', {
            method: 'PUT',
            headers: {
              'Content-Type': 'application/json',
              ...(token ? { Authorization: `Bearer ${token}` } : {}),
            },
            body: JSON.stringify({ default_learning_mode: modeKey }),
          });
          return { ok: response.ok, status: response.status };
        }, originalMode);
        expect(restoreResult.ok).toBe(true);
      }
    }
  });
});
