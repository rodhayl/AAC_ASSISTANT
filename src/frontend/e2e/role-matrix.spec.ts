import { expect, test } from '@playwright/test';

type Role = 'student' | 'teacher' | 'admin';

type RoleCase = {
  role: Role;
  stateFile: string;
  visibleLinks: RegExp[];
  allowedPaths: string[];
  forbiddenPaths: string[];
};

const roleCases: RoleCase[] = [
  {
    role: 'student',
    stateFile: 'playwright/.auth/student.json',
    visibleLinks: [
      /dashboard|panel/i,
      /communication|comunicación/i,
      /boards|tableros/i,
      /learning|aprendizaje/i,
      /symbol hunt|caza de símbolos/i,
      /achievements|logros/i,
      /settings|ajustes/i,
    ],
    allowedPaths: ['/communication', '/boards', '/learning', '/symbol-hunt', '/achievements', '/settings'],
    forbiddenPaths: ['/symbols', '/students', '/teachers', '/admins'],
  },
  {
    role: 'teacher',
    stateFile: 'playwright/.auth/teacher.json',
    visibleLinks: [
      /dashboard|panel/i,
      /communication|comunicación/i,
      /boards|tableros/i,
      /symbols|símbolos/i,
      /learning|aprendizaje/i,
      /symbol hunt|caza de símbolos/i,
      /achievements|logros/i,
      /students|estudiantes/i,
      /settings|ajustes/i,
    ],
    allowedPaths: ['/communication', '/boards', '/learning', '/symbol-hunt', '/achievements', '/symbols', '/students', '/settings'],
    forbiddenPaths: ['/teachers', '/admins'],
  },
  {
    role: 'admin',
    stateFile: 'playwright/.auth/admin.json',
    visibleLinks: [
      /dashboard|panel/i,
      /communication|comunicación/i,
      /boards|tableros/i,
      /symbols|símbolos/i,
      /learning|aprendizaje/i,
      /symbol hunt|caza de símbolos/i,
      /achievements|logros/i,
      /students|estudiantes/i,
      /teachers|profesores/i,
      /admins|administradores/i,
      /settings|ajustes/i,
    ],
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

      for (const linkName of roleCase.visibleLinks) {
        await expect(navigation.getByRole('link', { name: linkName })).toBeVisible();
      }

      const forbiddenLabels: Record<string, RegExp> = {
        '/symbols': /symbols|símbolos/i,
        '/students': /students|estudiantes/i,
        '/teachers': /teachers|profesores/i,
        '/admins': /admins|administradores/i,
      };
      for (const path of roleCase.forbiddenPaths) {
        await expect(
          navigation.getByRole('link', { name: forbiddenLabels[path] }),
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
