import { expect, test } from '@playwright/test';
import { spawn, type ChildProcess } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

// First-run onboarding is a critical path: a fresh install has no
// administrator and must be bootstrapped through /setup. The main E2E server is
// already seeded with admin1, so this spec spawns a throwaway second server
// with a fresh database and no bootstrap admin, drives the setup form, and
// verifies the new administrator lands in the app and that setup then locks.
const FIRST_RUN_PORT = 8099;
const FIRST_RUN_URL = `http://127.0.0.1:${FIRST_RUN_PORT}`;

let server: ChildProcess | null = null;

function projectRoot(): string {
  // Playwright runs from src/frontend; the repo root is two levels up.
  return path.resolve(process.cwd(), '..', '..');
}

async function waitForSetupRequired(timeoutMs = 60_000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  let lastError = '';
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${FIRST_RUN_URL}/api/auth/setup-status`);
      if (res.ok) {
        const body = (await res.json()) as { setup_required?: boolean };
        if (body.setup_required === true) return;
        lastError = `setup_required is ${body.setup_required}`;
      } else {
        lastError = `HTTP ${res.status}`;
      }
    } catch (err) {
      lastError = err instanceof Error ? err.message : String(err);
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`First-run server did not become ready: ${lastError}`);
}

test.describe('First-run setup', () => {
  test.beforeAll(async () => {
    const root = projectRoot();
    const dataDir = path.join(root, 'tmp', 'e2e-firstrun');
    fs.rmSync(dataDir, { recursive: true, force: true });

    server = spawn(
      'uv',
      [
        'run',
        'python',
        '-m',
        'scripts.run_server',
        '--host',
        '127.0.0.1',
        '--port',
        String(FIRST_RUN_PORT),
      ],
      {
        cwd: root,
        detached: true,
        stdio: 'ignore',
        env: {
          ...process.env,
          ENVIRONMENT: 'development',
          // Valid non-placeholder JWT secret for an isolated instance.
          JWT_SECRET_KEY: 'firstrun-e2e-secret-0123456789abcdef0123456789abcdef',
          DATA_DIR: dataDir,
          DATABASE_NAME: 'firstrun.sqlite3',
          LOGS_DIR: path.join(dataDir, 'logs'),
          UPLOADS_DIR: path.join(dataDir, 'uploads'),
          // No auto-created admin and no sample users: /setup must be required.
          AAC_BOOTSTRAP_ADMIN_ON_FIRST_RUN: 'false',
          AAC_SEED_SAMPLE_DATA: 'false',
          AAC_ASSISTANT_NO_BROWSER: '1',
        },
      },
    );

    await waitForSetupRequired();
  });

  test.afterAll(async () => {
    if (server?.pid) {
      try {
        process.kill(-server.pid, 'SIGTERM');
      } catch {
        // The process group may already be gone.
      }
    }
    server = null;
  });

  test('completes onboarding and locks setup afterward', async ({ browser }) => {
    const context = await browser.newContext();
    const page = await context.newPage();
    try {
      await page.goto(`${FIRST_RUN_URL}/setup`);
      await expect(page.locator('#setup-username')).toBeVisible({ timeout: 20000 });

      const submit = page.locator('button[type="submit"]');

      // A too-short password keeps the submit button disabled client-side.
      await page.locator('#setup-password').fill('short');
      await page.locator('#setup-confirm-password').fill('short');
      await expect(submit).toBeDisabled();

      // A strong password completes setup and lands on the dashboard.
      const password = 'SecureAdmin123!';
      await page.locator('#setup-password').fill(password);
      await page.locator('#setup-confirm-password').fill(password);
      await expect(submit).toBeEnabled();
      await submit.click();

      await expect(page).toHaveURL(new RegExp(`${FIRST_RUN_URL}/$`), { timeout: 20000 });
      await expect(page.getByRole('navigation')).toBeVisible();

      // Setup is now locked: revisiting /setup redirects to login.
      await page.goto(`${FIRST_RUN_URL}/setup`);
      await expect(page).toHaveURL(/\/login(?:[/?#]|$)/, { timeout: 20000 });
    } finally {
      await context.close();
    }
  });
});
