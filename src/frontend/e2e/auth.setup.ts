import { test as setup, expect } from '@playwright/test';

const adminFile = 'playwright/.auth/admin.json';
const studentFile = 'playwright/.auth/student.json';
const adminUsername = process.env.E2E_ADMIN_USERNAME || 'admin1';
const adminPassword = process.env.E2E_ADMIN_PASSWORD || 'Admin123';
const studentUsername = process.env.E2E_STUDENT_USERNAME || 'student1';
const studentPassword = process.env.E2E_STUDENT_PASSWORD || 'Student123';

setup('authenticate as admin', async ({ page }) => {
  page.on('console', msg => console.log(`[Browser] ${msg.text()}`));
  await page.goto('/login');
  await page.evaluate(() => {
    localStorage.setItem('i18nextLng', 'en');
    localStorage.setItem('aac_assistant_locale', 'en');
  });
  await page.reload();
  
  await page.waitForLoadState('networkidle');
  await page.locator('#username').fill(adminUsername);
  await page.locator('#password').fill(adminPassword);
  await page.locator('button[type="submit"]').click();
  
  try {
    await page.waitForURL('/', { timeout: 5000 });
  } catch {
    console.log('Login failed, checking error...');
    const error = await page.locator('.bg-red-50').textContent().catch(() => null);
    console.log('Login error:', error);
    
    if (error?.includes('Incorrect') || error?.includes('credentials') || error?.includes('not found')) {
       console.log('User not found? Trying to register admin...');
       // Registration usually doesn't allow creating admin role directly via UI unless backend allows it or secret code?
       // Only admin can create users?
       // Or Register page allows role selection? Register page allows Student/Teacher.
       // Admin must be seeded.
       // If admin login fails, we are stuck.
       throw new Error(`Admin login failed: ${error}`);
    }
    throw new Error(`Admin login failed: ${error || 'Unknown error'}`);
   }
 
   console.log(`Current URL: ${page.url()}`);
   await expect(page.getByRole('link', { name: /boards/i }).or(page.getByRole('link', { name: /tableros/i }))).toBeVisible();
   await page.context().storageState({ path: adminFile });
 });
 
 setup('authenticate as student', async ({ page }) => {
     page.on('console', msg => console.log(`[Student Setup Console] ${msg.text()}`));
     
     // Ensure clean slate
     await page.context().clearCookies();
     await page.goto('/login');
    await page.evaluate(() => localStorage.clear());
    await page.reload();
    
    // Ensure we are not mistakenly detecting login page as dashboard
    // We expect to be on login page initially in a fresh context
    
    await expect(page.locator('button[type="submit"]')).toBeVisible();

    await page.locator('#username').fill(studentUsername);
    await page.locator('#password').fill(studentPassword);
    await page.locator('button[type="submit"]').click();
    
    try {
      await page.waitForURL('/', { timeout: 10000 });
    } catch {
       console.log('Login failed, checking error...');
       const error = await page.locator('.bg-red-50').textContent().catch(() => null);
       console.log('Login error:', error);
       
       // A test setup must fail clearly when its seeded fixture is unavailable.
       // Creating a random user here masks broken database seeding and makes
       // subsequent authenticated tests nondeterministic.
       throw new Error(
         `Student login failed for seeded fixture ${studentUsername}: ${error || 'Unknown error'}`,
       );
      }
      
      // Save state only after the authenticated shell is actually rendered.
      // This avoids persisting a token that redirects immediately back to login.
      await expect(page).toHaveURL(/\/$/, { timeout: 20000 });
      await expect(
        page.getByRole('button', { name: /sign out|cerrar/i }),
      ).toBeVisible({ timeout: 20000 });
      await expect(page).not.toHaveURL(/\/login(?:[/?#]|$)/);

      console.log(`Current URL: ${page.url()}`);
      await page.context().storageState({ path: studentFile });
    });
