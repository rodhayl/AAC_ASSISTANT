/**
 * Production-build guard for the Playwright e2e suite.
 *
 * Two checks, used by the Playwright global setup (e2e/global-setup.ts) and by
 * the standalone script (scripts/verify-prod-build.mjs):
 *
 * 1. Dist freshness: `dist/index.html` must be newer than every frontend build
 *    input, so the suite never silently runs against a stale bundle.
 * 2. Production serving: the server behind the base URL must serve the built
 *    SPA (dist), not the Vite dev server. When the target is localhost, the
 *    assets referenced by the served HTML are also verified to exist in dist,
 *    so the suite cannot run against a different/stale build.
 *
 * Plain ESM (no TypeScript) on purpose: this module is imported by Node 20 in
 * CI, which cannot strip TypeScript types.
 */

import { existsSync, readdirSync, statSync } from 'node:fs';
import path from 'node:path';

const DEFAULT_BASE_URL = 'http://127.0.0.1:8086';

// Directories that are build inputs, scanned for their newest mtime.
const BUILD_INPUT_DIRS = ['src', 'public'];
// Root-level files that are build inputs.
const BUILD_INPUT_FILES = [
  'index.html',
  'vite.config.ts',
  'package.json',
  'tsconfig.json',
  'tsconfig.app.json',
  'tsconfig.node.json',
];
// Subdirectories that are NOT build inputs (test code, tooling, outputs).
const IGNORED_DIRS = new Set([
  'node_modules',
  'dist',
  'e2e',
  'tests',
  'test-results',
  'playwright',
  '.git',
  '.vite',
]);

// Filesystem timestamps can round to the same second; a 1s grace avoids
// false failures right after a build.
const TIMESTAMP_GRACE_MS = 1000;
const REQUEST_TIMEOUT_MS = 10000;

/**
 * Resolve the base URL exactly like playwright.config.ts does.
 */
export function resolveBaseUrl(env = process.env) {
  return env.PLAYWRIGHT_BASE_URL || DEFAULT_BASE_URL;
}

function newestMtimeMs(filePath) {
  const stat = statSync(filePath);
  if (!stat.isDirectory()) return stat.mtimeMs;
  let newest = 0;
  for (const entry of readdirSync(filePath, { withFileTypes: true })) {
    if (entry.isDirectory() && IGNORED_DIRS.has(entry.name)) continue;
    newest = Math.max(newest, newestMtimeMs(path.join(filePath, entry.name)));
  }
  return newest;
}

/**
 * Check that `dist/index.html` is newer than every frontend build input.
 * Test-only directories (e2e/, tests/) are deliberately excluded so adding
 * or editing specs never trips the guard.
 *
 * @param {string} frontendRoot Absolute path to the frontend project root
 *   (the directory containing index.html and dist/).
 * @returns {{ ok: boolean, message: string }}
 */
export function checkDistFreshness(frontendRoot) {
  const distIndex = path.join(frontendRoot, 'dist', 'index.html');
  if (!existsSync(distIndex)) {
    return {
      ok: false,
      message:
        `dist/index.html is missing (${distIndex}). Build the frontend with ` +
        '"npm run build" before running the e2e suite.',
    };
  }
  const distTimeMs = statSync(distIndex).mtimeMs;

  let newestInputMs = 0;
  let newestInput = '';
  for (const file of BUILD_INPUT_FILES) {
    const full = path.join(frontendRoot, file);
    if (!existsSync(full)) continue;
    const mtimeMs = statSync(full).mtimeMs;
    if (mtimeMs > newestInputMs) {
      newestInputMs = mtimeMs;
      newestInput = full;
    }
  }
  for (const dir of BUILD_INPUT_DIRS) {
    const full = path.join(frontendRoot, dir);
    if (!existsSync(full) || !statSync(full).isDirectory()) continue;
    const mtimeMs = newestMtimeMs(full);
    if (mtimeMs > newestInputMs) {
      newestInputMs = mtimeMs;
      newestInput = full;
    }
  }

  if (newestInputMs > distTimeMs + TIMESTAMP_GRACE_MS) {
    return {
      ok: false,
      message:
        `dist is stale: dist/index.html (${new Date(distTimeMs).toISOString()}) ` +
        `is older than ${path.relative(frontendRoot, newestInput) || newestInput} ` +
        `(${new Date(newestInputMs).toISOString()}). Rebuild with "npm run build" ` +
        'before running the e2e suite.',
    };
  }
  return {
    ok: true,
    message: `dist is up to date (${new Date(distTimeMs).toISOString()}).`,
  };
}

function isLocalhostUrl(baseURL) {
  try {
    return ['localhost', '127.0.0.1', '::1'].includes(new URL(baseURL).hostname);
  } catch {
    return false;
  }
}

/**
 * Check that the server at `baseURL` serves the built SPA rather than the
 * Vite dev server, and (for localhost targets) that the referenced assets
 * exist in `frontendRoot/dist`.
 *
 * @param {string} baseURL Base URL of the running application.
 * @param {string} frontendRoot Absolute path to the frontend project root.
 * @param {typeof fetch} [fetchFn] Injectable fetch for tests.
 * @returns {Promise<{ ok: boolean, message: string }>}
 */
export async function checkProductionServer(baseURL, frontendRoot, fetchFn = globalThis.fetch) {
  let html;
  try {
    const res = await fetchFn(`${baseURL.replace(/\/+$/, '')}/`, {
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
    if (!res.ok) {
      return {
        ok: false,
        message:
          `Server at ${baseURL} returned HTTP ${res.status} for "/" — expected ` +
          'the production SPA. Is the backend (uvicorn src.api.main:app) running?',
      };
    }
    html = await res.text();
  } catch (err) {
    return {
      ok: false,
      message:
        `Cannot reach a server at ${baseURL}: ${err?.message ?? err}. Start the ` +
        'backend (uvicorn src.api.main:app) before running the e2e suite.',
    };
  }

  if (html.includes('/@vite/client') || /<script[^>]*\bsrc="\/src\/[^"]+"/.test(html)) {
    return {
      ok: false,
      message:
        `Vite dev server detected at ${baseURL} (served HTML references ` +
        '@vite/client). The e2e suite must run against the production build: ' +
        'run "npm run build" and point PLAYWRIGHT_BASE_URL at the backend port.',
    };
  }

  const assetRefs = [...html.matchAll(/(?:src|href)="(\/assets\/[^"]+)"/g)].map(
    (match) => match[1],
  );
  if (assetRefs.length === 0) {
    return {
      ok: false,
      message:
        `No /assets/ references found in the HTML served at ${baseURL} — this ` +
        'does not look like the built SPA (dist/index.html).',
    };
  }

  if (isLocalhostUrl(baseURL)) {
    const missing = assetRefs.filter(
      (asset) => !existsSync(path.join(frontendRoot, 'dist', asset)),
    );
    if (missing.length > 0) {
      return {
        ok: false,
        message:
          `Server at ${baseURL} serves HTML referencing assets missing from ` +
          `dist: ${missing.join(', ')}. Rebuild with "npm run build" and restart ` +
          'the backend.',
      };
    }
  }

  return {
    ok: true,
    message: `Production SPA confirmed at ${baseURL} (${assetRefs.length} assets referenced).`,
  };
}
