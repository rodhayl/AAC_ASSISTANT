import { test, expect } from '@playwright/test';

test.describe('Achievements', () => {
  test.use({ storageState: 'playwright/.auth/student.json' });

  test('should view achievements', async ({ page }) => {
    await page.goto('/achievements');
    await expect(page.locator('.animate-spin')).not.toBeVisible({ timeout: 20000 });
    await expect(page.locator('h1').filter({ hasText: /achievements|logros/i })).toBeVisible();
    // The three seeded system achievements render from real data.
    await expect(page.getByText('First Steps', { exact: true })).toBeVisible();
  });

  test('should display seeded achievements with locked progress state', async ({ page }) => {
    await page.goto('/achievements');
    await expect(page.locator('.animate-spin')).not.toBeVisible({ timeout: 20000 });

    // A fresh student has earned none of the seeded system achievements, so
    // every card must render from real data in the locked (grayscale) state.
    for (const name of ['First Steps', 'Vocabulary Explorer', 'Quick Learner']) {
      const card = page
        .locator('.bg-white')
        .filter({ hasText: name })
        .first();
      await expect(card).toBeVisible();
      await expect(card).toHaveClass(/opacity-70|grayscale/);
      await expect(card.locator('.lucide-lock')).toBeVisible();
    }
  });
});
