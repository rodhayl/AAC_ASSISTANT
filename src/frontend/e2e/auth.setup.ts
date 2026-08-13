import { test as setup, expect, type Page } from '@playwright/test';

type Credentials = {
  username: string;
  password: string;
  stateFile: string;
};

const credentials: Record<string, Credentials> = {
  admin: {
    username: process.env.E2E_ADMIN_USERNAME || 'admin1',
    password: process.env.E2E_ADMIN_PASSWORD || 'Admin123',
    stateFile: 'playwright/.auth/admin.json',
  },
  student: {
    username: process.env.E2E_STUDENT_USERNAME || 'student1',
    password: process.env.E2E_STUDENT_PASSWORD || 'Student123',
    stateFile: 'playwright/.auth/student.json',
  },
  teacher: {
    username: process.env.E2E_TEACHER_USERNAME || 'teacher1',
    password: process.env.E2E_TEACHER_PASSWORD || 'Teacher123',
    stateFile: 'playwright/.auth/teacher.json',
  },
};

async function authenticate(page: Page, role: string, account: Credentials) {
  await page.context().clearCookies();
  await page.goto('/login');
  await page.evaluate(() => {
    localStorage.clear();
    localStorage.setItem('i18nextLng', 'en');
    localStorage.setItem('aac_assistant_locale', 'en');
  });
  await page.reload();

  await expect(page.locator('button[type="submit"]')).toBeVisible();
  await page.locator('#username').fill(account.username);
  await page.locator('#password').fill(account.password);
  await page.locator('button[type="submit"]').click();

  await expect(page).toHaveURL('/', { timeout: 20000 });
  await expect(
    page.getByRole('button', { name: /sign out|cerrar/i }),
  ).toBeVisible({ timeout: 20000 });
  await expect(page).not.toHaveURL(/\/login(?:[/?#]|$)/);
  await page.context().storageState({ path: account.stateFile });
  console.log(`Authenticated ${role} as ${account.username}`);
}

for (const [role, account] of Object.entries(credentials)) {
  setup(`authenticate as ${role}`, async ({ page }) => {
    await authenticate(page, role, account);
  });
}
