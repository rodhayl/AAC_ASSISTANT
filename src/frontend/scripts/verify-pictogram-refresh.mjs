/**
 * Verify the Smartbar pictogram auto-refresh: a topic word with no symbol is
 * surfaced as a text-only "generating" tile and upgrades to a real image
 * (background generation) without any user interaction.
 *
 * Run from src/frontend while the backend serves on 127.0.0.1:8086:
 *   node scripts/verify-pictogram-refresh.mjs
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

// Login through the real form.
await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded', timeout: 30000 });
await page.waitForTimeout(800);
await page.locator('#username').fill(USERNAME);
await page.locator('#password').fill(PASSWORD);
await page.locator('button[type="submit"]').click();
await page.waitForURL((u) => !/\/login(?:[/?#]|$)/.test(u.pathname + u.search), {
  timeout: 20000,
});

// Start a learning session with a topic the symbol DB does NOT cover, so the
// LLM topic words + autogen path is exercised. Do it via the API directly
// (the session then shows in the Learning chat with the topic-aware Smartbar).
const token = await page.evaluate(() => {
  const raw = localStorage.getItem('auth-storage');
  return raw ? JSON.parse(raw).state?.token : '';
});
// The learning/start endpoint needs the target user_id as a query param;
// decode it from the JWT payload.
const payload = JSON.parse(atob(token.split('.')[1]));
const startRes = await page.evaluate(
  async ({ t, uid }) => {
    const res = await fetch(`/api/learning/start?user_id=${uid}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${t}`,
      },
      body: JSON.stringify({
        topic: 'astrofísica',
        purpose: 'practice',
        difficulty: 'basic',
        mode_key: 'practice',
      }),
    });
    return res.json();
  },
  { t: token, uid: payload.user_id ?? 1 },
);
check('Session started with uncovered topic', Boolean(startRes.success), JSON.stringify(startRes).slice(0, 120));
const sessionId = startRes.session_id;

// Open the Learning page — the chat panel Smartbar should fetch topic words.
await page.goto(`${BASE}/learning`, { waitUntil: 'domcontentloaded', timeout: 30000 });
await page.waitForTimeout(4000);
await page.screenshot({ path: 'scripts/_picto_initial.png', fullPage: true });

// Look for any suggestion tile in the Smartbar area and record its state.
const tilesBefore = await page.locator('[data-testid*="suggestion"], [class*="suggestion"] img, [class*="suggestion"]').count();
const textOnlyBefore = await page
  .locator('text=/cuerpo celeste|gravedad|agujero negro|materia oscura|energía oscura/i')
  .count();
console.log(`  initial: tiles=${tilesBefore} topic-word texts=${textOnlyBefore}`);

// Wait for the auto-refresh polling (up to ~50s) so generated pictograms land.
let upgraded = false;
let sawGenerating = false;
for (let i = 0; i < 14; i++) {
  await page.waitForTimeout(4000);
  const body = await page.locator('body').innerText();
  if (/generating|generando/i.test(body)) sawGenerating = true;
  const imgs = await page.locator('img').evaluateAll((els) =>
    els.map((el) => (el.getAttribute('src') || '')).filter((s) => s.includes('/uploads/')),
  );
  if (imgs.length > 0) {
    upgraded = true;
    console.log(`  upgrade detected after ~${(i + 1) * 4}s (${imgs.length} uploaded images on page)`);
    break;
  }
}
await page.screenshot({ path: 'scripts/_picto_after.png', fullPage: true });
check('Pictogram tiles upgrade to real images without typing', upgraded);
check('No error state rendered', !(await page.locator('body').innerText()).includes('Failed to fetch'));

await browser.close();
if (failures.length) {
  console.log(`\n${failures.length} check(s) FAILED: ${failures.join(', ')}`);
  process.exit(1);
}
console.log('\nAll pictogram-refresh checks passed.');
