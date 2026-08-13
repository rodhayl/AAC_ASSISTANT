import { test, expect } from '@playwright/test';

test.describe('Board Refresh Bug', () => {
  test.use({ storageState: 'playwright/.auth/student.json' });

  test('should maintain board count after force refresh', async ({ page }) => {
    // 1. Go to boards page
    await page.goto('/boards');
    
    // 2. Wait for boards to load
    await expect(page.locator('.animate-spin')).not.toBeVisible();
    
    // Count initial boards. The current seeded student may have no boards, so
    // create one to keep this regression self-contained.
    // The grid contains board cards. We count the cards, not the links inside them, to be more precise.
    const boardCards = page.locator('.grid > div.relative');
    let initialCount = await boardCards.count();
    let createdBoardName: string | null = null;
    if (initialCount === 0) {
      createdBoardName = `Refresh Test ${Date.now()}`;
      await page.getByRole('button', { name: /new board|nuevo|create board|crear/i }).first().click();
      await page.getByLabel(/board name|nombre/i).fill(createdBoardName);
      await page.getByRole('button', { name: /create|crear/i }).click();
      await expect(page.getByText(createdBoardName)).toBeVisible({ timeout: 30000 });
      initialCount = await boardCards.count();
    }
    console.log(`Initial board count: ${initialCount}`);
    
    expect(initialCount).toBeGreaterThan(0);

    // 3. Click "Force Refresh"
    const refreshBtn = page.getByTestId('force-refresh');
    await expect(refreshBtn).toBeVisible();
    await refreshBtn.click();
    
    // 4. Wait for refresh (loading spinner appears then disappears)
    // Wait for at least one spinner or a network request
    await page.waitForTimeout(1000); 
    await expect(page.locator('.animate-spin')).not.toBeVisible();

    // 5. Verify count matches
    const finalCount = await boardCards.count();
    console.log(`Final board count: ${finalCount}`);
    
    expect(finalCount).toBe(initialCount);

    if (createdBoardName) {
      const card = page.locator('.grid > div.relative').filter({ hasText: createdBoardName });
      await card.getByRole('button', { name: /delete|eliminar/i }).click();
      await page.locator('div[role="dialog"]').getByRole('button', { name: /delete|eliminar/i }).click();
    }
  });
});
