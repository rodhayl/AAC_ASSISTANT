import { test, expect } from '@playwright/test';

// Symbol rendering is critical for AAC users: a missing/broken image must
// degrade to the placeholder icon instead of a broken <img>. The seeded
// library ships symbols without image_path (always placeholder), so this spec
// creates a symbol with a guaranteed-404 image path via the real API, verifies
// the SymbolImage onError fallback, and then removes it so the shared symbol
// library is left unchanged for other specs.
test.describe('Symbol image rendering', () => {
  test.use({ storageState: 'playwright/.auth/admin.json' });

  test('a broken symbol image falls back to the placeholder icon', async ({ page, playwright }) => {
    // Read the admin token so the setup can create a symbol via the API.
    await page.goto('/');
    const token = await page.evaluate(() => {
      const raw = localStorage.getItem('auth-storage');
      if (!raw) return null;
      try { return (JSON.parse(raw) as { state?: { token?: string } }).state?.token ?? null; } catch { return null; }
    });
    expect(token).toBeTruthy();

    const baseURL = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:8086';
    const apiContext = await playwright.request.newContext({ baseURL });
    const headers = { Authorization: `Bearer ${token}` };
    const label = `BrokenImg ${Date.now()}`;

    let symbolId: number | null = null;
    try {
      const createRes = await apiContext.post('/api/boards/symbols', {
        headers,
        data: {
          label,
          category: 'general',
          // Guaranteed-missing upload: the StaticFiles mount returns 404, which
          // drives the SymbolImage onError fallback.
          image_path: '/uploads/symbols/e2e-missing-image.png',
        },
      });
      expect(createRes.ok()).toBeTruthy();
      symbolId = (await createRes.json()).id as number;

      await page.goto('/symbols');
      await expect(page.locator('.animate-spin')).not.toBeVisible({ timeout: 20000 });

      // The default sort orders by id ascending, so a freshly created symbol
      // sits on the last page of the 17k-symbol library; search for it.
      await page.getByPlaceholder(/buscar símbolos|search symbols/i).fill(label);
      const card = page.locator('div.flex.flex-col.gap-2', { hasText: label }).first();
      await expect(card).toBeVisible({ timeout: 15000 });

      // After the 404 the <img> is removed and replaced by the placeholder icon.
      await expect(card.locator('img')).toHaveCount(0, { timeout: 10000 });
      await expect(card.locator('svg.lucide-image')).toBeVisible();
    } finally {
      if (symbolId != null) {
        await apiContext.delete(`/api/boards/symbols/${symbolId}`, { headers });
      }
      await apiContext.dispose();
    }
  });
});
