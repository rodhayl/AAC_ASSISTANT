import { test, expect, type Page } from '@playwright/test';

// Arrow-key navigation is a core access path for AAC users who cannot use a
// pointing device: arrows must move the focus between symbol cards, skipping
// empty grid cells, and stop at the grid edge without scrolling the page.
// The CI environment has no boards, so this spec provisions its own 3x3 board
// with deliberate holes (Alpha/hole/Bravo/Charlie) through the real API and
// removes it afterwards, leaving the shared library unchanged for other specs.
test.describe('Communication board arrow-key navigation', () => {
  test.use({ storageState: 'playwright/.auth/admin.json' });

  // The stored access token may be expired when the suite starts (auth states
  // are reused across runs); the app refreshes it silently during checkAuth.
  // Waiting for an authenticated-UI marker before reading the token makes the
  // API calls below deterministic instead of racing the silent refresh.
  async function readAdminToken(page: Page): Promise<string> {
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

  async function focusedCellIndex(page: Page): Promise<string | null> {
    return page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null;
      const cell = el?.closest('[data-cell-index]') as HTMLElement | null;
      return cell?.dataset.cellIndex ?? null;
    });
  }

  test('arrow keys move between symbols, skipping empty cells and stopping at edges', async ({ page, playwright }) => {
    const token = await readAdminToken(page);

    const baseURL = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:8086';
    const apiContext = await playwright.request.newContext({ baseURL });
    const headers = { Authorization: `Bearer ${token}` };
    const boardName = `ArrowNav E2E ${Date.now()}`;

    let boardId: number | null = null;
    try {
      // Pick any three existing library symbols; the startup seed guarantees
      // a non-empty library in every environment this suite runs in.
      const listRes = await apiContext.get('/api/boards/symbols', { headers });
      expect(listRes.ok()).toBeTruthy();
      const listData = await listRes.json();
      const symbols: Array<{ id: number }> = Array.isArray(listData)
        ? listData
        : (listData.symbols ?? listData.items ?? []);
      expect(symbols.length, 'library symbols for the nav fixture').toBeGreaterThanOrEqual(3);

      const userState = await page.evaluate(() => {
        const raw = localStorage.getItem('auth-storage');
        if (!raw) return null;
        try { return JSON.parse(raw) as { state?: { user?: { id: number } } }; } catch { return null; }
      });
      const userId = userState?.state?.user?.id;
      expect(userId).toBeTruthy();

      const createRes = await apiContext.post(`/api/boards/?user_id=${userId}`, {
        headers,
        data: {
          name: boardName,
          description: 'Ephemeral board for arrow-key navigation coverage',
          grid_rows: 3,
          grid_cols: 3,
        },
      });
      expect(createRes.ok()).toBeTruthy();
      boardId = ((await createRes.json()) as { id: number }).id;

      // 3x3 layout with holes: Alpha(0,0) hole(1,0) Bravo(2,0) Charlie(0,1).
      const placements = [
        { symbol_id: symbols[0].id, position_x: 0, position_y: 0, custom_text: 'Alpha' },
        { symbol_id: symbols[1].id, position_x: 2, position_y: 0, custom_text: 'Bravo' },
        { symbol_id: symbols[2].id, position_x: 0, position_y: 1, custom_text: 'Charlie' },
      ];
      for (const placement of placements) {
        const res = await apiContext.post(`/api/boards/${boardId}/symbols`, {
          headers,
          data: placement,
        });
        expect(res.ok()).toBeTruthy();
      }

      await page.goto(`/communication?boardId=${boardId}`);
      const firstCard = page.locator('[data-cell-index="0"] button');
      await expect(firstCard).toBeVisible({ timeout: 20000 });

      await firstCard.click();
      expect(await focusedCellIndex(page)).toBe('0');

      // Right: cell 0 -> skips the hole at (1,0) -> lands on cell 2.
      await page.keyboard.press('ArrowRight');
      expect(await focusedCellIndex(page)).toBe('2');

      // Right again: row edge -> focus stays put and the page must not scroll.
      await page.keyboard.press('ArrowRight');
      expect(await focusedCellIndex(page)).toBe('2');

      // Down from cell 2: nothing occupied below -> stays.
      await page.keyboard.press('ArrowDown');
      expect(await focusedCellIndex(page)).toBe('2');

      // Back to cell 0, then down: crosses rows to cell 3 (0,1).
      await page.locator('[data-cell-index="0"] button').focus();
      await page.keyboard.press('ArrowDown');
      expect(await focusedCellIndex(page)).toBe('3');

      // Left from (0,1): column edge -> stays.
      await page.keyboard.press('ArrowLeft');
      expect(await focusedCellIndex(page)).toBe('3');

      // Enter activates the focused card: the symbol joins the sentence strip.
      await page.locator('[data-cell-index="0"] button').focus();
      await page.keyboard.press('Enter');
      await expect(page.getByTestId('sentence-strip')).toContainText('Alpha');
    } finally {
      if (boardId != null) {
        await apiContext.delete(`/api/boards/${boardId}`, { headers });
      }
      await apiContext.dispose();
    }
  });
});
