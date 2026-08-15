import { expect, test } from '@playwright/test';

test.describe('Teacher student provisioning', () => {
  test.use({ storageState: 'playwright/.auth/teacher.json' });

  test('creates and immediately lists a student assigned to the teacher', async ({ page }) => {
    const username = `e2e_teacher_student_${Date.now()}`;

    await page.goto('/students');
    await expect(page.getByRole('button', { name: /create student/i })).toBeVisible();
    await page.getByRole('button', { name: /create student/i }).click();

    const dialog = page.getByRole('dialog', { name: /create new student/i });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByLabel(/username/i)).toBeVisible();
    await expect(dialog.getByLabel(/display name/i)).toBeVisible();
    const inputs = dialog.locator('input');
    await inputs.nth(0).fill(username);
    await inputs.nth(1).fill('E2E Teacher Student');
    await inputs.nth(3).fill('TeacherCreated123');
    const createResponsePromise = page.waitForResponse(
      (response) =>
        response.url().includes('/api/users/students') &&
        response.request().method() === 'POST',
    );
    await dialog.getByRole('button', { name: /create student/i }).click();
    const createResponse = await createResponsePromise;
    expect(createResponse.status()).toBe(200);

    await expect(dialog).not.toBeVisible({ timeout: 30000 });
    await expect(page.getByText(username)).toBeVisible({ timeout: 30000 });
  });
});
