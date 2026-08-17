import { expect, test, type Page } from '@playwright/test';

// Realtime board collaboration (WebSocket) had backend + unit coverage but no
// GUI e2e. This spec opens the same board in two browser contexts (admin owner
// and student collaborator) and verifies that a drag-and-drop move performed in
// one editor propagates to the other over the /api/collab WebSocket without a
// reload. No page.route mocks and no swallowed assertions.
test.describe('Realtime board collaboration', () => {
  test.use({ storageState: 'playwright/.auth/admin.json' });

  test('propagates a remote symbol move to a second collaborator', async ({ browser, page, playwright }) => {
    test.setTimeout(120000);

    // 1. Read the admin's persisted token so the API setup can authenticate.
    await page.goto('/');
    const token = await page.evaluate(() => {
      const raw = localStorage.getItem('auth-storage');
      if (!raw) return null;
      try { return (JSON.parse(raw) as { state?: { token?: string } }).state?.token ?? null; } catch { return null; }
    });
    expect(token).toBeTruthy();
    const adminId = JSON.parse(Buffer.from(token!.split('.')[1], 'base64').toString()).user_id as number;

    const baseURL = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:8086';
    const apiContext = await playwright.request.newContext({ baseURL });
    const headers = { Authorization: `Bearer ${token}` };

    // Grab any seeded symbol id from the local library.
    const symbolsRes = await apiContext.get('/api/boards/symbols', { headers, params: { limit: 1 } });
    expect(symbolsRes.ok()).toBeTruthy();
    const symbols = (await symbolsRes.json()) as Array<{ id: number }>;
    expect(symbols.length).toBeGreaterThan(0);
    const symbolId = symbols[0].id;

    // Create a fresh public board with a single symbol at (0,0) so the
    // target cell (1,1) is empty and the move is unambiguous. The default 4x5
    // grid keeps cells small enough that both cells stay within the viewport
    // during the drag (a 2x2 grid would overflow and push (1,1) off-screen).
    const createRes = await apiContext.post('/api/boards/', {
      headers,
      params: { user_id: adminId },
      data: {
        name: `Collab ${Date.now()}`,
        grid_rows: 4,
        grid_cols: 5,
        is_public: true,
        symbols: [{ symbol_id: symbolId, position_x: 0, position_y: 0 }],
      },
    });
    expect(createRes.ok()).toBeTruthy();
    const board = (await createRes.json()) as { id: number };
    const boardId = board.id;
    await apiContext.dispose();

    // 2. Open the board editor in both contexts and wait for each editor to
    // establish its /api/collab WebSocket connection.
    const adminWsPromise = page.waitForEvent('websocket', (ws) => ws.url().includes(`/collab/boards/${boardId}`));
    await page.goto(`/boards/${boardId}`);
    await expect(page.locator('.grid').locator('div.group')).toHaveCount(1, { timeout: 20000 });
    const adminWs = await adminWsPromise;

    const studentContext = await browser.newContext({ storageState: 'playwright/.auth/student.json' });
    const studentPage = await studentContext.newPage();
    try {
      const studentWsPromise = studentPage.waitForEvent('websocket', (ws) => ws.url().includes(`/collab/boards/${boardId}`));
      await studentPage.goto(`/boards/${boardId}`);
      await expect(studentPage.locator('.grid').locator('div.group')).toHaveCount(1, { timeout: 20000 });
      const studentWs = await studentWsPromise;

      // Both sockets are now created; give the localhost handshake a moment to
      // complete so the student is registered in the room before the broadcast.
      await studentPage.waitForTimeout(500);

      // 3. The admin drags the symbol from cell (0,0) onto cell (1,1).
      const source = page.locator('.grid').locator('div.group').first();
      const target = page.getByRole('gridcell', { name: 'Cell 1, 1' });
      const sourceBox = await source.boundingBox();
      const targetBox = await target.boundingBox();
      if (!sourceBox || !targetBox) throw new Error('missing bounding boxes for drag');
      await page.mouse.move(sourceBox.x + sourceBox.width / 2, sourceBox.y + sourceBox.height / 2);
      await page.mouse.down();
      await page.mouse.move(targetBox.x + targetBox.width / 2, targetBox.y + targetBox.height / 2, { steps: 20 });
      await page.mouse.up();

      // 4. The admin's own editor reflects the move locally.
      await expect(target.locator('div.group')).toBeVisible({ timeout: 10000 });
      await expect(page.getByRole('gridcell', { name: 'Cell 0, 0' }).locator('div.group')).toHaveCount(0, { timeout: 10000 });

      // 5. The student's editor receives the move over the WebSocket and
      // repositions the symbol without a reload.
      const studentTarget = studentPage.getByRole('gridcell', { name: 'Cell 1, 1' });
      await expect(studentTarget.locator('div.group')).toBeVisible({ timeout: 15000 });
      await expect(
        studentPage.getByRole('gridcell', { name: 'Cell 0, 0' }).locator('div.group'),
      ).toHaveCount(0, { timeout: 10000 });

      // Sanity: both collaboration sockets remained open throughout.
      expect(adminWs.isClosed()).toBe(false);
      expect(studentWs.isClosed()).toBe(false);
    } finally {
      await studentContext.close();
    }
  });
});
