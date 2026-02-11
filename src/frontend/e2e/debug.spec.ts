import { test } from '@playwright/test';

test.use({ storageState: 'playwright/.auth/admin.json' });

test('debug page content', async ({ page }) => {
  await page.goto('/');
  console.log('Root URL:', page.url());
  console.log('Root Title:', await page.title());
  console.log('Root Body:', await page.content());
  
  await page.goto('/boards');
  console.log('Boards URL:', page.url());
  console.log('Boards Body:', await page.content());
});
