// Regression coverage for the F02 offline-persistence sanitizer.
//
// The production sanitizer must reject (return null for) sensitive operations
// and secret-bearing payloads so they never reach sessionStorage, and it must
// strip secret-bearing headers/params from anything it does allow. These
// tests import the REAL module (no mocks) because a mocked sanitizer is what
// allowed the original defect to ship.

import { beforeEach, describe, expect, it } from 'vitest';
import {
  removeAuthorizationHeader,
  sanitizeOfflineConfig,
} from '../src/lib/offlinePersistence';

describe('offline persistence sanitizer (F02)', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it('rejects a password-reset request outright', () => {
    const result = sanitizeOfflineConfig({
      url: '/users/3/reset-password',
      method: 'post',
      data: { new_password: 'SuperSecret123!' },
      headers: { Authorization: 'Bearer token' },
    });
    expect(result).toBeNull();
  });

  it('rejects privileged account creation', () => {
    const result = sanitizeOfflineConfig({
      url: '/auth/admin/create-user',
      method: 'post',
      data: { username: 'admin2', password: 'AdminSecret123!' },
    });
    expect(result).toBeNull();
  });

  it('rejects provider settings updates carrying an API key', () => {
    const result = sanitizeOfflineConfig({
      url: '/settings/ai',
      method: 'put',
      data: { ai_provider: 'groq', groq_api_key: 'gsk_synthtic123' },
    });
    expect(result).toBeNull();
  });

  it('rejects allowlisted URLs whose payload carries a secret field', () => {
    const result = sanitizeOfflineConfig({
      url: '/boards/1',
      method: 'post',
      data: { name: 'Board', password: 'oops' },
    });
    expect(result).toBeNull();
  });

  it('rejects non-allowlisted ordinary endpoints', () => {
    expect(sanitizeOfflineConfig({
      url: '/learning/1/answer',
      method: 'post',
      data: { answer: 'a' },
    })).toBeNull();
    expect(sanitizeOfflineConfig({
      url: '/auth/token',
      method: 'post',
      data: { username: 'u', password: 'p' },
    })).toBeNull();
    expect(sanitizeOfflineConfig({
      url: '/users/me',
      method: 'put',
      data: { display_name: 'x' },
    })).toBeNull();
  });

  it('rejects a request whose params carry a secret rather than persisting it', () => {
    const result = sanitizeOfflineConfig({
      url: '/boards/1',
      method: 'post',
      data: { name: 'Fine' },
      params: { api_key: 'leak', keep: 'yes' },
    });
    // Rejection (not stripping) is the intended contract: a request whose
    // routing itself needs a secret must never enter the offline queue.
    expect(result).toBeNull();
  });

  it('strips Authorization and secret-bearing headers from an allowed mutation', () => {
    const result = sanitizeOfflineConfig({
      url: '/boards/1',
      method: 'post',
      data: { name: 'Fine' },
      headers: {
        Authorization: 'Bearer secret-token',
        'X-Api-Key': 'leak',
        'Content-Type': 'application/json',
      },
    });
    expect(result).not.toBeNull();
    const headers = result?.headers as Record<string, string>;
    expect(headers['Content-Type']).toBe('application/json');
    expect(JSON.stringify(headers)).not.toContain('secret-token');
    expect(JSON.stringify(headers)).not.toContain('leak');
  });

  it('keeps a supported board edit for offline replay', () => {
    const result = sanitizeOfflineConfig({
      url: '/boards/1',
      method: 'put',
      data: { name: 'Updated board name' },
      headers: { Authorization: 'Bearer token' },
    });
    expect(result).toEqual({
      method: 'put',
      url: '/boards/1',
      baseURL: undefined,
      params: undefined,
      data: { name: 'Updated board name' },
      headers: {},
    });
  });

  it('does not retain an Authorization header on hydration', () => {
    const sanitized = removeAuthorizationHeader({
      url: '/boards/1',
      method: 'post',
      data: { name: 'Fine' },
      headers: { Authorization: 'Bearer stale', 'Accept-Language': 'es' },
    });
    expect(JSON.stringify(sanitized.headers ?? {})).not.toContain('stale');
  });
});
