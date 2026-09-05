/**
 * Visual + functional verification of per-student safety configuration at
 * account creation.
 *
 * Logs in as admin, opens Estudiantes -> create student, expands the safety
 * section, fills age/filter level/forbidden topics/feature gate, creates the
 * student, and then reads the created guardian profile back through the API
 * to confirm the constraints landed. Also verifies a plain create (no safety)
 * leaves no guardian profile.
 *
 * Run from src/frontend while the backend serves on 127.0.0.1:8086:
 *   node scripts/verify-student-create-safety.mjs
 */
import { chromium } from '@playwright/test';

const BASE = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:8086';
const USERNAME = 'admin1';
const PASSWORD = 'Admin123';
const suffix = Date.now().toString().slice(-6);

const failures = [];
function check(name, ok, detail = '') {
  console.log(`[${ok ? 'PASS' : 'FAIL'}] ${name}${detail ? ` — ${detail}` : ''}`);
  if (!ok) failures.push(name);
}

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

// --- Login through the real form ---
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

// --- Create a student WITH safety configuration ---
console.log('\n=== Create student with safety ===');
await page.goto(`${BASE}/students`, { waitUntil: 'domcontentloaded', timeout: 30000 });
await page.waitForTimeout(2500);
await page.getByRole('button', { name: /crear|create/i }).first().click();
await page.waitForTimeout(800);

await page.locator('#create-student-username').fill(`safe_${suffix}`);
await page.locator('#create-student-display-name').fill(`Safe ${suffix}`);
await page.locator('#create-student-password').fill('StudentPass123');
await page.locator('#create-student-confirm-password').fill('StudentPass123');

const safetyToggle = page.getByText(/configuración de seguridad|safety configuration/i).first();
await safetyToggle.click();
await page.waitForTimeout(400);
await page.screenshot({ path: 'scripts/_create_safety_section.png', fullPage: true });

await page.locator('#create-student-age').fill('7');
await page.locator('#create-student-filter-level').selectOption('strict');
await page.locator('#create-student-forbidden-topics').fill('astronomía\nconflictos armados');
await page.locator('#create-student-trigger-words').fill('guerra');
await page.screenshot({ path: 'scripts/_create_safety_filled.png', fullPage: true });

await page.getByRole('button', { name: /crear estudiante|create student/i }).first().click({ force: true });
await page.waitForTimeout(2500);
let body = await page.locator('body').innerText();
check('Student created (modal closed)', !/crear nuevo estudiante|create new student/i.test(body));

// --- Verify the guardian profile through the API ---
console.log('\n=== Verify persisted safety ===');
const token = await page.evaluate(() => {
  const raw = localStorage.getItem('auth-storage');
  if (!raw) return '';
  try {
    const parsed = JSON.parse(raw);
    return parsed?.state?.token || parsed?.token || '';
  } catch {
    return '';
  }
});
const headers = { Authorization: `Bearer ${token}` };

const studentsRes = await page.request.get(`${BASE}/api/auth/users/student-summaries?limit=500`, { headers });
const summaries = await studentsRes.json();
const created = summaries.find((s) => s.username === `safe_${suffix}`);
check('Created student listed', Boolean(created), created ? '' : 'not in summaries');

if (created) {
  const profileRes = await page.request.get(`${BASE}/api/guardian-profiles/students/${created.id}`, { headers });
  check('Guardian profile read back (200)', profileRes.status() === 200, `status ${profileRes.status()}`);
  if (profileRes.status() === 200) {
    const profile = await profileRes.json();
    const constraints = profile.safety_constraints || {};
    check('Age persisted', profile.age === 7, `age=${profile.age}`);
    check('Filter level persisted', constraints.content_filter_level === 'strict');
    check(
      'Forbidden topics persisted',
      (constraints.forbidden_topics || []).includes('astronomía'),
      JSON.stringify(constraints.forbidden_topics),
    );
    check('Trigger words persisted', (constraints.trigger_words || []).includes('guerra'));
  }

  // Cleanup: remove the test student.
  await page.request.delete(`${BASE}/api/auth/users/${created.id}`, { headers });
}

// --- Plain create leaves no profile ---
console.log('\n=== Plain create (no safety) ===');
await page.goto(`${BASE}/students`, { waitUntil: 'domcontentloaded', timeout: 30000 });
await page.waitForTimeout(2000);
await page.getByRole('button', { name: /crear|create/i }).first().click();
await page.waitForTimeout(800);
await page.locator('#create-student-username').fill(`plain_${suffix}`);
await page.locator('#create-student-display-name').fill(`Plain ${suffix}`);
await page.locator('#create-student-password').fill('StudentPass123');
await page.locator('#create-student-confirm-password').fill('StudentPass123');
await page.getByRole('button', { name: /crear estudiante|create student/i }).first().click({ force: true });
await page.waitForTimeout(2500);

const plainRes = await page.request.get(`${BASE}/api/auth/users/student-summaries?limit=500`, { headers });
const plainSummaries = await plainRes.json();
const plainStudent = plainSummaries.find((s) => s.username === `plain_${suffix}`);
check('Plain student listed', Boolean(plainStudent));
if (plainStudent) {
  const profileRes = await page.request.get(`${BASE}/api/guardian-profiles/students/${plainStudent.id}`, { headers });
  check('Plain student has NO guardian profile (404)', profileRes.status() === 404, `status ${profileRes.status()}`);
  await page.request.delete(`${BASE}/api/auth/users/${plainStudent.id}`, { headers });
}

await browser.close();

if (failures.length) {
  console.log(`\n${failures.length} check(s) FAILED: ${failures.join(', ')}`);
  process.exit(1);
}
console.log('\nAll student-create-safety browser checks passed.');
