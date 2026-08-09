import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { loadWithRetry } from '../src/lib/lazyWithRetry';

describe('lazyWithRetry', () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  afterEach(() => {
    window.sessionStorage.clear();
  });

  it('clears the retry marker after a successful import', async () => {
    window.sessionStorage.setItem('aac-lazy-retry:boards', '1');
    const module = await loadWithRetry(() => Promise.resolve({ default: () => null }), 'boards');
    expect(module.default).toBeTypeOf('function');
    expect(window.sessionStorage.getItem('aac-lazy-retry:boards')).toBeNull();
  });

  it('rethrows ordinary importer failures', async () => {
    await expect(
      loadWithRetry(() => Promise.reject(new Error('ordinary render failure')), 'boards'),
    ).rejects.toThrow('ordinary render failure');
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
  });
});
