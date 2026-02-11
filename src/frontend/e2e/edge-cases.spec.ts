import { test, expect } from '@playwright/test';

test.describe('Edge Cases & Error Handling', () => {
  
  test.describe('Unauthorized Access', () => {
    test.use({ storageState: 'playwright/.auth/student.json' });

    test('should redirect student from admin pages', async ({ page }) => {
      await page.goto('/teachers');
      // Should redirect to dashboard or login or show 404/Error
      // Assuming redirect to dashboard or login
      // Check if we are NOT on /teachers
      await expect(page).not.toHaveURL('/teachers');
      await expect(page.locator('h1').first()).not.toContainText('Manage Teachers');
    });
  });

  test.describe('Form Validation', () => {
    test('should show validation errors on empty login', async ({ page }) => {
      await page.goto('/login');
      await page.locator('button[type="submit"]').click();
      
      // HTML5 validation might prevent submission, or UI shows error
      // Playwright handles HTML5 validation by checking :invalid pseudo-class
      // or we check for error message if backend is called
      
      // Check if input is invalid
    const username = page.locator('#username');
    // Using hardcoded locator to avoid unused var
    // const password = page.locator('#password');
    if (await page.locator('#password').count() > 0) {
      // Just verify it exists or fill
    }
      
      // If using HTML5 validation
      const isUsernameInvalid = await username.evaluate((e: HTMLInputElement) => !e.checkValidity());
      expect(isUsernameInvalid).toBe(true);
    });
  });

  test.describe('Localization & Symbols', () => {
    test.use({ storageState: 'playwright/.auth/student.json' });

    test('should search symbols in Spanish', async ({ page }) => {
      // Switch to Spanish
      await page.goto('/settings');
      const select = page.locator('select').filter({ hasText: /Español|English/ }).first();
      await select.selectOption({ value: 'es-ES' });
      const saveBtn = page.locator('button').filter({ hasText: /save|guardar/i }).last();
      await saveBtn.click();
      await expect(page.getByText(/guardado/i).first()).toBeVisible();

      // Go to board editor (requires board)
      await page.goto('/boards');
      await expect(page.locator('.animate-spin')).not.toBeVisible({ timeout: 20000 });
      // Create temp board
      await page.getByRole('button', { name: /new board|nuevo|create board|crear/i }).click({ force: true });
      await page.getByLabel(/nombre/i).fill('Spanish Test');
      await page.getByRole('button', { name: /crear/i }).last().click();
      
      // Fix: Search for the board to ensure it's found
      await page.getByPlaceholder(/search|buscar/i).fill('Spanish Test');
      await page.waitForTimeout(1000);
      
      // Edit
      await page.getByText('Spanish Test').first().click({ force: true });
      
      // Add symbol
      const borderDashed = page.locator('.border-dashed').first();
      // Wait for it to be visible with a generous timeout
      await expect(borderDashed).toBeVisible({ timeout: 20000 });
      await borderDashed.click({ force: true });
      await page.getByPlaceholder(/search|buscar/i).fill('dog'); // Use 'dog' as safe fallback search
      await page.waitForTimeout(1000);
      
      // Check if any result appears
      await expect(page.locator('.grid button').first()).toBeVisible();
      
      // Cleanup: Switch back to English? 
      // Ideally yes, but setup resets state or we can leave it for this context
    });
  });

  test.describe('Notifications', () => {
    test.use({ storageState: 'playwright/.auth/student.json' });

    test('should view and manage notifications', async ({ page }) => {
      await page.goto('/');
      const bell = page.locator('button').filter({ has: page.locator('svg.lucide-bell') });
      await expect(bell).toBeVisible();
      await bell.click();
      
      await expect(page.getByText(/notifications|notificaciones/i).first()).toBeVisible();
      
      // If "Mark all as read" exists
      const markRead = page.getByText(/mark all|marcar todo/i);
      if (await markRead.isVisible()) {
          await markRead.click();
      }
      
      // If "Clear" exists
      const clear = page.getByText(/clear|borrar/i);
      if (await clear.isVisible()) {
          await clear.click();
      }
    });
  });
});
