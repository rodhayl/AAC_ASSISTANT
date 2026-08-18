import { expect, test, type Page } from '@playwright/test';

/**
 * Automated portion of the supervised-pilot gate.
 *
 * These tests deliberately cover only behavior that a browser can verify
 * reliably. Windows installation, physical audio output, NVDA/Narrator, and
 * hardware-assisted input remain in docs/windows-assistive-validation.md.
 *
 * The suite expects the normal production-like Playwright environment: a
 * freshly built frontend served by the backend and the seeded accounts created
 * by e2e/auth.setup.ts. It does not reset or mutate the shared fixture users.
 */

type Role = 'admin' | 'teacher' | 'student';

const roleState: Record<Role, string> = {
  admin: 'playwright/.auth/admin.json',
  teacher: 'playwright/.auth/teacher.json',
  student: 'playwright/.auth/student.json',
};

function authHeaders(token: string) {
  return { Authorization: `Bearer ${token}` };
}

async function readStoredToken(page: Page): Promise<string> {
  const token = await page.evaluate(() => {
    const raw = localStorage.getItem('auth-storage');
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { state?: { token?: string } };
    return parsed.state?.token ?? null;
  });
  expect(token, 'the authenticated browser must persist an access token').toBeTruthy();
  return token!;
}

async function openAssignedCommunicationBoard(page: Page) {
  await page.goto('/communication');
  const board = page.getByRole('button', { name: /Comunicación General/i }).first();
  await expect(board).toBeVisible({ timeout: 20000 });
  await board.click();
  await expect(page.getByTestId('sentence-strip')).toBeVisible();
  await expect(
    page.locator('.grid').getByRole('button', { name: /Add .* to sentence/i }).first(),
  ).toBeVisible({ timeout: 20000 });
}

/**
 * Read the symbol labels rendered in the AAC grid. The app localizes symbol
 * labels to the student's UI language (e.g. Spanish), so tests must not
 * hardcode English labels. Returns the first `count` labels in grid order.
 */
async function readGridSymbolLabels(page: Page, count: number): Promise<string[]> {
  const buttons = page.locator('.grid').getByRole('button', { name: /Add .* to sentence/i });
  const labels: string[] = [];
  const total = Math.min(count, await buttons.count());
  for (let i = 0; i < total; i++) {
    const aria = await buttons.nth(i).getAttribute('aria-label');
    const match = aria?.match(/^Add (.+) to sentence$/);
    if (match) labels.push(match[1]);
  }
  expect(labels.length, 'the AAC grid must render add-to-sentence buttons').toBeGreaterThan(0);
  return labels;
}

