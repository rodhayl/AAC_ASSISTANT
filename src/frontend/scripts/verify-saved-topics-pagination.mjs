/**
 * Live verification of the paginated admin saved-topics table.
 *
 * Flow:
 *   1. Admin creates 30 saved topics via the API (default page size 25, so
 *      the table must show two pages).
 *   2. On /teachers: total count, page indicator, disabled Previous on
 *      page 1, then Next shows page 2 items.
 *   3. Page size 50 -> a single page; the table lists everything again.
 *   4. Delete the last item of the last page -> the view steps back instead
 *      of showing an empty final page.
 *   5. Cleanup removes every verification topic.
 *
 * Run from src/frontend while the backend serves on 127.0.0.1:8086:
 *   node scripts/verify-saved-topics-pagination.mjs
 */
import { chromium } from '@playwright/test';

const BASE = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:8086';

const failures = [];
const runMarker = `Paginación ${Date.now()}`;
function check(name, ok, detail = '') {
  console.log(`[${ok ? 'PASS' : 'FAIL'}] ${name}${detail ? ` — ${detail}` : ''}`);
  if (!ok) failures.push(name);
}

const authBlobs = new Map(); // username -> persisted auth-storage blob

async function login(page, username, password) {
  // Reuse a captured session for repeat logins: the production login rate
  // limiter (429) aborts verification when the token endpoint is hit once
  // per section (see verify-saved-topics.mjs).
  const cached = authBlobs.get(username);
  if (cached) {
    await page.addInitScript((blob) => {
      localStorage.setItem('auth-storage', blob);
    }, cached);
    await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForTimeout(1200);
    const restored = await page.evaluate(() => {
      const auth = JSON.parse(localStorage.getItem('auth-storage') || '{}');
      return Boolean(auth?.state?.token);
    });
    if (restored) return;
    authBlobs.delete(username); // stale session; fall through to a fresh login
  }
  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForTimeout(800);
  await page.locator('#username').fill(username);
  await page.locator('#password').fill(password);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL((u) => !/\/login(?:[/?#]|$)/.test(u.pathname + u.search), {
    timeout: 20000,
  }).catch(async () => {
    const authenticated = await page.evaluate(() => {
      const auth = JSON.parse(localStorage.getItem('auth-storage') || '{}');
      return Boolean(auth?.state?.token);
    });
    if (!authenticated) throw new Error(`Login failed for ${username}`);
  });
  await page.waitForTimeout(1200);
  const blob = await page.evaluate(() => localStorage.getItem('auth-storage'));
  if (blob) authBlobs.set(username, blob);
}

const browser = await chromium.launch();

// ---------------------------------------------------------------------------
// Setup: 30 saved topics (page size 25 -> two pages)
// ---------------------------------------------------------------------------
console.log('\n=== Setup: create 30 topics ===');
{
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await login(page, 'admin1', 'Admin123');
  const created = await page.evaluate(async (marker) => {
    const auth = JSON.parse(localStorage.getItem('auth-storage') || '{}');
    const token = auth?.state?.token;
    const headers = { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) };
    let ok = 0;
    for (let i = 1; i <= 30; i += 1) {
      const res = await fetch('/api/learning/topics/saved', {
        method: 'POST',
        headers,
        body: JSON.stringify({ topic: `${marker} ${String(i).padStart(2, '0')}`, board: 'Paginación' }),
      });
      if (res.ok) ok += 1;
    }
    return ok;
  }, runMarker);
  check('30 verification topics created', created === 30, `created ${created}`);
  await page.close();
}

