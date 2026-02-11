import { test, expect } from '@playwright/test';

test.describe('Dashboard - Student', () => {
  test.use({ storageState: 'playwright/.auth/student.json' });

  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('should display student welcome message', async ({ page }) => {
    // Wait for translation to load
    await expect(page.getByRole('heading', { level: 1 }).last()).toBeVisible();
    // Use last h1 which is the page title usually
    await expect(page.locator('h1').last()).toContainText(/welcome|bienvenido/i);
  });

  test('should show quick actions', async ({ page }) => {
    // Check for dashboard cards links
    await expect(page.getByRole('link', { name: /manage|view|gestionar|ver/i }).first()).toBeVisible();
  });

  test('should show statistics cards', async ({ page }) => {
    // Wait for cards to load
    await expect(page.locator('.bg-white').first()).toBeVisible();
    // Check for any text resembling stats (English or Spanish)
    await expect(page.locator('body')).toContainText(/streak|racha/i);
    await expect(page.locator('body')).toContainText(/achievements|logros/i);
  });
});

test.describe('Dashboard - Admin', () => {
  test.use({ storageState: 'playwright/.auth/admin.json' });

  test('should show admin specific links', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('link', { name: /teachers|profesores/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /students|estudiantes/i })).toBeVisible();
  });
});
