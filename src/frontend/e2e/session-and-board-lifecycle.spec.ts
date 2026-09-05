import { test, expect, type Page } from '@playwright/test';

// Targeted e2e (two specs, explicit filters only — never the full suite):
//
// 1. session isolation: login -> logout -> login as a different user must
//    not leave the first user's identity or data visible to the second.
// 2. board lifecycle: create -> appears in the list -> delete -> disappears
//    and a direct authenticated GET of its id returns 404.

async function loginAs(page: Page, username: string, password: string) {
  await page.goto('/login');
  // Force English so the assertions match the en locale regardless of the
  // browser's default language (same approach as e2e/auth.setup.ts).
  await page.evaluate(() => {
    localStorage.setItem('i18nextLng', 'en');
    localStorage.setItem('aac_assistant_locale', 'en');
  });
  await page.reload();
  await page.locator('#username').fill(username);
  await page.locator('#password').fill(password);
  await page.locator('button[type="submit"]').click();
  await expect(page).toHaveURL('/', { timeout: 20000 });
  await expect(
    page.getByRole('button', { name: /sign out|cerrar/i }),
  ).toBeVisible({ timeout: 20000 });
}

test.describe('Session isolation and board lifecycle', () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test('login-logout-login shows only the new user\u2019s session', async ({ page }) => {
    await loginAs(page, 'admin1', 'Admin123');

    // Admin-only nav link proves whose session is active.
    await expect(page.getByRole('link', { name: 'Admins' })).toBeVisible();

    await page.getByRole('button', { name: /sign out|cerrar/i }).click();
    await expect(page).toHaveURL(/\/login/, { timeout: 15000 });

    // Second user: student1. The student roster is account-scoped; the UI
    // must reflect student1, never admin1's links or identity.
    await loginAs(page, 'student1', 'Student123');

    await expect(page.getByRole('link', { name: 'Admins' })).toHaveCount(0);
    const body = await page.locator('body').innerText();
    expect(body).not.toContain('admin1');
  });

  test('board create appears in list, delete removes it and direct GET returns 404', async ({ page }) => {
    await loginAs(page, 'admin1', 'Admin123');

    await page.goto('/boards');
    await expect(page.getByRole('button', { name: 'New Board' })).toBeVisible({ timeout: 20000 });

    await page.getByRole('button', { name: 'New Board' }).click();
    await page.locator('#new-board-name').fill('E2E Lifecycle Board');
    const createResponse = page.waitForResponse(
      (res) => res.url().includes('/api/boards') && res.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Create Board' }).click();
    const created = await createResponse;
    const boardId = (await created.json()) as { id: number };
    expect(boardId.id).toBeGreaterThan(0);

    // The new board renders in the grid.
    const card = page.locator('div.bg-surface', { hasText: 'E2E Lifecycle Board' }).first();
    await expect(card).toBeVisible({ timeout: 15000 });

    // Delete through the card's Delete button + confirm dialog.
    await card.getByRole('button', { name: 'Delete' }).click();
    await page.getByRole('button', { name: 'Delete' }).last().click();
    await expect(page.locator('div.bg-surface', { hasText: 'E2E Lifecycle Board' })).toHaveCount(0, {
      timeout: 15000,
    });

    // Direct authenticated GET of the deleted id must 404 (fetch runs in the
    // page origin so the app's Bearer token from localStorage applies).
    const status = await page.evaluate(async (id) => {
      const raw = localStorage.getItem('auth-storage');
      const token = raw ? (JSON.parse(raw)?.state?.token as string | undefined) : undefined;
      const res = await fetch(`/api/boards/${id}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      return res.status;
    }, boardId.id);
    expect(status).toBe(404);
  });
});