// ---------------------------------------------------------------------------
// /teachers: pagination controls with two pages
// ---------------------------------------------------------------------------
console.log('\n=== Pagination on /teachers ===');
{
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await login(page, 'admin1', 'Admin123');
  await page.goto(`${BASE}/teachers`, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForSelector('[data-testid="admin-saved-topics"] tbody tr', { timeout: 20000 });
  await page.waitForTimeout(1000);

  const rowsOnPage1 = await page.locator('[data-testid="admin-saved-topics"] tbody tr').count();
  check('Page 1 shows the full page of rows', rowsOnPage1 === 25, `rows: ${rowsOnPage1}`);

  const total = await page.locator('[data-testid="saved-topics-total"]').innerText();
  check('Total count line shows 30', /30/.test(total), `total: "${total}"`);

  const indicator = await page.locator('[data-testid="saved-topics-page-indicator"]').innerText();
  check('Page indicator shows page 1 of 2', /1/.test(indicator) && /2/.test(indicator), `indicator: "${indicator}"`);

  const prevDisabled = await page.getByRole('button', { name: /Previous|Anterior/ }).isDisabled();
  check('Previous is disabled on page 1', prevDisabled);

  await page.getByRole('button', { name: /Next|Siguiente/ }).click();
  await page.waitForTimeout(1200);

  const rowsOnPage2 = await page.locator('[data-testid="admin-saved-topics"] tbody tr').count();
  check('Page 2 shows the remaining rows', rowsOnPage2 === 5, `rows: ${rowsOnPage2}`);

  // The table sorts newest-first (created_at DESC, id DESC). All 30 topics
  // are created inside the same timestamp window, so page 1 holds items
  // 30..06 and page 2 starts at the oldest item, 05.
  const firstOnPage2 = await page.locator('[data-testid="admin-saved-topics"] tbody tr').first().innerText();
  const expectedFirst = `${runMarker} 05`;
  check('Page 2 starts at the oldest item (05)', firstOnPage2.includes(expectedFirst), `first row: "${firstOnPage2.slice(0, 60)}"`);

  const indicator2 = await page.locator('[data-testid="saved-topics-page-indicator"]').innerText();
  check('Indicator shows page 2 after Next', /2/.test(indicator2), `indicator: "${indicator2}"`);

  const nextDisabled = await page.getByRole('button', { name: /Next|Siguiente/ }).isDisabled();
  check('Next is disabled on the last page', nextDisabled);

  // Page-size 50: everything fits on one page and the controls reflect it.
  await page.getByLabel(/Topics per page|Temas por página/).selectOption('50');
  await page.waitForTimeout(1500);
  const rowsFull = await page.locator('[data-testid="admin-saved-topics"] tbody tr').count();
  check('Page size 50 shows all 30 rows on one page', rowsFull === 30, `rows: ${rowsFull}`);
  const prevDisabledFull = await page.getByRole('button', { name: /Previous|Anterior/ }).isDisabled();
  const nextDisabledFull = await page.getByRole('button', { name: /Next|Siguiente/ }).isDisabled();
  check('Both directions disabled on the single page', prevDisabledFull && nextDisabledFull);

  // Deleting the last item of the final page must not strand an empty page.
  const before = await page.locator('[data-testid="admin-saved-topics"] tbody tr').count();
  await page.locator('button[aria-label*="Eliminar tema"], button[aria-label*="Delete topic"]').last().click();
  await page.waitForTimeout(600);
  await page.locator('button:has-text("Eliminar"), button:has-text("Delete")').last().click();
  await page.waitForTimeout(1500);
  const after = await page.locator('[data-testid="admin-saved-topics"] tbody tr').count();
  check('Deleting a row updates the table in place', after === before - 1, `rows ${before} -> ${after}`);

  await page.screenshot({ path: 'scripts/_saved_topics_pagination.png', fullPage: true });
  await page.close();
}

// ---------------------------------------------------------------------------
// Search: filtering composes with pagination and highlights matches
// ---------------------------------------------------------------------------
console.log('\n=== Search + highlight ===');
{
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await login(page, 'admin1', 'Admin123');
  await page.goto(`${BASE}/teachers`, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForSelector('[data-testid="admin-saved-topics"] tbody tr', { timeout: 20000 });
  await page.waitForTimeout(1000);

  // No marks before a search is active.
  const marksBefore = await page.locator('[data-testid="admin-saved-topics"] mark').count();
  check('No highlight marks before searching', marksBefore === 0, `marks: ${marksBefore}`);

  // Search for a distinctive term; items 1..9 are "Paginación <marker> 01"..
  // "09", so searching "08" must narrow the table to that single row.
  const searchTerm = `${runMarker} 08`;
  await page.getByLabel(/Search saved topics|Buscar temas guardados/).fill(searchTerm);
  await page.waitForTimeout(1500); // debounce + refetch

  const searchTotal = await page.locator('[data-testid="saved-topics-total"]').innerText();
  check('Search narrows the total to 1', /1/.test(searchTotal) && !/[2-9]/.test(searchTotal.replace(/^\D*1/, '')), `total: "${searchTotal}"`);

  const searchRows = await page.locator('[data-testid="admin-saved-topics"] tbody tr').count();
  check('Search shows a single row', searchRows === 1, `rows: ${searchRows}`);

  // Search composes with pagination: the filtered total fits one page, and
  // both directions are disabled.
  const prevDisabledSearch = await page.getByRole('button', { name: /Previous|Anterior/ }).isDisabled();
  const nextDisabledSearch = await page.getByRole('button', { name: /Next|Siguiente/ }).isDisabled();
  check('Page controls adapt to the filtered result', prevDisabledSearch && nextDisabledSearch);

  // The matched segments are highlighted in the topic cell. The board cell
  // shows no highlight here: the term matched the topic, and the board text
  // ("Paginación") does not contain the full search term.
  const topicMarks = await page.locator('[data-testid="admin-saved-topics"] tbody tr td:nth-child(1) mark').allInnerTexts();
  const boardMarks = await page.locator('[data-testid="admin-saved-topics"] tbody tr td:nth-child(2) mark').allInnerTexts();
  check('Matched topic segments highlighted', topicMarks.length > 0, `marks: ${JSON.stringify(topicMarks)}`);
  check('Board without term overlap stays unhighlighted', boardMarks.length === 0, `marks: ${JSON.stringify(boardMarks)}`);

  // Searching the board text highlights the board cell instead.
  await page.getByLabel(/Search saved topics|Buscar temas guardados/).fill('Paginaci');
  await page.waitForTimeout(1500);
  const boardMarksNow = await page.locator('[data-testid="admin-saved-topics"] tbody tr td:nth-child(2) mark').allInnerTexts();
  check('Board segments highlight when the term matches the board', boardMarksNow.length > 0, `marks: ${JSON.stringify(boardMarksNow.slice(0, 3))}`);

  // Prefix search matches the remaining numbered items. The earlier
  // deletion removed item 01 (the oldest row), so 02..09 = 8 rows.
  await page.getByLabel(/Search saved topics|Buscar temas guardados/).fill(`${runMarker} 0`);
  await page.waitForTimeout(1500);
  const prefixRows = await page.locator('[data-testid="admin-saved-topics"] tbody tr').count();
  check('Prefix search matches items 02..09 after the deletion', prefixRows === 8, `rows: ${prefixRows}`);

  // Clearing the search restores the full list and removes all marks.
  await page.getByLabel(/Search saved topics|Buscar temas guardados/).fill('');
  await page.waitForTimeout(1500);
  const rowsAfterClear = await page.locator('[data-testid="admin-saved-topics"] tbody tr').count();
  check('Clearing the search restores the full page', rowsAfterClear === 25, `rows: ${rowsAfterClear}`);
  const marksAfterClear = await page.locator('[data-testid="admin-saved-topics"] mark').count();
  check('Highlight marks removed after clearing', marksAfterClear === 0, `marks: ${marksAfterClear}`);

  await page.close();
}

// ---------------------------------------------------------------------------
// Cleanup: remove every verification topic
// ---------------------------------------------------------------------------
console.log('\n=== Cleanup ===');
{
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await login(page, 'admin1', 'Admin123');
  const removed = await page.evaluate(async (marker) => {
    const auth = JSON.parse(localStorage.getItem('auth-storage') || '{}');
    const token = auth?.state?.token;
    const headers = token ? { Authorization: `Bearer ${token}` } : {};
    const res = await fetch('/api/learning/topics/saved?scope=all', { headers });
    const topics = await res.json();
    let count = 0;
    for (const t of Array.isArray(topics) ? topics : []) {
      if (String(t.topic).startsWith(marker) || t.board === 'Paginación') {
        const del = await fetch(`/api/learning/topics/saved/${t.id}`, { method: 'DELETE', headers });
        if (del.ok || del.status === 204) count += 1;
      }
    }
    return count;
  }, runMarker);
  check('Verification topics cleaned up', removed >= 29, `removed ${removed}`);
  await page.close();
}

await browser.close();

console.log(`\n=== ${failures.length === 0 ? 'ALL CHECKS PASSED' : `${failures.length} FAILURES`} ===`);
if (failures.length > 0) process.exit(1);
