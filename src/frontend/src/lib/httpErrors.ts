/**
 * Structural error introspection helpers.
 *
 * Error objects cross the axios boundary as `unknown`, and casting them
 * (`error as { code?: ... }`) hides shape drift. These helpers narrow with
 * `in` checks (same model as `isDuplicateResponse` in learningTopics.ts) so
 * callers read error fields without casts and without crashing on exotic
 * shapes. Semantics mirror what each call site historically checked:
 *
 * - offline   : code `ERR_OFFLINE` or message `offline` (api.ts rejects)
 * - cancelled : axios cancel (code `ERR_CANCELED` / name `CanceledError`)
 * - aborted   : DOM `AbortError` (fetch/EventSource teardown)
 */

export type ErrorPayload = {
  status?: number;
  data?: { detail?: unknown; error?: unknown; message?: unknown };
};

function isObject(value: unknown): value is object {
  return typeof value === 'object' && value !== null;
}

/** HTTP status carried by an axios-style error, or null. */
export function httpStatusOf(error: unknown): number | null {
  if (!isObject(error) || !('response' in error)) return null;
  const { response } = error;
  if (!isObject(response) || !('status' in response)) return null;
  const { status } = response;
  return typeof status === 'number' ? status : null;
}

/** Normalized axios-style payload: response.status and response.data.*. */
export function errorPayloadOf(error: unknown): ErrorPayload | null {
  if (!isObject(error) || !('response' in error)) return null;
  const { response } = error;
  if (!isObject(response)) return null;

  const payload: ErrorPayload = {};
  if ('status' in response && typeof response.status === 'number') {
    payload.status = response.status;
  }
  if ('data' in response && isObject(response.data)) {
    const data = response.data;
    const normalized: NonNullable<ErrorPayload['data']> = {};
    if ('detail' in data) normalized.detail = data.detail;
    if ('error' in data) normalized.error = data.error;
    if ('message' in data) normalized.message = data.message;
    payload.data = normalized;
  }
  return payload;
}

/** The `message` field when it is a string, else null. */
export function errorMessageOf(error: unknown): string | null {
  if (!isObject(error) || !('message' in error)) return null;
  const { message } = error;
  return typeof message === 'string' ? message : null;
}

/** Requests the app itself rejects while offline ({ code: 'ERR_OFFLINE' }). */
export function isOfflineError(error: unknown): boolean {
  if (!isObject(error)) return false;
  const code = 'code' in error ? error.code : undefined;
  if (code === 'ERR_OFFLINE') return true;
  return errorMessageOf(error) === 'offline';
}

/** Axios request cancellation (abort controller / timeout), not a failure. */
export function isCancelledError(error: unknown): boolean {
  if (!isObject(error)) return false;
  const code = 'code' in error ? error.code : undefined;
  if (code === 'ERR_CANCELED') return true;
  const name = 'name' in error ? error.name : undefined;
  return name === 'CanceledError';
}

/** DOM AbortError raised by fetch/EventSource teardown. */
export function isAbortError(error: unknown): boolean {
  if (!isObject(error)) return false;
  const name = 'name' in error ? error.name : undefined;
  return name === 'AbortError';
}
