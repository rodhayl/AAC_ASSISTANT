import { test, expect } from '@playwright/test';

test.describe('Authentication', () => {
  test('should allow a new user to register', async ({ page }) => {
    page.on('console', msg => console.log(`[Browser] ${msg.text()}`));
    
    // Ensure we are logged out
    await page.context().clearCookies();
    await page.goto('/register');
    
    const username = `testuser_${Date.now()}`;
    await page.getByLabel(/username|usuario/i).fill(username);
    await page.getByLabel(/display name|nombre/i).fill(`Test User ${username}`);
    await page.getByLabel(/password|contraseña/i).fill('TestPass123!');
    // Role defaults to Student
    await page.locator('button[type="submit"]').click();
    
    // Should redirect to dashboard (auto-login) or login
    try {
        await expect(page).toHaveURL(/\/login|\/$/, { timeout: 15000 });
        const url = page.url();
        console.log(`[AuthDebug] Redirected to: ${url}`);
        
        if (url.endsWith('/login')) {
             // If redirected to login, perform login
             await page.getByLabel(/username|usuario/i).fill(username);
             await page.getByLabel(/password|contraseña/i).fill('TestPass123!');
             await page.locator('button[type="submit"]').click();
             await expect(page).toHaveURL('/');
        }
    } catch (e) {
        console.log(`[AuthDebug] Current URL: ${page.url()}`);
        // If failed, check for error message
        if (await page.locator('.bg-red-50').isVisible()) {
             const error = await page.locator('.bg-red-50').textContent();
             console.log(`[Registration Error] ${error}`);
             throw new Error(`Registration failed: ${error}`);
        }
        throw e;
    }
    
    await expect(page.getByText(/my boards|mis tableros/i)).toBeVisible();
  });
});

test.describe('Authentication - Student', () => {
  test.use({ storageState: 'playwright/.auth/student.json' });

  test('should allow logout', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: /sign out|cerrar/i }).click();
    await expect(page).toHaveURL('/login');
  });
});
