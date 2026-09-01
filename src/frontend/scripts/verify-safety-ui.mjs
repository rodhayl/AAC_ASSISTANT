/**
 * Visual + functional verification of the content-safety UI in a real browser.
 *
 * Logs in through the actual login form, then walks the admin settings tab,
 * the students/guardian page and the learning page.
 *
 * Run from src/frontend while the backend serves on 127.0.0.1:8086:
 *   node scripts/verify-safety-ui.mjs
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
await page.screenshot({ path: 'scripts/_safety_login.png', fullPage: true });
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

// --- Admin settings: content-safety tab ---
console.log('\n=== Admin settings page ===');
await page.goto(`${BASE}/settings`, { waitUntil: 'domcontentloaded', timeout: 30000 });
await page.waitForTimeout(2500);
await page.screenshot({ path: 'scripts/_safety_settings.png', fullPage: true });
let body = await page.locator('body').innerText();
check('Settings page loads (authenticated)', !/inicia sesi|log in|sign in/i.test(body));

const tabLocators = [
  page.getByRole('tab', { name: /content safety/i }),
  page.getByRole('tab', { name: /seguridad de contenido/i }),
  page.getByRole('tab', { name: /^seguridad/i }),
  page.getByRole('link', { name: /content safety/i }),
  page.getByRole('link', { name: /seguridad de contenido/i }),
];
let opened = false;
for (const el of tabLocators) {
  try {
    if (await el.first().isVisible({ timeout: 1500 })) {
      await el.first().click({ timeout: 3000 });
      await page.waitForTimeout(1200);
      opened = true;
      break;
    }
  } catch {
    /* keep trying */
  }
}
await page.screenshot({ path: 'scripts/_safety_settings_tab.png', fullPage: true });
body = await page.locator('body').innerText();
check(
  'Content Safety tab opened',
  opened || /forbidden topics|temas prohibidos|filter level|nivel de filtro/i.test(body),
  body.slice(0, 250).replace(/\n+/g, ' | '),
);
check(
  'Content-safety form fields present',
  /forbidden topics|temas prohibidos|trigger words|palabras disparadoras|filter level|nivel de filtro|locked fields|campos bloqueados/i.test(body),
);

// --- Students page: guardian modal safety section ---
console.log('\n=== Students page ===');
await page.goto(`${BASE}/students`, { waitUntil: 'domcontentloaded', timeout: 30000 });
await page.waitForTimeout(2500);
await page.screenshot({ path: 'scripts/_safety_students.png', fullPage: true });
body = await page.locator('body').innerText();
check('Students page loads', /students|estudiantes|alumnos/i.test(body));

// --- Learning page ---
console.log('\n=== Learning page ===');
await page.goto(`${BASE}/learning`, { waitUntil: 'domcontentloaded', timeout: 30000 });
await page.waitForTimeout(2500);
await page.screenshot({ path: 'scripts/_safety_learning.png', fullPage: true });
body = await page.locator('body').innerText();
check('Learning page loads', /learning|aprendizaje|estudiar|study/i.test(body));

// --- Communication page ---
console.log('\n=== Communication page ===');
await page.goto(`${BASE}/communication`, { waitUntil: 'domcontentloaded', timeout: 30000 });
await page.waitForTimeout(2500);
await page.screenshot({ path: 'scripts/_safety_communication.png', fullPage: true });
body = await page.locator('body').innerText();
check('Communication page loads', /communication|comunicación|board|tablero/i.test(body));

await browser.close();

if (failures.length) {
  console.log(`\n${failures.length} check(s) FAILED: ${failures.join(', ')}`);
  process.exit(1);
}
console.log('\nAll browser checks passed.');
