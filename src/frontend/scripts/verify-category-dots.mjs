/**
 * Visual verification that symbol-category dots come from the shared avatar
 * palette. Logs in as admin, opens a board (the board seed has symbols in
 * several categories), and asserts the rendered dot classes are palette
 * colors — e.g. emotions now resolves to violet instead of purple.
 *
 * Run from src/frontend while the backend serves on 127.0.0.1:8086:
 *   node scripts/verify-category-dots.mjs
 */
import { chromium } from '@playwright/test';

const BASE = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:8086';

const failures = [];
function check(name, ok, detail = '') {
  console.log(`[${ok ? 'PASS' : 'FAIL'}] ${name}${detail ? ` — ${detail}` : ''}`);
  if (!ok) failures.push(name);
}

const PALETTE = [
  'bg-indigo-500',
  'bg-sky-500',
  'bg-emerald-500',
  'bg-amber-500',
  'bg-rose-500',
  'bg-violet-500',
  'bg-teal-500',
  'bg-orange-500',
];

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

// --- Login as admin ---
await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded', timeout: 30000 });
await page.waitForTimeout(800);
await page.locator('#username').fill('admin1');
await page.locator('#password').fill('Admin123');
await page.locator('button[type="submit"]').click();
await page.waitForURL((u) => !/\/login(?:[/?#]|$)/.test(u.pathname + u.search), { timeout: 20000 });
await page.waitForTimeout(1200);
check('Login succeeds', true);

// --- Find a playable board via the API and open it ---
const boardId = await page.evaluate(async () => {
  const auth = JSON.parse(localStorage.getItem('auth-storage') || '{}');
  const token = auth?.state?.token;
  const res = await fetch('/api/boards?limit=100', {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  const boards = res.ok ? await res.json() : [];
  const arr = Array.isArray(boards) ? boards : boards.boards ?? [];
  const playable = arr.find(
    (b) => (b.playable_symbols_count ?? 0) > 0 || (b.symbols?.length ?? 0) > 0,
  );
  return playable ? playable.id : null;
});
check('Found a playable board', Boolean(boardId), boardId ? `id ${boardId}` : 'none');

if (boardId) {
  await page.goto(`${BASE}/communication?boardId=${boardId}`, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForTimeout(3500);

  // Collect every category-dot class rendered on the board's symbol cards.
  // These are the small top-left dots on symbol tiles; the navbar's
  // unread badge and the recording badge are not category dots.
  const dotClasses = await page.evaluate(() => {
    const out = [];
    // Category dots are aria-hidden (SymbolCard/SentenceStrip/SymbolPicker).
    for (const el of document.querySelectorAll('[aria-hidden="true"].rounded-full')) {
      const cls = typeof el.className === 'string' ? el.className : '';
      const match = cls.match(/bg-[a-z]+-500/);
      if (match) out.push(match[0]);
    }
    return out;
  });
  check('Board rendered some category dots', dotClasses.length > 0, `${dotClasses.length} dots`);

  const nonPalette = dotClasses.filter((c) => !PALETTE.includes(c) && c !== 'bg-muted-foreground');
  check('All colored dots come from the avatar palette', nonPalette.length === 0, `non-palette: ${JSON.stringify([...new Set(nonPalette)])}`);
  check('No purple-500 dots remain (emotions uses violet now)', !dotClasses.includes('bg-purple-500'));

  await page.screenshot({ path: 'scripts/_category_dots.png', fullPage: true });
}

await browser.close();

console.log(`\n=== ${failures.length === 0 ? 'ALL CHECKS PASSED' : `${failures.length} FAILURES`} ===`);
if (failures.length > 0) process.exit(1);
