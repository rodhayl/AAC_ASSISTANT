import { createPortal } from 'react-dom';
import type { ReactNode } from 'react';

/**
 * Renders children into `document.body` so overlays escape ancestor elements
 * whose `backdrop-filter`/`filter`/`transform`/`overflow` would otherwise turn
 * `position: fixed` into a containing block (WebKit/Safari) or clip the overlay.
 *
 * Modal/overlay components must use this for their top-level `fixed inset-0`
 * wrapper; otherwise the overlay is positioned relative to the panel instead of
 * the viewport and the page underneath intercepts pointer events.
 */
export function Portal({ children }: { children: ReactNode }) {
  return createPortal(children, document.body);
}
