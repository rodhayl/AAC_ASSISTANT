import { describe, expect, it } from 'vitest';

import {
  errorMessageOf,
  errorPayloadOf,
  httpStatusOf,
  isAbortError,
  isCancelledError,
  isOfflineError,
} from '../src/lib/httpErrors';

describe('httpStatusOf', () => {
  it('reads an axios-style response status', () => {
    expect(httpStatusOf({ response: { status: 404 } })).toBe(404);
    expect(httpStatusOf({ response: { status: 200, data: {} } })).toBe(200);
  });

  it('returns null for non-numeric or missing status', () => {
    expect(httpStatusOf({ response: { status: '404' } })).toBeNull();
    expect(httpStatusOf({ response: {} })).toBeNull();
    expect(httpStatusOf({})).toBeNull();
    expect(httpStatusOf(null)).toBeNull();
    expect(httpStatusOf('boom')).toBeNull();
  });
});

describe('errorPayloadOf', () => {
  it('normalizes the axios error response payload', () => {
    const payload = errorPayloadOf({
      response: { status: 400, data: { detail: 'bad input' } },
    });
    expect(payload).toEqual({ status: 400, data: { detail: 'bad input' } });
  });

  it('reads only known data keys', () => {
    const payload = errorPayloadOf({
      response: { data: { detail: 'x', other: 'ignored' } },
    });
    expect(payload).toEqual({ data: { detail: 'x' } });
  });

  it('returns null for non-object errors', () => {
    expect(errorPayloadOf(undefined)).toBeNull();
    expect(errorPayloadOf('offline')).toBeNull();
    expect(errorPayloadOf({})).toBeNull();
  });
});

describe('errorMessageOf', () => {
  it('returns string messages only', () => {
    expect(errorMessageOf({ message: 'offline' })).toBe('offline');
    expect(errorMessageOf({ message: 7 })).toBeNull();
    expect(errorMessageOf({})).toBeNull();
    expect(errorMessageOf(null)).toBeNull();
  });
});

describe('isOfflineError', () => {
  it('recognizes the app-level offline markers', () => {
    expect(isOfflineError({ code: 'ERR_OFFLINE' })).toBe(true);
    expect(isOfflineError({ message: 'offline' })).toBe(true);
    expect(isOfflineError({ code: 'ERR_OFFLINE', message: 'offline' })).toBe(true);
  });

  it('rejects network errors that are not the offline marker', () => {
    expect(isOfflineError({ code: 'ERR_NETWORK' })).toBe(false);
    expect(isOfflineError({ code: 'ERR_BAD_REQUEST' })).toBe(false);
    expect(isOfflineError(null)).toBe(false);
    expect(isOfflineError('offline')).toBe(false);
  });
});

describe('isCancelledError', () => {
  it('recognizes axios cancellations', () => {
    expect(isCancelledError({ code: 'ERR_CANCELED' })).toBe(true);
    expect(isCancelledError({ name: 'CanceledError' })).toBe(true);
    expect(isCancelledError({ code: 'ERR_CANCELED', name: 'CanceledError' })).toBe(true);
  });

  it('rejects real request failures', () => {
    expect(isCancelledError({ code: 'ERR_BAD_RESPONSE' })).toBe(false);
    expect(isCancelledError({ name: 'AbortError' })).toBe(false);
    expect(isCancelledError({})).toBe(false);
  });
});

describe('isAbortError', () => {
  it('recognizes DOM abort errors', () => {
    expect(isAbortError({ name: 'AbortError' })).toBe(true);
  });

  it('rejects non-abort errors', () => {
    expect(isAbortError({ name: 'CanceledError' })).toBe(false);
    expect(isAbortError({ name: 'TypeError' })).toBe(false);
    expect(isAbortError(null)).toBe(false);
  });
});
