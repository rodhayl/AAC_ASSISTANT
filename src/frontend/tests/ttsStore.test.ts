import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const LOCAL_VOICE_KEY = 'aac_local_voice';

describe('ttsStore', () => {
  beforeEach(() => {
    localStorage.removeItem(LOCAL_VOICE_KEY);
    vi.resetModules();
  });

  afterEach(() => {
    localStorage.removeItem(LOCAL_VOICE_KEY);
  });

  it('reads the stored local voice on creation', async () => {
    localStorage.setItem(LOCAL_VOICE_KEY, 'af_heart');

    const { useTTSStore } = await import('../src/store/ttsStore');

    expect(useTTSStore.getState().localVoice).toBe('af_heart');
  });

  it('selects a browser voice', async () => {
    const { useTTSStore } = await import('../src/store/ttsStore');

    useTTSStore.getState().setSelectedVoice('Google español');

    expect(useTTSStore.getState().selectedVoice).toBe('Google español');
  });

  it('persists the selected local voice', async () => {
    const { useTTSStore } = await import('../src/store/ttsStore');

    useTTSStore.getState().setLocalVoice('am_michael');

    expect(localStorage.getItem(LOCAL_VOICE_KEY)).toBe('am_michael');
    expect(useTTSStore.getState().localVoice).toBe('am_michael');
  });

  it('falls back to the default voice without storage access', async () => {
    const getItem = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('storage blocked');
    });
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('storage blocked');
    });

    const { useTTSStore } = await import('../src/store/ttsStore');

    expect(useTTSStore.getState().localVoice).toBe('default');

    expect(() => useTTSStore.getState().setLocalVoice('bf_emma')).not.toThrow();
    expect(useTTSStore.getState().localVoice).toBe('bf_emma');

    getItem.mockRestore();
    setItem.mockRestore();
  });

  it('defaults to the auto voice when localStorage is unavailable', async () => {
    const originalLocalStorage = globalThis.localStorage;
    Object.defineProperty(globalThis, 'localStorage', {
      configurable: true,
      value: undefined,
    });
    vi.resetModules();

    try {
      const { useTTSStore } = await import('../src/store/ttsStore');
      expect(useTTSStore.getState().localVoice).toBe('default');
    } finally {
      Object.defineProperty(globalThis, 'localStorage', {
        configurable: true,
        value: originalLocalStorage,
      });
    }
  });
});
