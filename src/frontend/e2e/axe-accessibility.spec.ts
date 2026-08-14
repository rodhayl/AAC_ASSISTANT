import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test.describe('Automated Accessibility Scans (Axe Core)', () => {
  test('First-run setup page has no serious/critical accessibility violations', async ({ page }) => {
    await page.goto('/setup');
    await expect(page.locator('main#main-content, form')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('#setup-admin-form, input#username, button[type="submit"]').first()).toBeVisible({ timeout: 10000 });
    
    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();

    const criticalViolations = results.violations.filter(
      (v) => v.impact === 'serious' || v.impact === 'critical'
    );
    expect(criticalViolations).toEqual([]);
  });

  test('Login page has no serious/critical accessibility violations', async ({ page }) => {
    await page.goto('/login');
    await expect(page.locator('#username')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('#password')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('button[type="submit"]')).toBeVisible({ timeout: 10000 });

    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();

    const criticalViolations = results.violations.filter(
      (v) => v.impact === 'serious' || v.impact === 'critical'
    );
    expect(criticalViolations).toEqual([]);
  });

  test.describe('Authenticated Student Views', () => {
    test.use({ storageState: 'playwright/.auth/student.json' });

    test('Communication Board has no serious/critical accessibility violations', async ({ page }) => {
      await page.goto('/communication');
      await expect(page.locator('main#main-content')).toBeVisible({ timeout: 10000 });

      // If on board picker, open the default board so actual board grid and sentence controls are scanned
      const boardPickerItem = page.getByRole('button', { name: /General Communication/ }).first();
      if (await boardPickerItem.isVisible({ timeout: 2000 }).catch(() => false)) {
        await boardPickerItem.click();
      }

      await expect(page.locator('.grid button, [role=grid] button').first()).toBeVisible({ timeout: 10000 });

      const results = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
        .analyze();

      const criticalViolations = results.violations.filter(
        (v) => v.impact === 'serious' || v.impact === 'critical'
      );
      expect(criticalViolations).toEqual([]);
    });

    test('Learning Mode has no serious/critical accessibility violations', async ({ page }) => {
      await page.goto('/learning');
      await expect(page.locator('main#main-content')).toBeVisible({ timeout: 10000 });

      // Confirm learning interactive controls are rendered
      const startOrQuestionBtn = page.locator('button:has-text("Start"), button:has-text("Iniciar"), button:has-text("Ask"), button:has-text("Preguntar")').first();
      await expect(startOrQuestionBtn).toBeVisible({ timeout: 10000 });

      const results = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
        .analyze();

      const criticalViolations = results.violations.filter(
        (v) => v.impact === 'serious' || v.impact === 'critical'
      );
      expect(criticalViolations).toEqual([]);
    });
  });

  test.describe('Authenticated Admin Views', () => {
    test.use({ storageState: 'playwright/.auth/admin.json' });

    test('Settings & Accessibility panel has no serious/critical accessibility violations', async ({ page }) => {
      await page.goto('/settings');
      await expect(page.locator('main#main-content')).toBeVisible({ timeout: 10000 });

      // Confirm settings panel is rendered
      await expect(page.locator('#settings-appearance-heading, #pref-dark-mode, [role="tablist"]').first()).toBeVisible({ timeout: 10000 });

      const results = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
        .analyze();

      const criticalViolations = results.violations.filter(
        (v) => v.impact === 'serious' || v.impact === 'critical'
      );
      expect(criticalViolations).toEqual([]);
    });
  });
});
