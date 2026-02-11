import { chromium } from '@playwright/test';

(async () => {
  const baseUrl = process.env.AAC_FRONTEND_URL ?? 'http://localhost:5176';
  const username = process.env.AAC_RESET_USERNAME ?? 'student1';
  const currentPassword = process.env.AAC_CURRENT_PASSWORD;
  const newPassword = process.env.AAC_NEW_PASSWORD;

  if (!currentPassword || !newPassword) {
    console.error('Set AAC_CURRENT_PASSWORD and AAC_NEW_PASSWORD before running this script.');
    process.exit(2);
  }

  const browser = await chromium.launch();
  const page = await browser.newPage();

  try {
    console.log('Navigating to login page...');
    await page.goto(`${baseUrl}/login`);

    console.log('Signing in with provided credentials...');
    await page.getByLabel(/username/i).fill(username);
    await page.getByLabel(/password/i).fill(currentPassword);
    await page.getByRole('button', { name: /login/i }).click();
    await page.waitForURL('/');

    console.log('Navigating to settings...');
    await page.goto(`${baseUrl}/settings`);

    console.log('Opening change password modal...');
    const changeBtn = page.getByRole('button', {
      name: /change password|cambiar contrase.a/i,
    });
    await changeBtn.click();

    console.log('Submitting password change...');
    await page.getByPlaceholder(/current|actual/i).fill(currentPassword);
    await page.getByPlaceholder(/new|nueva/i).first().fill(newPassword);
    await page.getByPlaceholder(/confirm|confirmar/i).fill(newPassword);

    const saveBtn = page
      .locator('button')
      .filter({ hasText: /save|guardar/i })
      .last();
    await saveBtn.click();

    console.log('Password update complete.');
    await page.waitForTimeout(2000);
  } catch (err) {
    console.error('Password reset failed:', err);
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
})();
