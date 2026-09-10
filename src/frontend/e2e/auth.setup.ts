import { test as setup, expect, type APIRequestContext, type Page } from '@playwright/test';

type Credentials = {
  username: string;
  password: string;
  stateFile: string;
  role: 'student' | 'teacher';
};

const credentials: Record<string, Credentials> = {
  admin: {
    username: process.env.E2E_ADMIN_USERNAME || 'admin1',
    password: process.env.E2E_ADMIN_PASSWORD || 'Admin123',
    stateFile: 'playwright/.auth/admin.json',
    role: 'student',
  },
  student: {
    username: process.env.E2E_STUDENT_USERNAME || 'student1',
    password: process.env.E2E_STUDENT_PASSWORD || 'Student123',
    stateFile: 'playwright/.auth/student.json',
    role: 'student',
  },
  teacher: {
    username: process.env.E2E_TEACHER_USERNAME || 'teacher1',
    password: process.env.E2E_TEACHER_PASSWORD || 'Teacher123',
    stateFile: 'playwright/.auth/teacher.json',
    role: 'teacher',
  },
};

// The production CI gate runs with AAC_SEED_SAMPLE_DATA=false, so demo users
// do not exist. When E2E_PROVISION_VIA_API=1, sign in as the bootstrap admin
// first and create the student/teacher accounts through the real API before
// their own setup steps run. This keeps the production gate free of seeded
// demo data while preserving deterministic E2E credentials (CI-only literals).
async function provisionViaAdminApi(request: APIRequestContext): Promise<void> {
  if (process.env.E2E_PROVISION_VIA_API !== '1') return;

  const admin = credentials.admin;
  const login = await request.post('/api/auth/token', {
    form: {
      username: admin.username,
      password: admin.password,
    },
  });
  if (!login.ok()) {
    throw new Error(`E2E provisioning: admin login failed (${login.status()})`);
  }
  const { access_token: adminToken } = await login.json();
  const authHeaders = { Authorization: `Bearer ${adminToken}` };

  for (const account of Object.values(credentials)) {
    if (account === admin) continue;
    const create = await request.post('/api/auth/admin/create-user', {
      headers: authHeaders,
      data: {
        username: account.username,
        password: account.password,
        confirm_password: account.password,
        user_type: account.role,
        display_name: account.role === 'teacher' ? 'E2E Teacher' : 'E2E Student',
      },
    });
    // 400/409 for an existing account is fine: provisioning is idempotent.
    if (!create.ok() && create.status() !== 400 && create.status() !== 409) {
      const body = await create.text();
      throw new Error(
        `E2E provisioning: failed to create ${account.username}: ${create.status()} ${body}`,
      );
    }
    console.log(`Provisioned ${account.username} via admin API`);
  }
}

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
    if (account === credentials.admin) {
      // The admin signs in first, so provisioning runs before the other
      // setup projects attempt their own logins.
      await provisionViaAdminApi(page.request);
    }
    await authenticate(page, role, account);
  });
}