test.describe('Pilot gate: initialized setup and unauthenticated boundaries', () => {
  test('initialized setup cannot be reused and setup UI redirects safely', async ({ page }) => {
    const status = await page.request.get('/api/auth/setup-status');
    expect(status.ok()).toBe(true);
    const setupStatus = (await status.json()) as { setup_required: boolean; has_admin: boolean };
    expect(setupStatus.setup_required).toBe(false);
    expect(setupStatus.has_admin).toBe(true);

    const secondSetup = await page.request.post('/api/auth/setup', {
      data: {
        username: `blocked_setup_${Date.now()}`,
        display_name: 'Blocked Setup User',
        password: 'StrongTest123!',
        confirm_password: 'StrongTest123!',
      },
    });
    expect(secondSetup.status()).toBe(403);

    await page.goto('/setup');
    await expect(page).toHaveURL(/\/login(?:[/?#]|$)/);
  });

  test('unauthenticated users cannot read representative protected APIs', async ({ page }) => {
    await page.context().clearCookies();
    await page.goto('/login');
    await page.evaluate(() => localStorage.clear());

    for (const endpoint of ['/api/users/me', '/api/boards', '/api/learning-modes/']) {
      const response = await page.request.get(endpoint);
      expect(
        [401, 403],
        `${endpoint} must deny unauthenticated access`,
      ).toContain(response.status());
    }
  });
});

for (const role of Object.keys(roleState) as Role[]) {
  test.describe(`Pilot gate: ${role} session`, () => {
    test.use({ storageState: roleState[role] });

    test('refreshes and opens the primary workflow', async ({ page }) => {
      await page.goto('/');
      await expect(page.getByRole('navigation')).toBeVisible();
      await page.reload();
      await expect(page).not.toHaveURL(/\/login(?:[/?#]|$)/);

      const primaryPath = role === 'admin' ? '/students' : role === 'teacher' ? '/students' : '/communication';
      await page.goto(primaryPath);
      await expect(page.getByRole('navigation')).toBeVisible();
      await expect(page).not.toHaveURL(/\/login(?:[/?#]|$)/);
    });
  });
}

test.describe('Pilot gate: logout revokes backend access', () => {
  test('a token captured before UI logout is rejected afterward', async ({ page }) => {
    test.setTimeout(60000);
    const username = `pilot_logout_${Date.now()}`;
    const password = 'PilotLogout123!';
    const registration = await page.request.post('/api/auth/register', {
      data: {
        username,
        display_name: 'Pilot Logout Test',
        password,
        user_type: 'student',
      },
    });
    expect(registration.ok()).toBe(true);

    await page.goto('/login');
    await page.getByLabel(/username|usuario/i).fill(username);
    await page.getByLabel(/password|contraseña/i).fill(password);
    await page.locator('button[type="submit"]').click();
    await expect(page).toHaveURL(/\/$/);

    const token = await readStoredToken(page);
    const beforeLogout = await page.request.get('/api/users/me', { headers: authHeaders(token) });
    expect(beforeLogout.status()).toBe(200);

    await page.getByRole('button', { name: /sign out|cerrar sesión/i }).click();
    await expect(page).toHaveURL(/\/login(?:[/?#]|$)/);

    const afterLogout = await page.request.get('/api/users/me', { headers: authHeaders(token) });
    expect(afterLogout.status()).toBe(401);
  });
});

test.describe('Pilot gate: Student AAC communication', () => {
  test.use({ storageState: roleState.student });

  test('builds, edits, clears, and rebuilds a phrase', async ({ page }) => {
    await openAssignedCommunicationBoard(page);
    const grid = page.locator('.grid');
    const preview = page.getByTestId('sentence-preview');
    const backspace = page.getByTestId('sentence-backspace');
    const clear = page.getByTestId('sentence-clear');

    await expect(page.getByTestId('sentence-empty')).toBeVisible();
    await expect(backspace).toBeDisabled();
    await expect(clear).toBeDisabled();

    const labels = await readGridSymbolLabels(page, 3);
    for (const label of labels) {
      await grid.getByRole('button', { name: `Add ${label} to sentence` }).click();
    }
    await expect(preview).toHaveText(labels.join(' '));

    await backspace.click();
    await expect(preview).toHaveText(labels.slice(0, -1).join(' '));

    await clear.click();
    await expect(page.getByTestId('sentence-empty')).toBeVisible();

    // Keyboard activation is included in the critical communication path.
    await grid.getByRole('button', { name: `Add ${labels[0]} to sentence` }).press('Enter');
    await expect(preview).toHaveText(labels[0]);
  });

  test('keeps core AAC interaction available while the browser is offline', async ({ page }) => {
    await openAssignedCommunicationBoard(page);
    const [label] = await readGridSymbolLabels(page, 1);
    const target = page.locator('.grid').getByRole('button', { name: `Add ${label} to sentence` });
    const preview = page.getByTestId('sentence-preview');

    try {
      await page.context().setOffline(true);
      await page.evaluate(() => window.dispatchEvent(new Event('offline')));
      await target.click();
      await expect(preview).toHaveText(label);
    } finally {
      await page.context().setOffline(false);
      await page.evaluate(() => window.dispatchEvent(new Event('online')));
    }
  });
});

test.describe('Pilot gate: Student UI boundary checks', () => {
  test.use({ storageState: roleState.student });

  test('cannot access Admin or Teacher UI routes', async ({ page }) => {
    for (const path of ['/admins', '/teachers', '/symbols']) {
      await page.goto(path);
      await expect(page).toHaveURL(/\/$/);
    }
  });
});

test.describe('Pilot gate: Teacher UI boundary checks', () => {
  test.use({ storageState: roleState.teacher });

  test('cannot access Admin UI routes', async ({ page }) => {
    for (const path of ['/admins', '/teachers']) {
      await page.goto(path);
      await expect(page).toHaveURL(/\/$/);
    }
  });
});

test.describe('Pilot gate: direct role boundary checks', () => {
  test('Student and Teacher receive server-side denial for representative privileged APIs', async ({ browser }) => {
    const cases: Array<{ role: 'student' | 'teacher'; payload: Record<string, string> }> = [
      { role: 'student', payload: { username: `blocked_student_${Date.now()}`, display_name: 'Blocked Student', password: 'Blocked123!', confirm_password: 'Blocked123!', user_type: 'student' } },
      { role: 'teacher', payload: { username: `blocked_teacher_${Date.now()}`, display_name: 'Blocked Teacher', password: 'Blocked123!', confirm_password: 'Blocked123!', user_type: 'teacher' } },
    ];

    for (const item of cases) {
      const context = await browser.newContext({ storageState: roleState[item.role] });
      const page = await context.newPage();
      try {
        await page.goto('/');
        const token = await readStoredToken(page);
        const response = await context.request.post('/api/auth/admin/create-user', {
          data: item.payload,
          headers: authHeaders(token),
        });
        expect(response.status()).toBe(403);
      } finally {
        await context.close();
      }
    }
  });
});
