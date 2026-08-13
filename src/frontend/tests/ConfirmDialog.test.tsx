import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ConfirmDialog } from '../src/components/ui/ConfirmDialog';

describe('ConfirmDialog', () => {
  it('labels the dialog, focuses its controls, and closes on Escape', () => {
    const onClose = vi.fn();

    render(
      <ConfirmDialog
        isOpen
        onClose={onClose}
        onConfirm={vi.fn()}
        title="Delete board"
        description="This cannot be undone."
      />,
    );

    expect(screen.getByRole('dialog', { name: 'Delete board' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Close dialog' })).toBeVisible();

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
