#!/usr/bin/env node
/**
 * Standalone production-build guard (CI-friendly).
 *
 *   node scripts/verify-prod-build.mjs [--freshness-only] [--base-url URL]
 *
 * Checks that:
 *   - dist/ is newer than every frontend build input, and
 *   - the server at --base-url (default: PLAYWRIGHT_BASE_URL or
 *     http://127.0.0.1:8086) serves the production SPA, not the Vite dev
 *     server.
 *
 * Exit code 0 when all checks pass, 1 otherwise. `--freshness-only` skips the
 * server check (used in CI jobs that build but do not run a backend).
 */

import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  checkDistFreshness,
  checkProductionServer,
  resolveBaseUrl,
} from '../e2e/prod-guard.mjs';

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

const args = process.argv.slice(2);
const freshnessOnly = args.includes('--freshness-only');
const baseUrlFlagIndex = args.indexOf('--base-url');
const baseURL =
  baseUrlFlagIndex >= 0 && args[baseUrlFlagIndex + 1]
    ? args[baseUrlFlagIndex + 1]
    : resolveBaseUrl();

const freshness = checkDistFreshness(frontendRoot);
if (!freshness.ok) {
  console.error(`[prod-guard] ${freshness.message}`);
  process.exit(1);
}
console.log(`[prod-guard] ${freshness.message}`);

if (freshnessOnly) {
  console.log('[prod-guard] --freshness-only: server check skipped');
  process.exit(0);
}

const server = await checkProductionServer(baseURL, frontendRoot);
if (!server.ok) {
  console.error(`[prod-guard] ${server.message}`);
  process.exit(1);
}
console.log(`[prod-guard] ${server.message}`);
process.exit(0);
