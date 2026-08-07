#!/usr/bin/env node
/**
 * Bundle-size budget guard (CI-friendly).
 *
 *   node scripts/check-bundle-size.mjs [--js-kb 450] [--css-kb 150]
 *
 * Fails when any emitted JavaScript or CSS asset in dist/assets/ exceeds the
 * configured budget. Budgets are documented ceilings, not targets:
 *
 *   - JS: 450 kB minified (largest chunk was ~355 kB, gzip ~113 kB)
 *   - CSS: 150 kB minified (largest stylesheet was ~99 kB, gzip ~15 kB)
 *
 * A regression that balloons a single chunk past the ceiling fails the build
 * early instead of silently shipping a slow-loading SPA.
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const assetsDir = path.join(frontendRoot, 'dist', 'assets');

const args = process.argv.slice(2);
function argValue(name, fallback) {
  const index = args.indexOf(name);
  return index >= 0 && args[index + 1] ? Number(args[index + 1]) : fallback;
}

const MAX_JS_KB = argValue('--js-kb', 450);
const MAX_CSS_KB = argValue('--css-kb', 150);

if (!fs.existsSync(assetsDir)) {
  console.error('[bundle-size] dist/assets not found; run the build first.');
  process.exit(1);
}

const failures = [];
let largestJs = 0;
let largestCss = 0;

for (const name of fs.readdirSync(assetsDir)) {
  const full = path.join(assetsDir, name);
  if (!fs.statSync(full).isFile()) continue;

  const sizeKb = fs.statSync(full).size / 1024;
  if (name.endsWith('.js')) {
    largestJs = Math.max(largestJs, sizeKb);
    if (sizeKb > MAX_JS_KB) {
      failures.push(`${name}: ${sizeKb.toFixed(1)} kB exceeds JS budget ${MAX_JS_KB} kB`);
    }
  } else if (name.endsWith('.css')) {
    largestCss = Math.max(largestCss, sizeKb);
    if (sizeKb > MAX_CSS_KB) {
      failures.push(`${name}: ${sizeKb.toFixed(1)} kB exceeds CSS budget ${MAX_CSS_KB} kB`);
    }
  }
}

console.log(
  `[bundle-size] largest JS ${largestJs.toFixed(1)} kB (budget ${MAX_JS_KB} kB), ` +
    `largest CSS ${largestCss.toFixed(1)} kB (budget ${MAX_CSS_KB} kB)`,
);

if (failures.length > 0) {
  console.error('[bundle-size] budget exceeded:');
  for (const failure of failures) console.error(`  - ${failure}`);
  process.exit(1);
}

process.exit(0);
