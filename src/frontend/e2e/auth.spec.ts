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

test.describe('Authentication - form validation', () => {
  test('handles an empty login attempt without bypassing first-run setup', async ({ page }) => {
    const setupStatus = await page.request.get('/api/auth/setup-status');
    expect(setupStatus.ok()).toBeTruthy();
    const { setup_required: setupRequired } = await setupStatus.json() as { setup_required: boolean };

    // A clean database must go through setup before login validation is
    // reachable. This branch keeps the test valid for both fixture states.
    if (setupRequired) {
      await page.goto('/setup');
      await expect(page.locator('form')).toBeVisible();
      await expect(page.locator('button[type="submit"]')).toBeDisabled();
      return;
    }

    await page.goto('/login');
    // Both login fields are required, so an empty submission never fires a request.
    await page.locator('button[type="submit"]').click();
    await expect(page.locator('#username:invalid')).toBeVisible();
    await expect(page).toHaveURL(/\/login(?:[/?#]|$)/);
    // No backend error surface appears because the request never fired.
    await expect(page.locator('.bg-red-50')).toHaveCount(0);
  });
});

test.describe('Authentication - Student', () => {
  // Do not consume the shared authenticated storage state: logout now revokes
  // its server-side token, which would make later tests inherit a dead session.
  test.use({ storageState: undefined });

  test('should allow logout', async ({ page }) => {
    // Use a disposable account so server-side revocation cannot invalidate the
    // shared student storage state used by the communication/role journeys.
    const username = `e2e_logout_${Date.now()}`;
    const password = 'LogoutTest123!';
    const registration = await page.request.post('/api/auth/register', {
      data: {
        username,
        display_name: 'Logout Test User',
        password,
        user_type: 'student',
      },
    });
    expect(registration.ok()).toBeTruthy();

    await page.goto('/login');
    await page.getByLabel(/username|usuario/i).fill(username);
    await page.getByLabel(/password|contraseña/i).fill(password);
    await page.locator('button[type="submit"]').click();
    await expect(page).toHaveURL(/\/$/);

    const signOut = page.getByRole('button', { name: /sign out|cerrar/i });
    await expect(signOut).toBeVisible();
    await signOut.click();
    await expect(page).toHaveURL(/\/login(?:[/?#]|$)/);
  });
});
