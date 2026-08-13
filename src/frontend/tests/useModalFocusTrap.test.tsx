import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useState, useRef } from 'react';
import { useModalFocusTrap } from '../src/hooks/useModalFocusTrap';

function TestModal({ onClose, label = '', empty = false }: { onClose: () => void; label?: string; empty?: boolean }) {
  const [open, setOpen] = useState(true);
  const dialogRef = useRef<HTMLDivElement | null>(null);
  useModalFocusTrap(dialogRef, open, () => {
    onClose();
    setOpen(false);
  });

  if (!open) return <button type="button">Outside {label}</button>;

  return (
    <div ref={dialogRef} role="dialog" aria-label={label || undefined}>
      {!empty && (
        <>
          <button type="button" aria-label={`First ${label}`.trim()}>First {label}</button>
          <button type="button" aria-label={`Last ${label}`.trim()}>Last {label}</button>
        </>
      )}
    </div>
  );
}

describe('useModalFocusTrap', () => {
  beforeEach(() => {
    document.body.style.overflow = '';
  });

  it('moves focus in, wraps Tab in both directions, and restores focus on close', () => {
    const trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.textContent = 'Trigger';
    document.body.appendChild(trigger);
    trigger.focus();

    const onClose = vi.fn();
    render(<TestModal onClose={onClose} />);

    const first = screen.getByRole('button', { name: 'First' });
    const last = screen.getByRole('button', { name: 'Last' });
    expect(document.activeElement).toBe(first);
    expect(document.body.style.overflow).toBe('hidden');

    last.focus();
    fireEvent.keyDown(document, { key: 'Tab' });
    expect(document.activeElement).toBe(first);

    first.focus();
    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true });
    expect(document.activeElement).toBe(last);

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(document.body.style.overflow).toBe('');
    expect(document.activeElement).toBe(trigger);

    trigger.remove();
  });

  it('ignores non-Tab keys and cleans up the document listener on unmount', () => {
    const onClose = vi.fn();
    const { unmount } = render(<TestModal onClose={onClose} />);

    fireEvent.keyDown(document, { key: 'Enter' });
    expect(onClose).not.toHaveBeenCalled();

    unmount();
    expect(document.body.style.overflow).toBe('');
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).not.toHaveBeenCalled();
  });

  it('restores an existing body overflow value after closing', () => {
    document.body.style.overflow = 'auto';
    const { unmount } = render(<TestModal onClose={vi.fn()} />);

    expect(document.body.style.overflow).toBe('hidden');
    unmount();
    expect(document.body.style.overflow).toBe('auto');
  });

  it('focuses an otherwise empty dialog and wraps its sole focus target', () => {
    const trigger = document.createElement('button');
    document.body.appendChild(trigger);
    trigger.focus();
    const { unmount } = render(<TestModal empty onClose={vi.fn()} />);

    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAttribute('tabindex', '-1');
    expect(document.activeElement).toBe(dialog);

    fireEvent.keyDown(document, { key: 'Tab' });
    expect(document.activeElement).toBe(dialog);

    unmount();
    expect(dialog).not.toHaveAttribute('tabindex', '-1');
    expect(document.activeElement).toBe(trigger);
    trigger.remove();
  });

  it('lets only the topmost nested modal handle Escape and keeps scroll locked', () => {
    const outerClose = vi.fn();
    const innerClose = vi.fn();
    const { rerender } = render(
      <>
        <TestModal label="Outer" onClose={outerClose} />
        <TestModal label="Inner" onClose={innerClose} />
      </>,
    );

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(innerClose).toHaveBeenCalledTimes(1);
    expect(outerClose).not.toHaveBeenCalled();
    expect(document.body.style.overflow).toBe('hidden');

    // The inner modal is now closed by its own state update; the outer modal
    // remains active and handles the next Escape.
    rerender(<TestModal label="Outer" onClose={outerClose} />);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(outerClose).toHaveBeenCalledTimes(1);
    expect(document.body.style.overflow).toBe('');
  });
});
