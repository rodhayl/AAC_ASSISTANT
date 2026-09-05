import { defineConfig, devices } from '@playwright/test';

/**
 * Minimal config for standalone verification specs (e.g. groq-verify.spec.ts)
 * that handle their own login. Unlike playwright.config.ts this has no
 * `setup` project dependency, so it does not require the student/teacher demo
 * accounts to exist.
 */
export default defineConfig({
  testDir: './e2e',
  testMatch: /groq-verify\.spec\.ts/,
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
  timeout: 240000,
  expect: {
    timeout: 20000,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});