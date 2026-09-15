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
    // Target the fields by id: index-based fills silently pointed at the wrong
    // input once the form gained its confirm-password field, and the client
    // validation then blocked the request entirely.
    await dialog.locator('#create-student-username').fill(username);
    await dialog.locator('#create-student-display-name').fill('E2E Teacher Student');
    await dialog.locator('#create-student-password').fill('TeacherCreated123');
    await dialog.locator('#create-student-confirm-password').fill('TeacherCreated123');
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
