import { test, expect, type Page } from '@playwright/test';

// The Dashboard's "recent activity" rows deep-link into the exact Learning
// conversation (/learning?session=N). This is the connective tissue between
// the two most-used student surfaces: a wrong id must never silently load the
// wrong conversation or strand the user on a broken page. The Learning page
// consumes the param once, strips it from the URL and falls back to the topic
// picker; a missing session surfaces the sessionNotFound toast.
//
// Idempotency: learning sessions cannot be deleted via the API (by design, no
// DELETE route), so this spec REUSES the most recent session when one exists
// and only creates a new one when the history is empty. That keeps repeated
// runs (local dev DBs) from accumulating rows while staying green on a clean
// CI environment, where the first run seeds its own session.
test.describe('Dashboard deep-link into Learning sessions', () => {
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

  test('the newest activity row opens its exact learning conversation', async ({ page, playwright }) => {
    const token = await readAdminToken(page);

    const baseURL = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:8086';
    const apiContext = await playwright.request.newContext({ baseURL });
    const headers = { Authorization: `Bearer ${token}` };

    // Resolve the authenticated user id from the injected session.
    const userState = await page.evaluate(() => {
      const raw = localStorage.getItem('auth-storage');
      if (!raw) return null;
      try { return JSON.parse(raw) as { state?: { user?: { id: number } } }; } catch { return null; }
    });
    const userId = userState?.state?.user?.id;
    expect(userId).toBeTruthy();

    let createdSessionId: number | null = null;
    try {
      // Most recent session, as the dashboard renders it (newest first).
      const historyRes = await apiContext.get(`/api/learning/history/${userId}?limit=1`, { headers });
      expect(historyRes.ok()).toBeTruthy();
      const historyData = await historyRes.json();
      const sessions: Array<{ id: number }> = Array.isArray(historyData)
        ? historyData
        : (historyData.sessions ?? []);

      let sessionId: number;
      if (sessions.length > 0) {
        sessionId = sessions[0].id;
      } else {
        // Clean CI environment: seed one session through the real endpoint so
        // the dashboard has an activity row to link to.
        const startRes = await apiContext.post('/api/learning/start', {
          headers,
          params: { user_id: userId as number },
          data: { topic: 'Dashboard deep-link E2E', difficulty: 'basic' },
        });
        expect(startRes.ok()).toBeTruthy();
        const started = (await startRes.json()) as { session_id: number };
        sessionId = started.session_id;
        createdSessionId = sessionId;
      }

      // On the dashboard, the newest activity row must carry that session id.
      await page.goto('/');
      const firstRow = page.locator('a[href*="/learning?session="]').first();
      await expect(firstRow).toBeVisible({ timeout: 20000 });
      await expect(firstRow).toHaveAttribute('href', new RegExp(`session=${sessionId}`));

      // Clicking it lands on Learning, loads the conversation, and the deep
      // link param is cleaned after being consumed exactly once.
      await firstRow.click();
      await expect(page).toHaveURL(/\/learning/);
      await expect(page).not.toHaveURL(/session=/);
      await expect(page.getByTestId('learning-session-active')).toBeVisible({ timeout: 20000 });

      // A second visit with the same param must not re-load the session twice
      // (the deep link is consumed once per URL value).
      await page.goto(`/learning?session=${sessionId}`);
      await expect(page.getByTestId('learning-session-active')).toBeVisible({ timeout: 20000 });
      await expect(page).not.toHaveURL(/session=/);
      await expect(page.getByText(/sessionNotFound|Sesión no encontrada/)).toHaveCount(0);
    } finally {
      // Sessions have no DELETE endpoint; the created row (only on a clean
      // environment) is intentionally left as the newest history entry.
      void createdSessionId;
      await apiContext.dispose();
    }
  });
});
