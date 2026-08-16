import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { readStoredUseLocalTTS, useTTSStore } from '../src/store/ttsStore';

describe('ttsStore local TTS toggle persistence', () => {
  beforeEach(() => {
    localStorage.clear();
    useTTSStore.setState({ useLocalTTS: false, localTTSAvailable: false });
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('reads null when the user has never set the toggle', () => {
    expect(readStoredUseLocalTTS()).toBeNull();
  });

  it('persists the toggle and re-reads it', () => {
    useTTSStore.getState().setUseLocalTTS(true);
    expect(localStorage.getItem('aac_use_local_tts')).toBe('1');
    expect(readStoredUseLocalTTS()).toBe(true);

    useTTSStore.getState().setUseLocalTTS(false);
    expect(localStorage.getItem('aac_use_local_tts')).toBe('0');
    expect(readStoredUseLocalTTS()).toBe(false);
  });

  it('keeps an explicit opt-out as false so capability refresh does not re-enable it', () => {
    localStorage.setItem('aac_use_local_tts', '0');
    useTTSStore.getState().setLocalTTSAvailable(true);
    // The runtime toggle must remain off until the user opts back in.
    expect(useTTSStore.getState().useLocalTTS).toBe(false);
    expect(readStoredUseLocalTTS()).toBe(false);
  });
});
