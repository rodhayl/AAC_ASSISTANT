import { test, expect } from '@playwright/test';

// The export flow was already covered in admin.spec.ts; this spec closes the
// gap for the import/restore path: an exported server snapshot must be
// re-importable through the settings data tab without error.
test.describe('Data Management', () => {
  test.use({ storageState: 'playwright/.auth/admin.json' });

  test('round-trips an exported server snapshot through import', async ({ page }) => {
    await page.goto('/settings');

    // Obtain a valid import payload by exporting from the server first.
    const exportButton = page.getByRole('button', {
      name: /server export|exportar del servidor/i,
    });
    await expect(exportButton).toBeVisible();

    const downloadPromise = page.waitForEvent('download');
    await exportButton.click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/^aac-data-.+-server\.json$/);

    // Feed that snapshot back through the hidden import file input.
    const exportPath = await download.path();
    expect(exportPath).toBeTruthy();
    const importResponse = page.waitForResponse(
      (response) =>
        response.url().includes('/api/data/import') &&
        response.request().method() === 'POST',
      { timeout: 30000 },
    );
    await page.locator('#import-boards-file').setInputFiles(exportPath!);

    // The import round-trip must succeed and surface a localized success toast.
    expect((await importResponse).status()).toBe(200);
    await expect(
      page.getByText(/import completed successfully|importación completada/i),
    ).toBeVisible();
  });
});
