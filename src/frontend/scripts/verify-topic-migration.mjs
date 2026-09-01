/**
 * End-to-end verification of the one-time saved-topic migration: legacy
 * localStorage topics are pushed to the backend on first load for a
 * teacher/admin, then the local copy is cleared — and reloading does not
 * duplicate them.
 *
 * Flow:
 *   1. Log in as teacher1 (demo seed), then seed a legacy
 *      `learning-topics-{userId}` entry in localStorage BEFORE the sidebar
 *      mounts (i.e. while still on the dashboard).
 *   2. Navigate to /learning so the sidebar mounts and runs the migration.
 *   3. Assert: the topics appear in the sidebar AND in the backend API,
 *      and the localStorage key was cleared.
 *   4. Navigate away and back: the topics must NOT be duplicated (still the
 *      same count).
 *   5. Cleanup: delete the migrated topics via the teacher API.
 *
 * Run from src/frontend while the backend serves on 127.0.0.1:8086:
 *   node scripts/verify-topic-migration.mjs
 */
import { chromium } from '@playwright/test';

const BASE = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:8086';

const failures = [];
function check(name, ok, detail = '') {
  console.log(`[${ok ? 'PASS' : 'FAIL'}] ${name}${detail ? ` — ${detail}` : ''}`);
  if (!ok) failures.push(name);
}

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

// --- Login as teacher1 ---
console.log('\n=== Login ===');
await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded', timeout: 30000 });
await page.waitForTimeout(800);
await page.locator('#username').fill('teacher1');
await page.locator('#password').fill('Teacher123');
await page.locator('button[type="submit"]').click();
await page.waitForURL((u) => !/\/login(?:[/?#]|$)/.test(u.pathname + u.search), {
  timeout: 20000,
});
await page.waitForTimeout(1200);
check('Login succeeds', true);

// --- Seed legacy localStorage data (before the sidebar ever mounts) ---
console.log('\n=== Seed legacy localStorage ===');
const markerA = `Migración A ${Date.now()}`;
const markerB = `Migración B ${Date.now()}`;
const seeded = await page.evaluate(
  async ([m1, m2]) => {
    const auth = JSON.parse(localStorage.getItem('auth-storage') || '{}');
    const userId = auth?.state?.user?.id;
    if (!userId) return { ok: false, userId: null };
    localStorage.setItem(
      `learning-topics-${userId}`,
      JSON.stringify([
        { id: Date.now(), board: 'El cielo', topic: m1, createdBy: 'Mig Test' },
        { id: Date.now() + 1, board: 'Clase', boardId: 7, topic: m2, createdBy: 'Mig Test' },
      ]),
    );
    return { ok: true, userId };
  },
  [markerA, markerB],
);
check('Legacy localStorage seeded', seeded.ok, `user ${seeded.userId}`);

// --- Mount the sidebar on /learning -> migration runs ---
console.log('\n=== Migration on first load ===');
await page.goto(`${BASE}/learning`, { waitUntil: 'domcontentloaded', timeout: 30000 });
await page.waitForTimeout(3500);

let body = await page.locator('body').innerText();
check('Migrated topics appear in the sidebar', body.includes(markerA) && body.includes(markerB));

const afterFirst = await page.evaluate(async ([m1, m2]) => {
  const auth = JSON.parse(localStorage.getItem('auth-storage') || '{}');
  const token = auth?.state?.token;
  const userId = auth?.state?.user?.id;
  const res = await fetch('/api/learning/topics/saved', {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  const topics = await res.json();
  const matching = Array.isArray(topics)
    ? topics.filter((t) => [m1, m2].includes(String(t.topic)))
    : [];
  return {
    count: matching.length,
    topics: matching.map((t) => t.topic),
    localKeyStillThere: localStorage.getItem(`learning-topics-${userId}`) !== null,
  };
}, [markerA, markerB]);

check('Topics landed in the backend API', afterFirst.count === 2, `found ${afterFirst.count}: ${JSON.stringify(afterFirst.topics)}`);
check('localStorage copy cleared after migration', !afterFirst.localKeyStillThere);

await page.screenshot({ path: 'scripts/_migration_first.png', fullPage: true });

// --- Reload: no duplication ---
console.log('\n=== Reload (no duplication) ===');
await page.goto(`${BASE}/learning`, { waitUntil: 'domcontentloaded', timeout: 30000 });
await page.waitForTimeout(3000);
const afterSecond = await page.evaluate(async ([m1, m2]) => {
  const auth = JSON.parse(localStorage.getItem('auth-storage') || '{}');
  const token = auth?.state?.token;
  const res = await fetch('/api/learning/topics/saved', {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  const topics = await res.json();
  return Array.isArray(topics)
    ? topics.filter((t) => [m1, m2].includes(String(t.topic))).length
    : -1;
}, [markerA, markerB]);
check('No duplicated topics after reload', afterSecond === 2, `count ${afterSecond}`);

await page.screenshot({ path: 'scripts/_migration_reload.png', fullPage: true });

// --- Cleanup: delete the migrated topics ---
console.log('\n=== Cleanup ===');
const deleted = await page.evaluate(async ([m1, m2]) => {
  const auth = JSON.parse(localStorage.getItem('auth-storage') || '{}');
  const token = auth?.state?.token;
  const res = await fetch('/api/learning/topics/saved', {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  const topics = await res.json();
  let removed = 0;
  for (const t of topics) {
    if ([m1, m2].includes(String(t.topic))) {
      const del = await fetch(`/api/learning/topics/saved/${t.id}`, {
        method: 'DELETE',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (del.ok || del.status === 204) removed += 1;
    }
  }
  return removed;
}, [markerA, markerB]);
check('Migrated topics cleaned up', deleted === 2, `removed ${deleted}`);

await browser.close();

console.log(`\n=== ${failures.length === 0 ? 'ALL CHECKS PASSED' : `${failures.length} FAILURES`} ===`);
if (failures.length > 0) process.exit(1);
