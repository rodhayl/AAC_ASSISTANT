import { test, expect } from '@playwright/test';

test.describe('Advanced Scenarios', () => {
  test.use({ storageState: 'playwright/.auth/admin.json' });

  test('should handle offline mode', async ({ page }) => {
    await page.goto('/');

    // Check if we are online first
    const boardsLink = page.locator('a[href="/boards"]').first();
    await expect(boardsLink).toBeVisible();

    try {
      // Simulate offline
      await page.context().setOffline(true);
      await page.evaluate(() => window.dispatchEvent(new Event('offline')));

      // Should see offline indicator
      await expect(page.getByRole('status').filter({ hasText: /offline|conexión/i })).toBeVisible({ timeout: 15000 });

      // Link should still be visible
      await expect(boardsLink).toBeVisible();
      // Navigate to boards via UI (client-side routing)
      // Use force: true to click even if overlay/banner is present (though it shouldn't cover)
      await boardsLink.click({ force: true });
      // The production SPA keeps the route but renders its retry boundary when
      // API calls are unavailable offline.
      await expect(page).toHaveURL(/\/boards/);
      await expect(page.getByText(/something went wrong|algo salió mal/i)).toBeVisible();

      // Go back online
      await page.context().setOffline(false);
      await page.evaluate(() => window.dispatchEvent(new Event('online')));

      // Banner should disappear
      await expect(page.getByRole('status').filter({ hasText: /offline|conexión/i })).not.toBeVisible();
    } finally {
      try {
        await page.context().setOffline(false);
      } catch {
        // The context may already be closed after a navigation failure.
      }
      await page.evaluate(() => window.dispatchEvent(new Event('online'))).catch(() => undefined);
    }
  });

  test('should view notifications', async ({ page }) => {
    await page.goto('/');
    // Click bell icon
    await page.getByLabel(/notifications|notificaciones/i).click();

    // Verify panel
    await expect(page.getByRole('button', { name: /mark all|marcar/i })).toBeVisible();
  });

  test('receives a notification via SSE without reload', async ({ page, playwright }) => {
    // Open the panel; the Navbar's SSE stream subscribes on mount.
    await page.goto('/');
    await page.getByLabel(/notifications|notificaciones/i).click();
    await expect(page.getByRole('button', { name: /mark all|marcar/i })).toBeVisible();

    // The admin's own token lives in localStorage (zustand persist), not a
    // cookie, so page.request cannot authenticate. Extract it to call the
    // admin-only notification endpoint.
    const token = await page.evaluate(() => {
      const raw = localStorage.getItem('auth-storage');
      if (!raw) return null;
      try { return JSON.parse(raw).state.token as string | null; } catch { return null; }
    });
    expect(token).toBeTruthy();
    const adminId = JSON.parse(Buffer.from(token!.split('.')[1], 'base64').toString()).user_id as number;

    // Create a notification for the admin themself.
    const title = `SSE ${Date.now()}`;
    const apiContext = await playwright.request.newContext({
      baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:8086',
    });
    const res = await apiContext.post('/api/notifications', {
      headers: { Authorization: `Bearer ${token}` },
      data: { user_id: adminId, title, message: 'SSE push works', notification_type: 'info', priority: 'normal' },
    });
    expect(res.ok()).toBeTruthy();
    await apiContext.dispose();

    // The stream pushes it into the open panel without a reload.
    await expect(page.getByText(title)).toBeVisible({ timeout: 15000 });
  });

  test('should redirect legacy speak mode to the communication board', async ({ page }) => {
    await page.goto('/play/1');
    await expect(page).toHaveURL(/\/communication\?boardId=1$/);
  });

  test('should handle 404', async ({ page }) => {
    await page.goto('/non-existent-page');
    await expect(page.getByText(/page not found/i)).toBeVisible();
  });

  test('should handle offline conflicts', async ({ page }) => {

    // 0. Go to boards page FIRST (while online)
    await page.goto('/boards');
    await expect(page.locator('.animate-spin')).not.toBeVisible();

    try {
      // 1. Open a real board while online so the editor can load its data.
      const editLink = page.getByRole('link', { name: /edit board|editar/i }).first();
      await expect(editLink).toBeVisible();
      await editLink.click();
      const settingsButton = page.getByLabel(/board settings|configuración del tablero/i).first();
      await expect(settingsButton).toBeVisible();

      // 2. Mock the conflict response before replaying the offline mutation.
      await page.route('**/api/boards/*', async route => {
        if (route.request().method() === 'PUT' || route.request().method() === 'POST') {
          await route.fulfill({
            status: 409,
            contentType: 'application/json',
            body: JSON.stringify({ detail: 'Conflict detected: Server has newer version' }),
          });
          return;
        }
        await route.continue();
      });

      // 3. Queue a real board metadata mutation while offline.
      await page.context().setOffline(true);
      await page.evaluate(() => window.dispatchEvent(new Event('offline')));
      await settingsButton.click();
      const dialog = page.getByRole('dialog');
      await expect(dialog).toBeVisible();
      const aiToggle = dialog.locator('#aiEnabledEdit');
      if (await aiToggle.isChecked()) {
        await aiToggle.uncheck();
      }
      await dialog.getByLabel(/name|nombre/i).fill('Conflict Board');
      await dialog.getByRole('button', { name: /save settings|guardar/i }).click();

      // 4. Go online so the queued mutation is replayed into the forced 409.
      await page.context().setOffline(false);
      await page.evaluate(() => window.dispatchEvent(new Event('online')));
      // 5. The conflict panel must expose the failed mutation.
      await expect(page.getByRole('heading', { name: /offline conflicts|conflictos/i })).toBeVisible({ timeout: 10000 });
      await expect(page.getByRole('button', { name: /retry request|reintentar/i })).toBeVisible();
    } finally {
      try {
        await page.context().setOffline(false);
      } catch {
        // The context may already be closed after a navigation failure.
      }
      await page.evaluate(() => window.dispatchEvent(new Event('online'))).catch(() => undefined);
    }
  });
});