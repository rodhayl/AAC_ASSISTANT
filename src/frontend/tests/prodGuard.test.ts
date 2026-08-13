import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { mkdirSync, mkdtempSync, rmSync, utimesSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import {
  checkDistFreshness,
  checkProductionServer,
  resolveBaseUrl,
} from '../e2e/prod-guard.mjs';

/** Create a temp frontend-root fixture; returns absolute path. */
function makeRoot(): string {
  return mkdtempSync(path.join(tmpdir(), 'prod-guard-'));
}

/** Write a file at root-relative path with a specific mtime. */
function touch(root: string, rel: string, mtime: Date): string {
  const full = path.join(root, rel);
  mkdirSync(path.dirname(full), { recursive: true });
  writeFileSync(full, 'content');
  utimesSync(full, mtime, mtime);
  return full;
}

const NOW = () => new Date();
const OLD = () => new Date(Date.now() - 60_000);

type FetchResult = { ok: boolean; status?: number; text: () => Promise<string> };
type FakeFetch = (result: FetchResult | Error) => typeof fetch;

const fakeFetch: FakeFetch = (result) =>
  (async () => {
    if (result instanceof Error) throw result;
    return result;
  }) as unknown as typeof fetch;

const PROD_HTML = (asset: string) =>
  `<!doctype html><html><head><script src="${asset}"></script><link href="/assets/index-abc.css"></head></html>`;

describe('prod-guard: resolveBaseUrl', () => {
  it('defaults to the backend URL', () => {
    expect(resolveBaseUrl({})).toBe('http://127.0.0.1:8086');
  });

  it('honours PLAYWRIGHT_BASE_URL', () => {
    expect(resolveBaseUrl({ PLAYWRIGHT_BASE_URL: 'http://localhost:9999' })).toBe(
      'http://localhost:9999',
    );
  });
});

describe('prod-guard: checkDistFreshness', () => {
  let root: string;

  beforeEach(() => {
    root = makeRoot();
  });

  afterEach(() => {
    rmSync(root, { recursive: true, force: true });
  });

  it('fails when dist is missing entirely', () => {
    const result = checkDistFreshness(root);
    expect(result.ok).toBe(false);
    expect(result.message).toContain('npm run build');
  });

  it('fails when dist is older than a build input', () => {
    touch(root, 'dist/index.html', OLD());
    touch(root, 'src/App.tsx', NOW());
    const result = checkDistFreshness(root);
    expect(result.ok).toBe(false);
    expect(result.message).toContain('dist is stale');
    expect(result.message).toContain('npm run build');
  });

  it('passes when dist is newer than all build inputs', () => {
    touch(root, 'dist/index.html', NOW());
    touch(root, 'src/App.tsx', OLD());
    touch(root, 'public/vite.svg', OLD());
    touch(root, 'index.html', OLD());
    touch(root, 'vite.config.ts', OLD());
    const result = checkDistFreshness(root);
    expect(result.ok).toBe(true);
  });

  it('ignores e2e and test files when deciding freshness', () => {
    // dist is stale, but only e2e/tests changed since — no rebuild needed.
    touch(root, 'dist/index.html', OLD());
    touch(root, 'e2e/maintenance.spec.ts', NOW());
    touch(root, 'tests/foo.test.ts', NOW());
    const result = checkDistFreshness(root);
    expect(result.ok).toBe(true);
  });

  it('allows a build that is as new as the newest input (grace period)', () => {
    touch(root, 'dist/index.html', NOW());
    touch(root, 'src/App.tsx', new Date(Date.now() + 500));
    const result = checkDistFreshness(root);
    expect(result.ok).toBe(true);
  });
});

describe('prod-guard: checkProductionServer', () => {
  let root: string;

  beforeEach(() => {
    root = makeRoot();
  });

  afterEach(() => {
    rmSync(root, { recursive: true, force: true });
  });

  it('fails with a clear message when the server is unreachable', async () => {
    const result = await checkProductionServer(
      'http://127.0.0.1:8086',
      root,
      fakeFetch(new Error('connect ECONNREFUSED')),
    );
    expect(result.ok).toBe(false);
    expect(result.message).toContain('Cannot reach a server');
  });

  it('fails with a clear message when the server returns a non-200 status', async () => {
    const result = await checkProductionServer(
      'http://127.0.0.1:8086',
      root,
      fakeFetch({ ok: false, status: 503, text: async () => 'Service Unavailable' }),
    );
    expect(result.ok).toBe(false);
    expect(result.message).toContain('HTTP 503');
  });

  it('fails when the served HTML is the Vite dev server', async () => {
    const viteHtml = `<!doctype html><html><head>
      <script type="module" src="/@vite/client"></script>
      <script type="module" src="/src/main.tsx"></script>
    </head></html>`;
    const result = await checkProductionServer(
      'http://127.0.0.1:8086',
      root,
      fakeFetch({ ok: true, text: async () => viteHtml }),
    );
    expect(result.ok).toBe(false);
    expect(result.message).toContain('Vite dev server detected');
  });

  it('fails when the served HTML references no /assets at all', async () => {
    const result = await checkProductionServer(
      'http://127.0.0.1:8086',
      root,
      fakeFetch({ ok: true, text: async () => '<html><body>hello</body></html>' }),
    );
    expect(result.ok).toBe(false);
    expect(result.message).toContain('No /assets/ references');
  });

  it('fails on localhost when a referenced asset is missing from dist', async () => {
    const result = await checkProductionServer(
      'http://127.0.0.1:8086',
      root,
      fakeFetch({ ok: true, text: async () => PROD_HTML('/assets/index-abc.js') }),
    );
    expect(result.ok).toBe(false);
    expect(result.message).toContain('missing from dist');
  });

  it('passes when the production SPA is served and its assets exist locally', async () => {
    touch(root, 'dist/assets/index-abc.js', NOW());
    touch(root, 'dist/assets/index-abc.css', NOW());
    const result = await checkProductionServer(
      'http://127.0.0.1:8086',
      root,
      fakeFetch({ ok: true, text: async () => PROD_HTML('/assets/index-abc.js') }),
    );
    expect(result.ok).toBe(true);
  });

  it('does not require local asset presence for non-localhost targets', async () => {
    const result = await checkProductionServer(
      'http://deploy.example.com:8086',
      root,
      fakeFetch({ ok: true, text: async () => PROD_HTML('/assets/index-remote.js') }),
    );
    expect(result.ok).toBe(true);
  });
});
