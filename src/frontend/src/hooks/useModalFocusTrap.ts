import { useEffect, useRef, type RefObject } from 'react';

const FOCUSABLE_SELECTOR =
  'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [href], [tabindex]:not([tabindex="-1"])';

// A module-level stack lets multiple consumers coexist safely. Only the
// topmost open modal handles document keyboard events and owns body scroll
// locking/focus restoration.
const openModalIds: symbol[] = [];
let previousBodyOverflow: string | null = null;

/**
 * Provides the keyboard and focus behavior shared by application modals.
 *
 * The dialog element must be rendered before `isOpen` becomes true. When the
 * modal opens, focus moves to its first focusable control; Escape calls
 * `onClose`; Tab and Shift+Tab wrap within the dialog; and the previously
 * focused element is restored when the modal closes or unmounts.
 */
export function useModalFocusTrap<T extends HTMLElement>(
  dialogRef: RefObject<T | null>,
  isOpen: boolean,
  onClose: () => void,
): void {
  const onCloseRef = useRef(onClose);
  const modalIdRef = useRef<symbol | null>(null);

  // Keep the callback current without restarting the focus-trap effect on
  // every parent render.
  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!isOpen) return;

    const dialog = dialogRef.current;
    if (!dialog) return;

    const modalId = Symbol('modal-focus-trap');
    modalIdRef.current = modalId;
    const previouslyFocused =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const wasFirstModal = openModalIds.length === 0;
    openModalIds.push(modalId);

    const getFocusable = () =>
      Array.from(dialog.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
    const originalTabIndex = dialog.getAttribute('tabindex');
    const initialFocusable = getFocusable();
    // A future/minimal dialog may contain no controls. Make the dialog itself
    // a programmatic focus target so focus never remains behind the modal.
    if (initialFocusable.length === 0 && originalTabIndex === null) {
      dialog.setAttribute('tabindex', '-1');
    }
    const getFocusTargets = () => {
      const focusables = getFocusable();
      return focusables.length > 0 ? focusables : [dialog];
    };

    // Only the newly opened topmost modal moves focus and owns scroll lock.
    if (wasFirstModal || openModalIds[openModalIds.length - 1] === modalId) {
      getFocusTargets()[0]?.focus();
    }
    if (wasFirstModal) {
      previousBodyOverflow = document.body.style.overflow;
      document.body.style.overflow = 'hidden';
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (openModalIds[openModalIds.length - 1] !== modalId) return;
      if (event.key === 'Escape') {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== 'Tab') return;

      const focusTargets = getFocusTargets();
      const current = document.activeElement;
      const index = focusTargets.indexOf(current as HTMLElement);
      if (event.shiftKey) {
        if (index <= 0) {
          event.preventDefault();
          focusTargets[focusTargets.length - 1].focus();
        }
      } else if (index === -1 || index === focusTargets.length - 1) {
        event.preventDefault();
        focusTargets[0].focus();
      }
    };

    document.addEventListener('keydown', handleKeyDown);

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      const stackIndex = openModalIds.indexOf(modalId);
      const wasTopmost = stackIndex === openModalIds.length - 1;
      if (stackIndex >= 0) openModalIds.splice(stackIndex, 1);

      // Restore body state only after the last modal closes. A nested modal's
      // cleanup must not unlock the page while its parent remains open.
      if (openModalIds.length === 0) {
        document.body.style.overflow = previousBodyOverflow ?? '';
        previousBodyOverflow = null;
      }
      if (originalTabIndex === null) {
        dialog.removeAttribute('tabindex');
      } else {
        dialog.setAttribute('tabindex', originalTabIndex);
      }

      // Restore focus only for the modal that was actually on top when it
      // closed; nested cleanup should not steal focus from its parent.
      if (wasTopmost && previouslyFocused && document.contains(previouslyFocused)) {
        previouslyFocused.focus();
      }
      if (modalIdRef.current === modalId) modalIdRef.current = null;
    };
  }, [dialogRef, isOpen]);
}
