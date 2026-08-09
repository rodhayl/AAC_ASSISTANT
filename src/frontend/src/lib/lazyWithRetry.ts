import { lazy } from 'react';
import type { ComponentType } from 'react';

type ModuleWithDefault<Props extends object> = { default: ComponentType<Props> };

const RETRY_PREFIX = 'aac-lazy-retry:';

function isChunkLoadError(error: unknown): boolean {
  const message =
    error instanceof Error ? error.message : typeof error === 'string' ? error : '';
  const name = error instanceof Error ? error.name : '';
  const haystack = `${name} ${message}`.toLowerCase();

  return (
    haystack.includes('chunkloaderror') ||
    haystack.includes('failed to fetch dynamically imported module') ||
    haystack.includes('importing a module script failed') ||
    haystack.includes('failed to import')
  );
}

export function lazyWithRetry<Props extends object>(
  importer: () => Promise<ModuleWithDefault<Props>>,
  cacheKey: string,
) {
  return lazy(() => loadWithRetry(importer, cacheKey));
}

export async function loadWithRetry<Props extends object>(
  importer: () => Promise<ModuleWithDefault<Props>>,
  cacheKey: string,
): Promise<ModuleWithDefault<Props>> {
  try {
    const module = await importer();
    if (typeof window !== 'undefined') {
      window.sessionStorage.removeItem(`${RETRY_PREFIX}${cacheKey}`);
    }
    return module;
  } catch (error) {
    if (
      typeof window !== 'undefined' &&
      isChunkLoadError(error)
    ) {
      // Reloading while offline cannot fetch the missing chunk and only ends
      // in a browser-level error page. Let the error boundary surface instead.
      const offline = typeof navigator === 'undefined' || !navigator.onLine;
      const storageKey = `${RETRY_PREFIX}${cacheKey}`;
      const alreadyRetried = !offline && window.sessionStorage.getItem(storageKey) === '1';
      if (!alreadyRetried && !offline) {
        window.sessionStorage.setItem(storageKey, '1');
        window.location.reload();
        return new Promise<ModuleWithDefault<Props>>(() => {});
      }
    }
    throw error;
  }
}
