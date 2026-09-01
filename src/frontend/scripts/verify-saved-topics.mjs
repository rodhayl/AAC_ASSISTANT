/**
 * Visual + functional verification of server-side saved topics.
 *
 * Logs in as teacher1, saves a topic through the sidebar UI, confirms it
 * persists via the API, then logs in as student1 (roster-linked to teacher1)
 * and confirms the student sees the teacher's topic on the Learning picker —
 * proving topics follow the student to any device.
 *
 * Run from src/frontend while the backend serves on 127.0.0.1:8086:
 *   node scripts/verify-saved-topics.mjs
 */
import { chromium } from '@playwright/test';

const BASE = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:8086';

const failures = [];
function check(name, ok, detail = '') {
  console.log(`[${ok ? 'PASS' : 'FAIL'}] ${name}${detail ? ` — ${detail}` : ''}`);
  if (!ok) failures.push(name);
}

async function login(page, username, password) {
  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForTimeout(800);
  await page.locator('#username').fill(username);
  await page.locator('#password').fill(password);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL((u) => !/\/login(?:[/?#]|$)/.test(u.pathname + u.search), {
    timeout: 20000,
  });
  await page.waitForTimeout(1200);
}

const browser = await chromium.launch();

// ---------------------------------------------------------------------------
// Setup: ensure student1 is on teacher1's roster (via admin API)
// ---------------------------------------------------------------------------
console.log('\n=== Setup roster link ===');
{
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await login(page, 'admin1', 'Admin123');
  const linked = await page.evaluate(async () => {
    const auth = JSON.parse(localStorage.getItem('auth-storage') || '{}');
    const token = auth?.state?.token;
    const headers = { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) };
    // teacher1 id=3, student1 id=2 (demo seed).
    const res = await fetch('/api/users/assign-student', {
      method: 'POST',
      headers,
      body: JSON.stringify({ student_id: 2, teacher_id: 3 }),
    });
    if (res.ok || res.status === 409) return true;
    return false;
  });
  check('student1 linked to teacher1 roster', linked);
  await page.close();
}

// ---------------------------------------------------------------------------
// Teacher: save a topic via the sidebar UI
// ---------------------------------------------------------------------------
console.log('\n=== Teacher saves a topic ===');
{
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await login(page, 'teacher1', 'Teacher123');

  await page.goto(`${BASE}/learning`, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForTimeout(2500);

  // Open the sidebar if collapsed, then add a custom topic.
  const sidebarOpen = await page.locator('#comp-topic-select').count();
  if (sidebarOpen === 0) {
    await page.locator('button[title*="Expandir"], button[title*="Expand"]').first().click();
    await page.waitForTimeout(600);
  }

  const marker = `Verificación ${Date.now()}`;
  await page.selectOption('#comp-topic-select', 'custom');
  await page.locator('input[placeholder*="Tema"], input[placeholder*="topic"]').first().fill(marker);
  await page.locator('button:has-text("Guardar tema"), button:has-text("Save topic")').first().click();
  await page.waitForTimeout(1500);

  let body = await page.locator('body').innerText();
  check('Teacher sees the saved topic in the sidebar', body.includes(marker));

  // Verify it persisted via the API (server-side, not localStorage).
  const apiTopics = await page.evaluate(async (m) => {
    const auth = JSON.parse(localStorage.getItem('auth-storage') || '{}');
    const token = auth?.state?.token;
    const res = await fetch('/api/learning/topics/saved', {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    const data = await res.json();
    return Array.isArray(data) ? data.map((t) => t.topic) : [];
  }, marker);
  check('Topic persisted server-side (API)', apiTopics.includes(marker), `API: ${JSON.stringify(apiTopics)}`);

  await page.screenshot({ path: 'scripts/_saved_teacher.png', fullPage: true });
  await page.close();
}

// ---------------------------------------------------------------------------
// Student: sees the teacher's topic on the Learning picker
// ---------------------------------------------------------------------------
console.log('\n=== Student sees teacher topic ===');
{
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await login(page, 'student1', 'Student123');

  await page.goto(`${BASE}/learning`, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForTimeout(3500);

  const body = await page.locator('body').innerText();
  const topics = await page.evaluate(async () => {
    const auth = JSON.parse(localStorage.getItem('auth-storage') || '{}');
    const token = auth?.state?.token;
    const res = await fetch('/api/learning/topics/saved', {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    return res.ok ? res.json() : [];
  });
  if (!Array.isArray(topics)) {
    check('Student API returns teacher topics', false, `non-array: ${JSON.stringify(topics)}`);
  } else {
    check(
      'Student API returns teacher topics',
      topics.some((t) => String(t.topic).startsWith('Verificación')),
      `student API: ${JSON.stringify(topics.map((t) => t.topic))}`,
    );
  }
  check('Student picker mentions a saved teacher topic', /Verificación/.test(body));

  await page.screenshot({ path: 'scripts/_saved_student.png', fullPage: true });
  await page.close();
}

// ---------------------------------------------------------------------------
// Cleanup: delete the verification topics via the teacher API
// ---------------------------------------------------------------------------
console.log('\n=== Cleanup ===');
{
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await login(page, 'teacher1', 'Teacher123');
  const deleted = await page.evaluate(async () => {
    const auth = JSON.parse(localStorage.getItem('auth-storage') || '{}');
    const token = auth?.state?.token;
    const res = await fetch('/api/learning/topics/saved', {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    const topics = await res.json();
    let removed = 0;
    for (const t of topics) {
      if (String(t.topic).startsWith('Verificación')) {
        const del = await fetch(`/api/learning/topics/saved/${t.id}`, {
          method: 'DELETE',
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (del.ok || del.status === 204) removed += 1;
      }
    }
    return removed;
  });
  check('Verification topics cleaned up', deleted > 0, `removed ${deleted}`);
  await page.close();
}

await browser.close();

console.log(`\n=== ${failures.length === 0 ? 'ALL CHECKS PASSED' : `${failures.length} FAILURES`} ===`);
if (failures.length > 0) process.exit(1);
