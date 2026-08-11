import { test, expect } from '@playwright/test';

test.describe('Authentication', () => {
  test('should allow a new user to register', async ({ page }) => {
    page.on('console', msg => console.log(`[Browser] ${msg.text()}`));

    const username = process.env.E2E_REGISTRATION_USERNAME || 'e2e_registration_user';
    const password = process.env.E2E_REGISTRATION_PASSWORD || 'TestPass123!';
    const displayName = `Test User ${username}`;

    // Reuse the deterministic fixture on reruns. This keeps the test isolated
    // from the production registration rate limit while still exercising public
    // registration on a clean database.
    const existingLogin = await page.request.post('/api/auth/token', {
      form: { username, password },
    });
    const alreadyRegistered = existingLogin.ok();

    await page.context().clearCookies();
    if (alreadyRegistered) {
      await page.goto('/login');
      await page.getByLabel(/username|usuario/i).fill(username);
      await page.getByLabel(/password|contraseña/i).fill(password);
      await page.locator('button[type="submit"]').click();
      await expect(page).toHaveURL('/');
    } else {
      await page.goto('/register');
      await page.getByLabel(/username|usuario/i).fill(username);
      await page.getByLabel(/display name|nombre/i).fill(displayName);
      await page.getByLabel(/password|contraseña/i).fill(password);
      await page.locator('button[type="submit"]').click();

      try {
        // Registration does not auto-login; finish the journey through login.
        await expect(page).toHaveURL(/\/login|\/$/, { timeout: 15000 });
        if (page.url().endsWith('/login')) {
          await page.getByLabel(/username|usuario/i).fill(username);
          await page.getByLabel(/password|contraseña/i).fill(password);
          await page.locator('button[type="submit"]').click();
          await expect(page).toHaveURL('/');
        }
      } catch (error) {
        console.log(`[AuthDebug] Current URL: ${page.url()}`);
        const errorMessage = await page.locator('.bg-red-50').textContent().catch(() => null);
        if (errorMessage) {
          throw new Error(`Registration failed: ${errorMessage}`);
        }
        throw error;
      }
    }

    await expect(page.getByText(/my boards|mis tableros/i)).toBeVisible();
  });
});

test.describe('Authentication - Student', () => {
  test.use({ storageState: 'playwright/.auth/student.json' });

  test('should allow logout', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveURL(/\/$/);
    const signOut = page.getByRole('button', { name: /sign out|cerrar/i });
    await expect(signOut).toBeVisible();
    await signOut.click();
    await expect(page).toHaveURL(/\/login(?:[/?#]|$)/);
  });
});
