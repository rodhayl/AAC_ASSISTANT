import { expect, test } from '@playwright/test';

type Role = 'student' | 'teacher' | 'admin';

type RoleCase = {
  role: Role;
  stateFile: string;
  allowedPaths: string[];
  forbiddenPaths: string[];
};

const roleCases: RoleCase[] = [
  {
    role: 'student',
    stateFile: 'playwright/.auth/student.json',
    allowedPaths: ['/communication', '/boards', '/learning', '/symbol-hunt', '/achievements', '/settings'],
    forbiddenPaths: ['/symbols', '/students', '/teachers', '/admins'],
  },
  {
    role: 'teacher',
    stateFile: 'playwright/.auth/teacher.json',
    allowedPaths: ['/communication', '/boards', '/learning', '/symbol-hunt', '/achievements', '/symbols', '/students', '/settings'],
    forbiddenPaths: ['/teachers', '/admins'],
  },
  {
    role: 'admin',
    stateFile: 'playwright/.auth/admin.json',
    allowedPaths: ['/communication', '/boards', '/learning', '/symbol-hunt', '/achievements', '/symbols', '/students', '/teachers', '/admins', '/settings'],
    forbiddenPaths: [],
  },
];

for (const roleCase of roleCases) {
  test.describe(`GUI role matrix: ${roleCase.role}`, () => {
    test.use({ storageState: roleCase.stateFile });

    test('loads every role-authorized route', async ({ page }) => {
      for (const path of roleCase.allowedPaths) {
        await page.goto(path);
        await expect(page).toHaveURL(new RegExp(`${path.replace('/', '\\/')}(?:[/?#]|$)`));
        await expect(page.getByRole('navigation')).toBeVisible();
      }
    });

    test('shows exactly the role-appropriate navigation', async ({ page }) => {
      await page.goto('/');
      const navigation = page.getByRole('navigation');
      await expect(navigation).toBeVisible();

      // The dashboard link points to the root route.
      const visibleHrefs = ['/', ...roleCase.allowedPaths];
      for (const href of visibleHrefs) {
        await expect(
          navigation.locator(`a[href="${href}"]`),
        ).toBeVisible();
      }

      for (const path of roleCase.forbiddenPaths) {
        // Match by href so language variants and similarly-named links
        // (e.g. "symbols" vs "symbol hunt") do not collide.
        await expect(
          navigation.locator(`a[href="${path}"]`),
        ).toHaveCount(0);
      }
    });

    for (const path of roleCase.forbiddenPaths) {
      test(`redirects from forbidden route ${path}`, async ({ page }) => {
        await page.goto(path);
        await expect(page).toHaveURL(/\/$/);
        await expect(page.getByRole('navigation')).toBeVisible();
      });
    }
  });
}
