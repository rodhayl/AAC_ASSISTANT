import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test.describe('Automated Accessibility Scans (Axe Core)', () => {
  test('First-run setup page has no serious/critical accessibility violations', async ({ page }) => {
    await page.goto('/setup');
    await page.waitForSelector('#setup-admin-form, main#main-content', { state: 'visible', timeout: 5000 }).catch(() => {});
    
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
    await page.waitForSelector('form, main#main-content', { state: 'visible', timeout: 5000 }).catch(() => {});

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
      await page.waitForSelector('main#main-content', { state: 'visible' });

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
      await page.waitForSelector('main#main-content', { state: 'visible' });

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
      await page.waitForSelector('main#main-content', { state: 'visible' });

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
