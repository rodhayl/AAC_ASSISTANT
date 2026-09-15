/**
 * Tier I e2e hygiene guards (PROMPT_5).
 *
 * H12: playwright.config.ts must not install a project-wide storageState —
 * every spec opts into the role it exercises, or explicitly into no session.
 * A global default ran role-gated specs as one user, hiding privilege bugs.
 *
 * H17: the dist-freshness guard must ignore test-only files (Vite never
 * bundles them), so touching a spec cannot make the build look stale.
 *
 * prediction-tiers.spec.ts mirrors the prediction `source` values emitted by
 * PredictionService; the guard below fails when a new tier adds a source the
 * spec would reject as unknown.
 */

import { readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const frontendRoot = path.resolve(__dirname, '..');
const e2eDir = path.join(frontendRoot, 'e2e');

describe('playwright project configuration', () => {
  const configSource = readFileSync(
    path.join(frontendRoot, 'playwright.config.ts'),
    'utf8',
  );
  // Comments explain the rule and must not count as a configuration entry.
  const configCode = configSource
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*\/\/.*$/gm, '');

  it('installs no project-wide storageState', () => {
    // The project `use` blocks are the only place a global role could hide.
    expect(configCode).not.toMatch(/storageState\s*:/);
  });

  it('requires every spec to declare its session explicitly', () => {
    const specs = readdirSync(e2eDir).filter((name) => name.endsWith('.spec.ts'));
    const undeclared = specs.filter((name) => {
      const source = readFileSync(path.join(e2eDir, name), 'utf8');
      return !source.includes('storageState');
    });
    expect(undeclared).toEqual([]);
  });
});

describe('prediction source allow-list', () => {
  it('covers every source the prediction service can emit', () => {
    const service = readFileSync(
      path.resolve(
        frontendRoot,
        '..',
        '..',
        'src',
        'aac_app',
        'services',
        'prediction_service.py',
      ),
      'utf8',
    );
    const emitted = new Set(
      [...service.matchAll(/source="([a-z_]+)"/g)].map((match) => match[1]),
    );
    expect(emitted.size).toBeGreaterThan(0);

    const spec = readFileSync(path.join(e2eDir, 'prediction-tiers.spec.ts'), 'utf8');
    const block = spec.match(/const KNOWN_SOURCES = new Set\(\[([\s\S]*?)\]\)/)?.[1] ?? '';
    const allowed = new Set([...block.matchAll(/'([a-z_]+)'/g)].map((match) => match[1]));

    expect([...emitted].filter((source) => !allowed.has(source))).toEqual([]);
  });
});

describe('dist freshness guard', () => {
  it('ignores test-only files and still catches real source edits', async () => {
    const { checkDistFreshness } = (await import(
      path.join(e2eDir, 'prod-guard.mjs')
    )) as {
      checkDistFreshness: (root: string) => { ok: boolean };
    };

    const { mkdirSync, writeFileSync, utimesSync, rmSync } = await import(
      'node:fs'
    );
    const os = await import('node:os');
    const root = path.join(
      os.tmpdir(),
      `guard-vitest-${process.pid}-${Date.now()}`,
    );
    mkdirSync(path.join(root, 'dist'), { recursive: true });
    mkdirSync(path.join(root, 'src'), { recursive: true });
    const now = Date.now() / 1000;
    const old = now - 500;
    writeFileSync(path.join(root, 'dist', 'index.html'), 'x');
    utimesSync(path.join(root, 'dist', 'index.html'), old, old);
    writeFileSync(path.join(root, 'src', 'App.tsx'), 'x');
    utimesSync(path.join(root, 'src', 'App.tsx'), old, old);

    try {
      writeFileSync(path.join(root, 'src', 'App.test.tsx'), 'x');
      utimesSync(path.join(root, 'src', 'App.test.tsx'), now, now);
      expect(checkDistFreshness(root).ok).toBe(true);

      writeFileSync(path.join(root, 'src', 'App.tsx'), 'changed');
      utimesSync(path.join(root, 'src', 'App.tsx'), now, now);
      expect(checkDistFreshness(root).ok).toBe(false);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });
});
