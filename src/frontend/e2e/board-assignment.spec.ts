import { test, expect } from '@playwright/test';

// Board assignment (teacher/admin assigning a board to a student) had backend
// coverage but no GUI e2e. This spec exercises the full cycle in the Students
// view: unassign the seeded board, then re-assign it through the modal.
test.describe('Board Assignment', () => {
  test.use({ storageState: 'playwright/.auth/admin.json' });

  test('unassigns and re-assigns a board for a student', async ({ page }) => {
    await page.goto('/students');

    await expect(page.locator('.animate-spin')).not.toBeVisible({ timeout: 20000 });
    const row = page.locator('tbody tr', { hasText: 'student1' }).first();
    await expect(row).toBeVisible();

    // The seeded "Comunicación General" board is assigned by default.
    const boardName = /general communication|comunicación general/i;
    await expect(row.getByText(boardName)).toBeVisible();

    // Unassign it via the chip's close button.
    await row
      .getByRole('button', { name: /unassign (general communication|comunicación general)|desasignar (general communication|comunicación general)/i })
      .click();
    await expect(row.getByText(/no boards assigned|sin tableros asignados/i)).toBeVisible();

    // Re-assign it through the modal.
    await row
      .getByRole('button', { name: /assign board to student1|asignar tablero a student1/i })
      .click();
    const dialog = page.locator('div[role="dialog"]');
    await expect(dialog).toBeVisible();
    await dialog.getByRole('button', { name: boardName }).click();

    // The board chip reappears and the modal closes.
    await expect(dialog).not.toBeVisible();
    await expect(row.getByText(boardName)).toBeVisible();
  });
});
