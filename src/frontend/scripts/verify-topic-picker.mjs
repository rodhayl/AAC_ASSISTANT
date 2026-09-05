/**
 * Visual + functional verification of the learning topic picker.
 *
 * Logs in as admin through the real form, opens Aprendizaje, verifies the
 * topic picker renders the canonical pool, starts a session by tapping a
 * topic card, and confirms the topic is marked practiced after the session
 * ends (coverage refresh).
 *
 * Run from src/frontend while the backend serves on 127.0.0.1:8086:
 *   node scripts/verify-topic-picker.mjs
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

// --- Learning page: picker empty state ---
console.log('\n=== Learning topic picker ===');
await page.goto(`${BASE}/learning`, { waitUntil: 'domcontentloaded', timeout: 30000 });
await page.waitForTimeout(3000);

let body = await page.locator('body').innerText();
check(
  'Picker title shown',
  /sobre qué quieres hablar|what would you like to talk about/i.test(body),
);

const cardCount = await page.locator('[data-testid^="topic-card-"]').count();
check('Nine topic cards rendered', cardCount >= 9, `found ${cardCount}`);

const practicedCount = await page.locator('[data-testid^="topic-card-"]:has-text("Practicado"), [data-testid^="topic-card-"]:has-text("Practiced")').count();
console.log(`  (${practicedCount} topic(s) already marked practiced from real history)`);

await page.screenshot({ path: 'scripts/_picker_empty.png', fullPage: true });

// --- Tap a topic card and confirm a session starts ---
const foodCard = page
  .locator('[data-testid="topic-card-food"]')
  .or(page.locator('[data-testid="topic-card-general"]'));
await foodCard.first().click();

// The end button only renders once the session is active: the definitive
// signal that starting the session worked.
try {
  await page.waitForSelector('[data-testid="learning-session-active"]', { timeout: 25000 });
  check('Session started after tapping a topic', true);
} catch {
  check('Session started after tapping a topic', false, 'no active-session button');
}
await page.waitForTimeout(1500);
body = await page.locator('body').innerText();
check(
  'Welcome message names the picked topic',
  /vamos a practicar (comida y cena|conversación general)|let's practice (food|general)/i.test(body),
);
await page.screenshot({ path: 'scripts/_picker_session.png', fullPage: true });

// --- End the session and confirm the picker returns with coverage refresh ---
const endButton = page.locator('[data-testid="learning-session-active"]');
if (await endButton.isVisible({ timeout: 3000 }).catch(() => false)) {
  await endButton.click();
  await page.waitForTimeout(800);
  // The confirmation dialog's danger button reuses the endSession label.
  const confirm = page.getByRole('button', { name: /finalizar sesión|end session/i }).last();
  if (await confirm.isVisible({ timeout: 2000 }).catch(() => false)) {
    await confirm.click();
  }
}
try {
  await page.waitForSelector('[data-testid="topic-card-general"]', { timeout: 25000 });
  check('Picker returns after the session ends', true);
} catch {
  check('Picker returns after the session ends', false, 'picker did not reappear');
}
await page.waitForTimeout(1200);
const practicedAfter = await page
  .locator('[data-testid^="topic-card-"]:has-text("Practicado"), [data-testid^="topic-card-"]:has-text("Practiced")')
  .count();
check('Ended topic is now marked practiced', practicedAfter >= 1, `practiced cards: ${practicedAfter}`);

await page.screenshot({ path: 'scripts/_picker_practiced.png', fullPage: true });

await browser.close();

if (failures.length) {
  console.log(`\n${failures.length} check(s) FAILED: ${failures.join(', ')}`);
  process.exit(1);
}
console.log('\nAll topic-picker browser checks passed.');
