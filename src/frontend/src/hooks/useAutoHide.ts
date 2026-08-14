import { useEffect, useRef } from 'react';

/**
 * Clears a transient value (e.g. a success message) after `delayMs` once it
 * becomes truthy. `clear` is kept in a ref (updated in an effect) so unrelated
 * re-renders do not restart the timer.
 */
export function useAutoHide(value: unknown, clear: () => void, delayMs = 3000): void {
  const clearRef = useRef(clear);

  useEffect(() => {
    clearRef.current = clear;
  });

  useEffect(() => {
    if (!value) return;
    const timeoutId = setTimeout(() => clearRef.current(), delayMs);
    return () => clearTimeout(timeoutId);
  }, [value, delayMs]);
}
