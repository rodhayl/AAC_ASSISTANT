import { useEffect } from 'react'

const DEFAULT_TITLE = 'AAC Assistant'

/**
 * Sets the browser-tab title while the calling page is mounted so several
 * open tabs (and screen readers / browser history) can tell pages apart.
 * Restores the default title on unmount.
 */
export function usePageTitle(title?: string) {
  useEffect(() => {
    if (title) {
      document.title = `${title} · AAC Assistant`
    }
    return () => {
      document.title = DEFAULT_TITLE
    }
  }, [title])
}
