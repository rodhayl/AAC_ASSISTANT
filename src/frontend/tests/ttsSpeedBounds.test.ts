import { describe, expect, it } from 'vitest';

import {
  LOCAL_SPEED_MAX,
  LOCAL_SPEED_MIN,
  clampLocalSpeed,
} from '../src/store/ttsStore';

describe('TTS local speed bounds (single frontend home)', () => {
  it('keeps the backend [0.5, 2.0] range', () => {
    expect(LOCAL_SPEED_MIN).toBe(0.5);
    expect(LOCAL_SPEED_MAX).toBe(2.0);
  });

  it('clamps inclusively at both endpoints', () => {
    expect(clampLocalSpeed(0)).toBe(0.5);
    expect(clampLocalSpeed(0.5)).toBe(0.5);
    expect(clampLocalSpeed(1.0)).toBe(1.0);
    expect(clampLocalSpeed(2.0)).toBe(2.0);
    expect(clampLocalSpeed(9)).toBe(2.0);
  });

  it('falls back to neutral for non-finite input', () => {
    expect(clampLocalSpeed(Number.NaN)).toBe(1.0);
    expect(clampLocalSpeed(Infinity)).toBe(1.0);
  });
});
