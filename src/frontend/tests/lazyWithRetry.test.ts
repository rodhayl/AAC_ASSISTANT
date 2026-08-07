import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';

import { __lazyWithRetryForTests, loadWithRetry } from '../src/lib/lazyWithRetry';

describe('lazyWithRetry', () => {
  const reloadSpy = vi.fn();

  beforeEach(() => {
    window.sessionStorage.clear();
    reloadSpy.mockClear();
    __lazyWithRetryForTests.setReloadPage(reloadSpy);
  });

  afterEach(() => {
    window.sessionStorage.clear();
    __lazyWithRetryForTests.resetReloadPage();
  });

  it('detects stale chunk loading errors', () => {
    expect(
      __lazyWithRetryForTests.isChunkLoadError(
        new TypeError('Failed to fetch dynamically imported module'),
      ),
    ).toBe(true);
    expect(
      __lazyWithRetryForTests.isChunkLoadError(
        new Error('ChunkLoadError: Loading chunk 7 failed.'),
      ),
    ).toBe(true);
    expect(__lazyWithRetryForTests.isChunkLoadError(new Error('ordinary render failure'))).toBe(false);
  });

  it('reloads once on the first stale chunk failure', async () => {
    void loadWithRetry(
      () => Promise.reject(new TypeError('Failed to fetch dynamically imported module')),
      'boards',
    );
    await Promise.resolve();
    expect(window.sessionStorage.getItem('aac-lazy-retry:boards')).toBe('1');
    expect(reloadSpy).toHaveBeenCalledTimes(1);
  });

  it('does not reload and rethrows when the chunk failure happens offline', async () => {
    const originalOnLine = Object.getOwnPropertyDescriptor(window.navigator, 'onLine');
    Object.defineProperty(window.navigator, 'onLine', {
      configurable: true,
      value: false,
    });

    try {
      await expect(
        loadWithRetry(
          () => Promise.reject(new TypeError('Failed to fetch dynamically imported module')),
          'boards',
        ),
      ).rejects.toThrow('Failed to fetch dynamically imported module');
      expect(reloadSpy).not.toHaveBeenCalled();
      expect(window.sessionStorage.getItem('aac-lazy-retry:boards')).toBeNull();
    } finally {
      if (originalOnLine) {
        Object.defineProperty(window.navigator, 'onLine', originalOnLine);
      }
    }
  });

  it('rethrows after the retry was already used', async () => {
    window.sessionStorage.setItem('aac-lazy-retry:boards', '1');

    await expect(
      loadWithRetry(
        () => Promise.reject(new TypeError('Failed to fetch dynamically imported module')),
        'boards',
      ),
    ).rejects.toThrow(
      'Failed to fetch dynamically imported module',
    );
    expect(reloadSpy).not.toHaveBeenCalled();
  });
});
