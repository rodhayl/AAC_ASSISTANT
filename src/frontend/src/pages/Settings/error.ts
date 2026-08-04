export function extractErrorMessage(err: unknown, defaultMsg: string): string {
  const errWithResponse = err as { response?: { data?: { detail?: unknown } } };
  const detail = errWithResponse?.response?.data?.detail;

  if (typeof detail === 'string') {
    return detail;
  }

  if (Array.isArray(detail)) {
    return detail
      .map((entry: unknown) => {
        if (
          entry &&
          typeof entry === 'object' &&
          'msg' in entry &&
          typeof (entry as { msg?: unknown }).msg === 'string'
        ) {
          return (entry as { msg: string }).msg;
        }
        return JSON.stringify(entry);
      })
      .join(', ');
  }

  if (typeof detail === 'object' && detail !== null) {
    return JSON.stringify(detail);
  }

  return defaultMsg;
}
