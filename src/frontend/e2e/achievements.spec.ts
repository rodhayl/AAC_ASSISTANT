import { test, expect } from '@playwright/test';

test.describe('Achievements', () => {
  test.use({ storageState: 'playwright/.auth/student.json' });

  test('should view achievements', async ({ page }) => {
    await page.goto('/achievements');
    await expect(page.locator('.animate-spin')).not.toBeVisible({ timeout: 20000 });
    await expect(page.locator('h1').filter({ hasText: /achievements|logros/i })).toBeVisible();
    await expect(page.locator('.space-y-6')).toBeVisible();
  });

  test('should display locked and unlocked achievements', async ({ page }) => {
    // Mock API response
    // Match /api/achievements/user/:id
    await page.route('**/api/achievements/user/*', async route => {
        const url = route.request().url();
        if (url.includes('/points')) {
            await route.fulfill({ status: 200, body: '150' });
            return;
        }
        if (url.includes('/check')) {
            await route.fulfill({ status: 200 });
            return;
        }
        
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify([
                {
                    name: 'First Steps',
                    description: 'Create your first board',
                    icon: '⭐',
                    category: 'General',
                    earned_at: new Date().toISOString(),
                    progress: 100,
                    points: 10
                },
                {
                    name: 'Social Butterfly',
                    description: 'Chat for 10 minutes',
                    icon: '💬',
                    category: 'Social',
                    earned_at: null,
                    progress: 50, // 50%
                    points: 20
                }
            ])
        });
    });

    await page.goto('/achievements');
    await expect(page.locator('.animate-spin')).not.toBeVisible();

    // Verify Unlocked
    const unlockedCard = page.locator('.bg-white').filter({ hasText: 'First Steps' });
    await expect(unlockedCard).toBeVisible();
    await expect(unlockedCard).not.toHaveClass(/opacity-70|grayscale/);

    // Verify Locked
    const lockedCard = page.locator('.bg-white').filter({ hasText: 'Social Butterfly' });
    await expect(lockedCard).toBeVisible();
    // Check for locked state
    await expect(lockedCard).toHaveClass(/opacity-70|grayscale/);
    await expect(lockedCard).toContainText('50%');
    await expect(lockedCard.locator('.lucide-lock')).toBeVisible();
  });
});
