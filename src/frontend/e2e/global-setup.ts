import path from 'node:path';
import type { FullConfig } from '@playwright/test';
import { checkDistFreshness, checkProductionServer, resolveBaseUrl } from './prod-guard.mjs';

/**
 * Runs once before the whole e2e suite (including the auth setup project).
 *
 * Fails fast with an actionable message when the suite is misconfigured:
 *  - the built frontend (dist/) is stale or missing, or
 *  - the server behind PLAYWRIGHT_BASE_URL is the Vite dev server instead of
 *    the production backend serving dist/.
 *
 * Set AAC_E2E_SKIP_GUARD=1 to bypass intentionally (e.g. debugging against a
 * dev server); the guard is otherwise always active so CI and local runs
 * cannot silently test the wrong build.
 */
export default async function globalSetup(config: FullConfig): Promise<void> {
  if (process.env.AAC_E2E_SKIP_GUARD === '1') {
    console.log('[prod-guard] skipped (AAC_E2E_SKIP_GUARD=1)');
    return;
  }

  // config.configFile is the absolute path to playwright.config.ts, which
  // lives at the frontend project root. Fall back to the cwd (where the e2e
  // scripts are normally run) if it is ever absent.
  const frontendRoot = path.resolve(
    config.configFile ? path.dirname(config.configFile) : process.cwd(),
  );
  const baseURL = resolveBaseUrl();

  const freshness = checkDistFreshness(frontendRoot);
  if (!freshness.ok) {
    throw new Error(`[prod-guard] ${freshness.message}`);
  }
  console.log(`[prod-guard] ${freshness.message}`);

  const server = await checkProductionServer(baseURL, frontendRoot);
  if (!server.ok) {
    throw new Error(`[prod-guard] ${server.message}`);
  }
  console.log(`[prod-guard] ${server.message}`);
}
