import { expect, test, type Page } from '@playwright/test';

const routes = [
  { name: 'dashboard', path: '/' },
  { name: 'communication', path: '/communication' },
  { name: 'learning', path: '/learning' },
  { name: 'settings', path: '/settings' },
];

const viewports = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'mobile', width: 390, height: 844 },
];

const modes = ['light', 'dark', 'high-contrast', 'high-contrast-dark'] as const;
type Mode = (typeof modes)[number];

async function applyMode(page: Page, mode: Mode) {
  await page.evaluate((targetMode: Mode) => {
    const root = document.documentElement;
    root.classList.remove('dark', 'high-contrast');

    if (targetMode === 'dark') {
      root.classList.add('dark');
      return;
    }

    if (targetMode === 'high-contrast') {
      root.classList.add('high-contrast');
      return;
    }

    if (targetMode === 'high-contrast-dark') {
      root.classList.add('dark', 'high-contrast');
    }
  }, mode);
}

async function ensureAuthenticated(page: Page) {
  if (!page.url().includes('/login')) {
    return;
  }

  await page.locator('#username').fill('student1');
  await page.locator('#password').fill('Student123');
  await page.locator('button[type="submit"]').click();
  await page.waitForURL('/', { timeout: 15000 });
}

for (const viewport of viewports) {
  test.describe(`visual smoke ${viewport.name}`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height } });

    for (const route of routes) {
      for (const mode of modes) {
        test(`renders ${route.name} in ${mode}`, async ({ page }, testInfo) => {
          await page.goto(route.path, { waitUntil: 'domcontentloaded' });
          await ensureAuthenticated(page);
          await page.waitForTimeout(800);
          if (route.path !== '/') {
            await page.goto(route.path, { waitUntil: 'domcontentloaded' });
            await page.waitForTimeout(800);
          }
          await applyMode(page, mode);
          await page.waitForTimeout(300);

          await expect(page.locator('#root')).toBeVisible();
          const screenshot = await page.screenshot({ fullPage: true });
          await testInfo.attach(`${viewport.name}-${route.name}-${mode}.png`, {
            body: screenshot,
            contentType: 'image/png',
          });
        });
      }
    }
  });
}
