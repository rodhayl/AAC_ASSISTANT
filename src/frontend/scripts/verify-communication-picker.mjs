/**
 * Visual + functional verification of the Communication tab's topic picker
 * and board-less topic conversation flow.
 *
 * Logs in as admin through the real form, opens Comunicación, verifies the
 * topic picker cards render on the board selection view, taps a topic card
 * and confirms the board-less conversation view appears (Smartbar vocabulary
 * + topic header, no grid), then taps back and confirms the session clears
 * and the board list returns.
 *
 * Run from src/frontend while the backend serves on 127.0.0.1:8086:
 *   node scripts/verify-communication-picker.mjs
 */
import { chromium } from '@playwright/test';

const BASE = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:8086';
const USERNAME = 'admin1';
const PASSWORD = 'Admin123';

const failures = [];
function check(name, ok, detail = '') {
  console.log(`[${ok ? 'PASS' : 'FAIL'}] ${name}${detail ? ` — ${detail}` : ''}`);
  if (!ok) failures.push(name);
}

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

// --- Real login through the UI ---
console.log('\n=== Login ===');
await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded', timeout: 30000 });
await page.waitForTimeout(800);
await page.locator('#username').fill(USERNAME);
await page.locator('#password').fill(PASSWORD);
await page.locator('button[type="submit"]').click();
try {
  await page.waitForURL((u) => !/\/login(?:[/?#]|$)/.test(u.pathname + u.search), {
    timeout: 20000,
  });
  check('Login succeeds', true);
} catch {
  check('Login succeeds', false, await page.locator('body').innerText().catch(() => 'no body'));
  await browser.close();
  process.exit(1);
}
await page.waitForTimeout(1200);

// --- Communication page: board selection view with topic picker ---
console.log('\n=== Communication board selection ===');
await page.goto(`${BASE}/communication`, { waitUntil: 'domcontentloaded', timeout: 30000 });
await page.waitForTimeout(3500);

let body = await page.locator('body').innerText();
check('Page title shown', /comunicación|communication/i.test(body));

const cardCount = await page.locator('[data-testid^="topic-card-"]').count();
check('Topic picker cards render on board selection', cardCount >= 9, `found ${cardCount}`);

await page.screenshot({ path: 'scripts/_comm_picker.png', fullPage: true });

// --- Tap a topic card -> boardless conversation view ---
const card = page
  .locator('[data-testid="topic-card-food"]')
  .or(page.locator('[data-testid="topic-card-general"]'))
  .first();
await card.click();

try {
  await page.waitForSelector('[data-testid="smartbar-suggestions"]', { timeout: 25000 });
  check('Board-less conversation view appears (Smartbar rendered)', true);
} catch {
  check('Board-less conversation view appears (Smartbar rendered)', false, 'no smartbar');
}

body = await page.locator('body').innerText();
check(
  'Topic hint shown in place of the grid',
  /estás conversando sobre|you.re talking about/i.test(body),
);

await page.waitForTimeout(8000); // let AI vocabulary + pictograms stream in
const suggestionCount = await page
  .locator('[data-testid="smartbar-suggestions"] [role="button"], [data-testid="smartbar-suggestions"] button')
  .count();
check('AI topic vocabulary suggestions appear', suggestionCount > 0, `found ${suggestionCount}`);

await page.screenshot({ path: 'scripts/_comm_boardless.png', fullPage: true });

// --- Back to the board list clears the session ---
const backBtn = page.locator('header button[aria-label="Volver a los tableros"], header button[aria-label="Back to boards"]');
await backBtn.click();
await page.waitForTimeout(1500);

body = await page.locator('body').innerText();
check('Returned to board selection view', /selecciona un tablero|select a board/i.test(body));
const cardCountAfter = await page.locator('[data-testid^="topic-card-"]').count();
check('Topic picker visible again after back', cardCountAfter >= 9, `found ${cardCountAfter}`);
const smartbarAfter = await page.locator('[data-testid="smartbar-suggestions"]').count();
check('Board-less session cleared (no Smartbar lingering)', smartbarAfter === 0, `found ${smartbarAfter}`);

await page.screenshot({ path: 'scripts/_comm_back.png', fullPage: true });

await browser.close();

console.log(`\n=== ${failures.length === 0 ? 'ALL CHECKS PASSED' : `${failures.length} FAILURES`} ===`);
if (failures.length > 0) process.exit(1);
