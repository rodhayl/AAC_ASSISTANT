import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import type { AxeResults } from 'axe-core';

function summarizeAxeResults(results: AxeResults, name: string) {
  const critical = results.violations.filter((v) => v.impact === 'critical');
  const serious = results.violations.filter((v) => v.impact === 'serious');
  const moderate = results.violations.filter((v) => v.impact === 'moderate');
  const minor = results.violations.filter((v) => v.impact === 'minor');
  const incomplete = results.incomplete;

  console.log(
    `[Axe: ${name}] critical: ${critical.length}, serious: ${serious.length}, ` +
    `moderate: ${moderate.length}, minor: ${minor.length}, incomplete: ${incomplete.length}`
  );
  return { critical, serious, moderate, minor, incomplete };
}

test.describe('Automated Accessibility Scans (Axe Core)', () => {
  test('First-run setup page has no serious/critical accessibility violations', async ({ page }) => {
    await page.goto('/setup');
    await expect(page.locator('main#main-content, form')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('#setup-admin-form, input#username, button[type="submit"]').first()).toBeVisible({ timeout: 10000 });

    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();

    const { critical, serious } = summarizeAxeResults(results, 'Setup Page');
    expect([...critical, ...serious]).toEqual([]);
  });

  test('Login page has no serious/critical accessibility violations', async ({ page }) => {
    await page.goto('/login');
    await expect(page.locator('#username')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('#password')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('button[type="submit"]')).toBeVisible({ timeout: 10000 });

    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();

    const { critical, serious } = summarizeAxeResults(results, 'Login Page');
    expect([...critical, ...serious]).toEqual([]);
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

      const { critical, serious } = summarizeAxeResults(results, 'Communication Board');
      expect([...critical, ...serious]).toEqual([]);
    });

    test('Learning session active view has no serious/critical accessibility violations', async ({ page }) => {
      await page.goto('/learning');
      await expect(page.locator('main#main-content')).toBeVisible({ timeout: 10000 });

      const startBtn = page.getByTestId('learning-session-start');
      if (await startBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
        await startBtn.click();
        await expect(page.getByTestId('learning-session-active')).toBeVisible({ timeout: 10000 });
      }

      const results = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
        .analyze();

      const { critical, serious } = summarizeAxeResults(results, 'Learning View');
      expect([...critical, ...serious]).toEqual([]);
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

      const { critical, serious } = summarizeAxeResults(results, 'Settings View');
      expect([...critical, ...serious]).toEqual([]);
    });
  });
});
