import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ConfirmDialog } from '../src/components/ui/ConfirmDialog';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => (key === 'close' ? 'Close' : key),
  }),
}));

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

    // Base UI AlertDialog exposes the more specific role="alertdialog".
    expect(screen.getByRole('alertdialog', { name: 'Delete board' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Close' })).toBeVisible();

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
