import { describe, expect, it } from 'vitest';
import { normalizeUILanguage } from '../src/lib/utils';

describe('normalizeUILanguage', () => {
  it('maps legacy short codes to the regional select options', () => {
    expect(normalizeUILanguage('en')).toBe('en-US');
    expect(normalizeUILanguage('es')).toBe('es-ES');
  });

  it('keeps regional codes unchanged', () => {
    expect(normalizeUILanguage('en-US')).toBe('en-US');
    expect(normalizeUILanguage('es-ES')).toBe('es-ES');
  });

  it('handles case and whitespace variants', () => {
    expect(normalizeUILanguage('EN')).toBe('en-US');
    expect(normalizeUILanguage(' Es ')).toBe('es-ES');
  });

  it('falls back to es-ES for empty or unknown values', () => {
    expect(normalizeUILanguage(null)).toBe('es-ES');
    expect(normalizeUILanguage(undefined)).toBe('es-ES');
    expect(normalizeUILanguage('')).toBe('es-ES');
    expect(normalizeUILanguage('fr')).toBe('fr');
  });
});
