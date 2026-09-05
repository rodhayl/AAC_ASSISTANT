import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  globalSetup: './e2e/global-setup.ts',
  // groq-verify.spec.ts is a manual browser-verification spec that needs a
  // real Groq API key (E2E_GROQ_API_KEY) and the local admin account; keep it
  // out of the standard CI suite. Run it with playwright.verify.config.ts.
  testIgnore: /groq-verify\.spec\.ts/,
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: 'list',
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:8086',
    trace: 'on-first-retry',
    video: 'retain-on-failure',
    screenshot: 'only-on-failure',
    locale: 'en-US',
    timezoneId: 'UTC',
    actionTimeout: 15000,
    navigationTimeout: 30000,
  },
  timeout: 120000,
  expect: {
    timeout: 15000,
  },
  projects: [
    { name: 'setup', testMatch: /.*\.setup\.ts/ },
    {
      name: 'chromium',
      use: { 
        ...devices['Desktop Chrome'],
        storageState: 'playwright/.auth/student.json',
      },
      dependencies: ['setup'],
    },
  ],
});
