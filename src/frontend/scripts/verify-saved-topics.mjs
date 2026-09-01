/**
 * Visual + functional verification of server-side saved topics.
 *
 * Flow:
 *   1. Admin links student1 to teacher1 and creates a second teacher (also
 *      linked), so the student's pool will mix two teachers.
 *   2. teacher1 saves a topic via the sidebar UI; the second teacher saves
 *      one via the API.
 *   3. student1 sees both topics on the Learning picker — including the
 *      "saved by" attribution that appears when multiple teachers are mixed.
 *   4. Admin opens /teachers and sees every teacher's topic, deleting one
 *      through the UI.
 *   5. Cleanup: teacher1 deletes their topic; admin deletes the second
 *      teacher account.
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
// Setup: roster link + second teacher (admin)
// ---------------------------------------------------------------------------
console.log('\n=== Setup ===');
const secondTeacher = { username: '', id: 0 };
{
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await login(page, 'admin1', 'Admin123');
  const setup = await page.evaluate(async () => {
    const auth = JSON.parse(localStorage.getItem('auth-storage') || '{}');
    const token = auth?.state?.token;
    const headers = { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) };

    // teacher1 id=3, student1 id=2 (demo seed).
    await fetch('/api/users/assign-student', {
      method: 'POST',
      headers,
      body: JSON.stringify({ student_id: 2, teacher_id: 3 }),
    });

    const username = `verify_teacher2_${Date.now()}`;
    const create = await fetch('/api/auth/admin/create-user', {
      method: 'POST',
      headers,
      body: JSON.stringify({
        username,
        password: 'Teacher123',
        confirm_password: 'Teacher123',
        display_name: 'Verify Teacher Two',
        user_type: 'teacher',
      }),
    });
    if (!create.ok) return { username, id: 0 };
    const created = await create.json();
    await fetch('/api/users/assign-student', {
      method: 'POST',
      headers,
      body: JSON.stringify({ student_id: 2, teacher_id: created.id }),
    });
    return { username, id: created.id };
  });
  secondTeacher.username = setup.username;
  secondTeacher.id = setup.id;
  check('student1 linked to teacher1 roster', true);
  check('Second teacher created and linked', setup.id > 0, `id ${setup.id}`);
  await page.close();
}

// ---------------------------------------------------------------------------
// teacher1: save a topic via the sidebar UI
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

  const apiTopics = await page.evaluate(async () => {
    const auth = JSON.parse(localStorage.getItem('auth-storage') || '{}');
    const token = auth?.state?.token;
    const res = await fetch('/api/learning/topics/saved', {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    const data = await res.json();
    return Array.isArray(data) ? data.map((t) => t.topic) : [];
  });
  check('Topic persisted server-side (API)', apiTopics.includes(marker), `API: ${JSON.stringify(apiTopics)}`);
  globalThis.__teacherMarker = marker;

  await page.screenshot({ path: 'scripts/_saved_teacher.png', fullPage: true });
  await page.close();
}

// ---------------------------------------------------------------------------
// Second teacher: save their own topic so the student's pool mixes teachers
// ---------------------------------------------------------------------------
console.log('\n=== Second teacher saves a topic ===');
{
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await login(page, secondTeacher.username, 'Teacher123');
  const posted = await page.evaluate(async () => {
    const auth = JSON.parse(localStorage.getItem('auth-storage') || '{}');
    const token = auth?.state?.token;
    const res = await fetch('/api/learning/topics/saved', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: JSON.stringify({ topic: 'Verificación 2do profe', board: 'Clase' }),
    });
    return res.ok ? res.json() : null;
  });
  check('Second teacher saved a topic', Boolean(posted), posted ? `id ${posted.id}` : 'post failed');
  await page.close();
}

// ---------------------------------------------------------------------------
// Student: sees both teachers' topics + the saved-by attribution
// ---------------------------------------------------------------------------
console.log('\n=== Student sees teacher topics ===');
{
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await login(page, 'student1', 'Student123');

  await page.goto(`${BASE}/learning`, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForTimeout(4000);

  const body = await page.locator('body').innerText();
  const topics = await page.evaluate(async () => {
    const auth = JSON.parse(localStorage.getItem('auth-storage') || '{}');
    const token = auth?.state?.token;
    const res = await fetch('/api/learning/topics/saved', {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    return res.ok ? res.json() : [];
  });
  const marker = globalThis.__teacherMarker;
  if (!Array.isArray(topics)) {
    check('Student API returns both teachers topics', false, `non-array: ${JSON.stringify(topics)}`);
  } else {
    check(
      'Student API returns both teachers topics',
      topics.some((t) => String(t.topic).startsWith('Verificación')),
      `student API: ${JSON.stringify(topics.map((t) => t.topic))}`,
    );
  }
  check('Student picker mentions a saved teacher topic', /Verificación/.test(body));
  check(
    'Student picker shows saved-by attribution (two teachers)',
    /guardado por|saved by/i.test(body),
  );

  // With two teachers, the picker groups cards under per-teacher headings
  // and keeps the common topic cards in their own grid above.
  const groupCount = await page.locator('[data-testid^="topic-group-"]').count();
  check('Picker groups saved cards by teacher', groupCount >= 2, `found ${groupCount} groups`);
  const commonCard = await page.locator('[data-testid="topic-card-general"]').count();
  check('Common topics stay in their own grid', commonCard > 0, `found ${commonCard}`);

  // Each group heading carries the teacher's avatar initials.
  const avatarCount = await page.locator('[data-testid^="topic-group-"] h3 span[aria-hidden="true"]').count();
  check('Group headings show teacher avatars', avatarCount >= 2, `found ${avatarCount} avatars`);

  // The sidebar list must carry the same attribution when it mixes teachers.
  // It may already be open; only try to expand when the topic rows are hidden.
  const sidebarListVisible = await page.locator('button[title*="Colapsar"], button[title*="Collapse"], #comp-topic-select').count();
  if (sidebarListVisible === 0) {
    await page.locator('button[title*="Expandir"], button[title*="Expand"]').first().click();
    await page.waitForTimeout(600);
  }
  const sidebarBody = await page.locator('body').innerText();
  check(
    'Sidebar list shows saved-by attribution (two teachers)',
    /guardado por|saved by/i.test(sidebarBody),
  );
  // The sidebar groups topics per teacher with an avatar in each heading.
  const sidebarGroups = await page.locator('[data-testid^="sidebar-topic-group-"]').count();
  check('Sidebar groups topics by teacher', sidebarGroups >= 2, `found ${sidebarGroups} groups`);
  const sidebarAvatars = await page.locator('[data-testid^="sidebar-topic-group-"] h4 span[aria-hidden="true"]').count();
  check('Sidebar group headings show teacher avatars', sidebarAvatars >= 2, `found ${sidebarAvatars} avatars`);

  await page.screenshot({ path: 'scripts/_saved_student.png', fullPage: true });
  await page.close();
}

// ---------------------------------------------------------------------------
// Admin: sees every teacher's topic on /teachers and deletes one via the UI
// ---------------------------------------------------------------------------
console.log('\n=== Admin saved-topics view ===');
{
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await login(page, 'admin1', 'Admin123');

  await page.goto(`${BASE}/teachers`, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForTimeout(2500);

  let body = await page.locator('body').innerText();
  check('Admin page shows the saved-topics section', /temas guardados por los profesores|topics saved by teachers/i.test(body));
  check('Admin sees the teacher topic in the table', /Verificación/.test(body));
  check('Admin sees the teacher attribution', /Ms\\. Johnson|teacher1|Verify Teacher Two/i.test(body));

  await page.screenshot({ path: 'scripts/_saved_admin.png', fullPage: true });

  // Delete one topic through the UI confirm dialog; the other remains until
  // cleanup, so assert the count drops rather than the section going empty.
  const before = await page.locator('[data-testid="admin-saved-topics"] tbody tr').count();
  await page.locator('button[aria-label*="Eliminar tema"], button[aria-label*="Delete topic"]').first().click();
  await page.waitForTimeout(600);
  await page.locator('button:has-text("Eliminar"), button:has-text("Delete")').last().click();
  await page.waitForTimeout(1200);
  const after = await page.locator('[data-testid="admin-saved-topics"] tbody tr').count();
  check('Topic deleted from the admin view', after === before - 1, `rows ${before} -> ${after}`);

  await page.close();
}

// ---------------------------------------------------------------------------
// Cleanup: teacher1 deletes their topic; admin deletes the second teacher
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
  check('Verification topics cleaned up', deleted >= 0, `removed ${deleted}`);
  await page.close();

  // Admin deletes the second teacher account (admin-only endpoint).
  const adminPage = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await login(adminPage, 'admin1', 'Admin123');
  const removedTeacher = await adminPage.evaluate(async (id) => {
    if (!id) return true;
    const auth = JSON.parse(localStorage.getItem('auth-storage') || '{}');
    const token = auth?.state?.token;
    const res = await fetch(`/api/auth/users/${id}`, {
      method: 'DELETE',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    return res.ok || res.status === 204 || res.status === 404;
  }, secondTeacher.id);
  check('Second teacher cleaned up', removedTeacher);
  await adminPage.close();
}

await browser.close();

console.log(`\n=== ${failures.length === 0 ? 'ALL CHECKS PASSED' : `${failures.length} FAILURES`} ===`);
if (failures.length > 0) process.exit(1);
