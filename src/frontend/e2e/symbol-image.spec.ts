import { test, expect } from '@playwright/test';

// Symbol rendering is critical for AAC users: a missing/broken image must
// degrade to the placeholder icon instead of a broken <img>, and a symbol
// with a real image must actually render pixels. The seeded library ships
// symbols without image_path (always placeholder), so this spec creates its
// own symbols through the real API — one with a guaranteed-404 image path,
// one via a real multipart upload — and removes them afterwards so the
// shared symbol library is left unchanged for other specs.
test.describe('Symbol image rendering', () => {
  test.use({ storageState: 'playwright/.auth/admin.json' });

  // The stored access token may be expired when the suite starts (auth states
  // are reused across runs); the app refreshes it silently during checkAuth.
  // Waiting for an authenticated-UI marker before reading the token makes the
  // API calls below deterministic instead of racing the silent refresh.
  async function readAdminToken(page: import('@playwright/test').Page): Promise<string> {
    await page.goto('/');
    await expect(
      page.getByRole('button', { name: /sign out|cerrar/i }),
    ).toBeVisible({ timeout: 20000 });
    const token = await page.evaluate(() => {
      const raw = localStorage.getItem('auth-storage');
      if (!raw) return null;
      try { return (JSON.parse(raw) as { state?: { token?: string } }).state?.token ?? null; } catch { return null; }
    });
    expect(token).toBeTruthy();
    return token as string;
  }

  test('a broken symbol image falls back to the placeholder icon', async ({ page, playwright }) => {
    // Read the admin token so the setup can create a symbol via the API.
    const token = await readAdminToken(page);

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

  test('an uploaded symbol image renders as a real image, not the placeholder', async ({ page, playwright }) => {
    const token = await readAdminToken(page);

    const baseURL = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:8086';
    const apiContext = await playwright.request.newContext({ baseURL });
    const headers = { Authorization: `Bearer ${token}` };
    const label = `RealImg ${Date.now()}`;
    // Minimal valid 1x1 PNG; the backend verifies uploads with Pillow, so a
    // fake bytes payload would be rejected by the multipart endpoint.
    const pngBase64 =
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=';
    const pngBuffer = Buffer.from(pngBase64, 'base64');

    let symbolId: number | null = null;
    try {
      // Upload through the real multipart endpoint so image_path points at a
      // file the StaticFiles mount actually serves.
      const uploadRes = await apiContext.post('/api/boards/symbols/upload', {
        headers,
        multipart: {
          label,
          description: 'E2E rendered-image verification symbol',
          category: 'general',
          keywords: 'e2e',
          language: 'en',
          file: {
            name: 'e2e-symbol.png',
            mimeType: 'image/png',
            buffer: pngBuffer,
          },
        },
      });
      expect(uploadRes.ok()).toBeTruthy();
      const uploaded = (await uploadRes.json()) as { id: number; image_path: string };
      symbolId = uploaded.id;
      expect(uploaded.image_path).toMatch(/^\/uploads\/symbols\/.+\.png$/);

      await page.goto('/symbols');
      await expect(page.locator('.animate-spin')).not.toBeVisible({ timeout: 20000 });
      await page.getByPlaceholder(/buscar símbolos|search symbols/i).fill(label);
      const card = page.locator('div.flex.flex-col.gap-2', { hasText: label }).first();
      await expect(card).toBeVisible({ timeout: 15000 });

      // SymbolImage renders a real <img> (never the placeholder icon) whose
      // src points at the stored upload, and the pixels actually decode:
      // naturalWidth > 0 proves the backend served the file, i.e. the image
      // did not silently 404 into the onError fallback. The src may carry an
      // absolute backend origin in dev; matching a suffix keeps both forms
      // (same-origin production and cross-origin dev) valid.
      const img = card.locator('img');
      await expect(img).toHaveCount(1, { timeout: 10000 });
      await expect(card.locator('svg.lucide-image')).toHaveCount(0);
      await expect(img).toHaveAttribute('src', new RegExp(`${uploaded.image_path.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}$`));
      await expect(img).toHaveAttribute('alt', label);
      await expect
        .poll(async () => img.evaluate((el) => (el as HTMLImageElement).naturalWidth), {
          timeout: 10000,
          message: 'the uploaded PNG must decode pixels (backend must serve it)',
        })
        .toBeGreaterThan(0);
    } finally {
      if (symbolId != null) {
        await apiContext.delete(`/api/boards/symbols/${symbolId}`, { headers });
      }
      await apiContext.dispose();
    }
  });
});
