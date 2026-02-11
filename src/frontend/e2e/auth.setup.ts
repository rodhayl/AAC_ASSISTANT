import { test as setup, expect } from '@playwright/test';

const adminFile = 'playwright/.auth/admin.json';
const studentFile = 'playwright/.auth/student.json';

setup('authenticate as admin', async ({ page }) => {
  page.on('console', msg => console.log(`[Browser] ${msg.text()}`));
  await page.goto('/login');
  await page.evaluate(() => {
    localStorage.setItem('i18nextLng', 'en');
    localStorage.setItem('aac_assistant_locale', 'en');
  });
  await page.reload();
  
  await page.waitForLoadState('networkidle');
  await page.locator('#username').fill('admin1');
  await page.locator('#password').fill('Admin123');
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

    await page.locator('#username').fill('student1');
    await page.locator('#password').fill('Student123');
    await page.locator('button[type="submit"]').click();
    
    try {
      await page.waitForURL('/', { timeout: 10000 });
    } catch {
       console.log('Login failed, checking error...');
       const error = await page.locator('.bg-red-50').textContent().catch(() => null);
       console.log('Login error:', error);
       
       // Fallback if error detected OR if we are still on login page
       if (error || page.url().includes('/login')) {
          console.log('Login failed with default password, trying NewPass123!...');
          await page.locator('#password').fill('NewPass123!');
          await page.locator('button[type="submit"]').click();
          
          try {
              await page.waitForURL('/', { timeout: 10000 });
          } catch {
              console.log('Login failed with NewPass123! too. Registering fallback student...');
              await page.goto('/register');
              const fallbackUser = `student_fallback_${Date.now()}`;
              await page.locator('#username').fill(fallbackUser);
              await page.locator('#displayName').fill('Student Fallback');
              await page.locator('#password').fill('Student123');
              // Role student is default
              await page.locator('button[type="submit"]').click();
              
              // Registration successful -> redirects to / -> redirects to /login
              // So we must login manually
              await page.waitForTimeout(1000);
              await page.goto('/login');
              await page.locator('#username').fill(fallbackUser);
              await page.locator('#password').fill('Student123');
              await page.locator('button[type="submit"]').click();
              
              await page.waitForURL('/', { timeout: 15000 });
              console.log(`Registered and logged in as ${fallbackUser}`);
          }
       } else {
            throw new Error(`Student login failed: ${error || 'Unknown error'}`);
         }
      }
      
      // Wait for app to settle - use a reliable element on dashboard
      await page.waitForTimeout(2000);
  
      console.log(`Current URL: ${page.url()}`);
      // Check for dashboard element
      await expect(page.locator('h1, h2, .dashboard-content, .grid').first()).toBeVisible({ timeout: 20000 });
      
      // Ensure we are not still on login - wait for login button to disappear
      // Wait longer and ensure we are really on dashboard
      await expect(page.getByRole('button', { name: /login/i })).not.toBeVisible({ timeout: 15000 });
      await expect(page).not.toHaveURL(/login/);
      
      // Save state
      await page.context().storageState({ path: studentFile });
    });
