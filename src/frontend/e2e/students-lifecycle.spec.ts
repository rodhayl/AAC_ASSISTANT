import { test, expect } from '@playwright/test';

// Targeted e2e for the account-scoped Students surface:
// - the roster renders through the shared walkPages helper (paginated
//   student-summaries endpoint, short final page terminates the walk);
// - the assignment modal completes an assign -> reopen -> already-assigned
//   cycle (the backend idempotency itself is pinned by
//   tests/test_board_assignment.py, tests/test_board_contracts.py, and
//   scripts/smoke_live.py — the unique constraint makes double POSTs safe);
// - the guardian profile modal creates and then updates a profile
//   (create/update are the 200 paths; the 409 race is DB-level and covered
//   by tests/test_guardian_profiles.py).

test.describe('Students lifecycle', () => {
  test.use({ storageState: 'playwright/.auth/admin.json' });

  test('loads the roster and drives the assign + guardian modals', async ({ page }) => {
    await page.goto('/students');
    await expect(page.locator('.animate-spin')).not.toBeVisible({ timeout: 20000 });

    // Roster loaded (walkPages terminated on the short final page).
    const row = page.locator('tbody tr', { hasText: 'student1' }).first();
    await expect(row).toBeVisible();

    // --- assignment modal: unassign the seeded board, assign it back, then
    // reopen the modal to see the backend's idempotent "already assigned" UX ---
    const boardName = /general communication|comunicación general/i;
    await row
      .getByRole('button', { name: /unassign (general communication|comunicación general)|desasignar (general communication|comunicación general)/i })
      .click();
    await expect(row.getByText(/no boards assigned|sin tableros asignados/i)).toBeVisible();

    await row.getByRole('button', { name: /assign board to student1|asignar tablero a student1/i }).click();
    const dialog = page.locator('div[role="dialog"]');
    await expect(dialog).toBeVisible();
    await dialog.getByRole('button', { name: boardName }).first().click();
    await expect(dialog).not.toBeVisible();
    await expect(row.getByText(boardName)).toBeVisible();

    // Reopen the modal: the board shows "Already assigned" (disabled),
    // proving the assignment is durable and double-assigns are prevented
    // at the UI layer (the API-level idempotency is pinned by
    // tests/test_board_contracts.py and scripts/smoke_live.py).
    await row.getByRole('button', { name: /assign board to student1|asignar tablero a student1/i }).click();
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText(/already assigned|ya asignado/i).first()).toBeVisible();
    await dialog.getByRole('button', { name: /close|cerrar/i }).click();
    await expect(dialog).not.toBeVisible();

    // --- guardian profile: create then update through the modal ---
    await row.getByRole('button', { name: /guardian profile|perfil del tutor/i }).click();
    const guardianDialog = page.locator('div[role="dialog"]');
    await expect(guardianDialog).toBeVisible();

    const saveButton = guardianDialog.getByRole('button', { name: /save|guardar/i });
    const ageInput = guardianDialog.locator('#age');
    await ageInput.fill('9');
    await saveButton.click();
    await expect(guardianDialog.getByText(/profile saved successfully|perfil guardado/i)).toBeVisible({
      timeout: 15000,
    });

    // The modal auto-closes after the success toast; reopen to update.
    await expect(guardianDialog).not.toBeVisible({ timeout: 5000 });
    await row.getByRole('button', { name: /guardian profile|perfil del tutor/i }).click();
    await expect(page.locator('div[role="dialog"]').locator('#age')).toHaveValue('9');
    await page.locator('div[role="dialog"]').locator('#age').fill('11');
    await page
      .locator('div[role="dialog"]')
      .getByRole('button', { name: /save|guardar/i })
      .click();
    await expect(
      page.locator('div[role="dialog"]').getByText(/profile saved successfully|perfil guardado/i),
    ).toBeVisible({ timeout: 15000 });
    await expect(page.locator('div[role="dialog"]')).not.toBeVisible({ timeout: 5000 });
  });
});
