import { test, expect } from '@playwright/test';

// Directed multipage-walk regression: frontend walkPages and backend
// pagination were previously only tested separately. This spec exercises the
// whole chain against the production build: 620 students are seeded through
// the real HTTP API (more than one 500-row page), the admin Students view
// walks both pages via walkPages, and the visible roster must equal the
// seeded total with the final seeded student rendered.
//
// Cleanup relies on the throwaway database of scripts/e2e_live.sh (explicitly
// allowed: "borra lo sembrado o usa DB temporal desechable"); the dev database
// is never touched.

const SEEDED = 620;
const PAGE_SIZE = 500;

test.describe('Roster multipage walk (real backend)', () => {
  test.use({ storageState: 'playwright/.auth/admin.json' });

  test('admin roster walks every page and renders the seeded total', async ({ page, request }) => {
    test.setTimeout(300_000);

    const tokenRes = await request.post('/api/auth/token', {
      form: {
        username: process.env.E2E_ADMIN_USERNAME || 'admin1',
        password: process.env.E2E_ADMIN_PASSWORD || 'Admin123',
      },
    });
    expect(tokenRes.ok(), await tokenRes.text()).toBeTruthy();
    const auth = { Authorization: `Bearer ${(await tokenRes.json()).access_token}` };

    // Baseline roster size (walkPages contract: final short page terminates).
    const countRoster = async () => {
      let total = 0;
      let skip = 0;
      while (true) {
        const res = await request.get('/api/auth/users/student-summaries', {
          headers: auth,
          params: { limit: PAGE_SIZE, ...(skip > 0 ? { skip } : {}) },
        });
        expect(res.ok(), await res.text()).toBeTruthy();
        const rows: { id: number }[] = await res.json();
        total += rows.length;
        if (rows.length < PAGE_SIZE) return total;
        skip += rows.length;
      }
    };
    const before = await countRoster();

    // Seed 620 students through the production creation endpoint, in small
    // concurrent batches so the throwaway SQLite database never locks.
    for (let batch = 0; batch < SEEDED; batch += 10) {
      const responses = await Promise.all(
        Array.from({ length: Math.min(10, SEEDED - batch) }, (_, i) => {
          const n = batch + i;
          return request.post('/api/users/students', {
            headers: auth,
            data: {
              username: `walk_student_${String(n).padStart(3, '0')}`,
              display_name: `Walk Student ${n}`,
              user_type: 'student',
              password: 'WalkStudent123',
              confirm_password: 'WalkStudent123',
            },
          });
        }),
      );
      const bad = responses.find((r) => r.status() !== 200);
      if (bad) throw new Error(`seed failed: ${bad.status()} ${await bad.text()}`);
    }

    await page.goto('/students');
    await expect(page.locator('.animate-spin')).not.toBeVisible({ timeout: 30_000 });

    // The last seeded student proves the walk continued past page one.
    await expect(page.locator('tbody tr', { hasText: 'walk_student_619' })).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.locator('tbody tr')).toHaveCount(before + SEEDED);
  });
});
