import { test, expect } from '@playwright/test';

// Directed teacher-scoped guardian-profile flow (PROMPT_5 F2). The happy path
// was previously covered only admin-scoped (students-lifecycle.spec.ts); this
// spec proves the visible flow works for a teacher account too, including
// persistence after reopening and after a full page reload.
//
// The teacher's students are created through the real API in the spec setup
// and the throwaway database of scripts/e2e_live.sh is discarded afterwards.

test.describe('Teacher guardian profile (visible flow)', () => {
  test.use({ storageState: 'playwright/.auth/teacher.json' });

  test('create, edit, reopen and reload a student guardian profile', async ({ page, request }) => {
    test.setTimeout(180_000);

    // --- API setup: one teacher-created student ---
    const tokenRes = await request.post('/api/auth/token', {
      form: {
        username: process.env.E2E_TEACHER_USERNAME || 'teacher1',
        password: process.env.E2E_TEACHER_PASSWORD || 'Teacher123',
      },
    });
    expect(tokenRes.ok(), await tokenRes.text()).toBeTruthy();
    const auth = { Authorization: `Bearer ${(await tokenRes.json()).access_token}` };

    const meRes = await request.get('/api/auth/me', { headers: auth });
    expect(meRes.ok(), await meRes.text()).toBeTruthy();
    const teacherId = (await meRes.json()).id as number;

    const createRes = await request.post('/api/users/students', {
      headers: auth,
      data: {
        username: 'guardian_flow_student',
        display_name: 'Guardian Flow Student',
        user_type: 'student',
        password: 'GuardianFlow123',
        confirm_password: 'GuardianFlow123',
        created_by_teacher_id: teacherId,
      },
    });
    expect(
      createRes.ok(),
      `student create failed: ${createRes.status()} ${await createRes.text()}`,
    ).toBeTruthy();

    // --- UI: open the Students view as teacher1 ---
    await page.goto('/students');
    await expect(page.locator('.animate-spin')).not.toBeVisible({ timeout: 20_000 });
    const row = page.locator('tbody tr', { hasText: 'guardian_flow_student' }).first();
    await expect(row).toBeVisible();

    // --- create the profile ---
    await row.getByRole('button', { name: /guardian profile|perfil del tutor/i }).click();
    const dialog = page.locator('div[role="dialog"]');
    await expect(dialog).toBeVisible();
    await dialog.locator('#age').fill('10');
    await dialog.getByRole('button', { name: /save|guardar/i }).click();
    await expect(dialog.getByText(/profile saved successfully|perfil guardado/i)).toBeVisible({
      timeout: 15_000,
    });
    await expect(dialog).not.toBeVisible({ timeout: 5_000 });

    // --- reopen: the edit is visible ---
    await row.getByRole('button', { name: /guardian profile|perfil del tutor/i }).click();
    const reopenDialog = page.locator('div[role="dialog"]');
    await expect(reopenDialog.locator('#age')).toHaveValue('10');

    // --- edit a field and save ---
    await reopenDialog.locator('#age').fill('12');
    await reopenDialog.getByRole('button', { name: /save|guardar/i }).click();
    await expect(reopenDialog.getByText(/profile saved successfully|perfil guardado/i)).toBeVisible({
      timeout: 15_000,
    });
    await expect(reopenDialog).not.toBeVisible({ timeout: 5_000 });

    // --- full reload: persistence survives a fresh page load ---
    await page.reload();
    await expect(page.locator('.animate-spin')).not.toBeVisible({ timeout: 20_000 });
    const rowAfter = page.locator('tbody tr', { hasText: 'guardian_flow_student' }).first();
    await expect(rowAfter).toBeVisible();
    await rowAfter.getByRole('button', { name: /guardian profile|perfil del tutor/i }).click();
    await expect(page.locator('div[role="dialog"]').locator('#age')).toHaveValue('12');
  });
});
