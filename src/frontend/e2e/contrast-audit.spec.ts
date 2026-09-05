import { expect, test } from '@playwright/test';
import type { Page } from '@playwright/test';
import { auditContrast } from './contrast-audit';

/**
 * Full-route contrast audit: every page of the app is rendered in all four
 * appearance modes (light, dark, high-contrast, high-contrast-dark) and every
 * visible text element must meet WCAG AA (4.5:1). This is the executable
 * guarantee behind the "100% implemented dark mode / high contrast" claim.
 */
const modes = ['light', 'dark', 'high-contrast', 'high-contrast-dark'] as const;
type Mode = (typeof modes)[number];

const adminRoutes = [
  { name: 'dashboard', path: '/' },
  { name: 'communication', path: '/communication' },
  { name: 'boards', path: '/boards' },
  { name: 'board-editor', path: '/boards/1' },
  { name: 'learning', path: '/learning' },
  { name: 'symbol-hunt', path: '/symbol-hunt' },
  { name: 'achievements', path: '/achievements' },
  { name: 'students', path: '/students' },
  { name: 'symbols', path: '/symbols' },
  { name: 'teachers', path: '/teachers' },
  { name: 'admins', path: '/admins' },
  { name: 'settings', path: '/settings' },
  // /play/:id renders no UI of its own; it redirects to the communication
  // route, which is audited separately. Keep it listed so the router's full
  // surface is exercised.
  { name: 'play-redirect', path: '/play/1' },
];

// Role-limited surfaces: the student sees assigned boards, the student
// dashboard and the read-only AI panel — views the admin audit does not
// render with the same content.
const studentRoutes = [
  { name: 'student-dashboard', path: '/' },
  { name: 'student-communication', path: '/communication' },
  { name: 'student-learning', path: '/learning' },
  { name: 'student-symbol-hunt', path: '/symbol-hunt' },
  { name: 'student-achievements', path: '/achievements' },
  { name: 'student-settings', path: '/settings' },
];

const publicRoutes = [
  { name: 'login', path: '/login' },
  { name: 'register', path: '/register' },
  { name: 'setup', path: '/setup' },
  { name: 'not-found', path: '/this-route-does-not-exist' },
];

async function applyMode(page: Page, mode: Mode) {
  await page.evaluate((target: Mode) => {
    const root = document.documentElement;
    root.classList.remove('dark', 'high-contrast');
    if (target === 'dark' || target === 'high-contrast-dark') root.classList.add('dark');
    if (target === 'high-contrast' || target === 'high-contrast-dark') root.classList.add('high-contrast');
  }, mode);
}

test.describe('Contrast audit (WCAG AA)', () => {
  test.describe('admin routes', () => {
    test.use({ storageState: 'playwright/.auth/admin.json' });

    for (const route of adminRoutes) {
      for (const mode of modes) {
        test(`${route.name} in ${mode}`, async ({ page }) => {
          await page.goto(route.path, { waitUntil: 'domcontentloaded' });
          // Let the page data settle before measuring painted colors.
          await page.waitForTimeout(1200);
          await applyMode(page, mode);
          await page.waitForTimeout(200);

          await expect(page.locator('#root')).toBeVisible();
          await auditContrast(page, `${route.name}/${mode}`);
        });
      }
    }
  });

  test.describe('student routes', () => {
    test.use({ storageState: 'playwright/.auth/student.json' });

    for (const route of studentRoutes) {
      for (const mode of modes) {
        test(`${route.name} in ${mode}`, async ({ page }) => {
          await page.goto(route.path, { waitUntil: 'domcontentloaded' });
          await page.waitForTimeout(1200);
          await applyMode(page, mode);
          await page.waitForTimeout(200);

          await expect(page.locator('#root')).toBeVisible();
          await auditContrast(page, `${route.name}/${mode}`);
        });
      }
    }
  });

  test.describe('public routes', () => {
    // Public pages must not inherit a previous session's appearance.
    test.use({ storageState: { cookies: [], origins: [] } });

    for (const route of publicRoutes) {
      for (const mode of modes) {
        test(`${route.name} in ${mode}`, async ({ page }) => {
          await page.goto(route.path, { waitUntil: 'domcontentloaded' });
          await page.waitForTimeout(600);
          await applyMode(page, mode);
          await page.waitForTimeout(200);

          await expect(page.locator('#root')).toBeVisible();
          await auditContrast(page, `${route.name}/${mode}`);
        });
      }
    }
  });
});