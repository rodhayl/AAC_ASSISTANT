import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { TrashIcon } from 'lucide-react';
import { IconButton } from '../src/components/ui/icon-button';

describe('IconButton', () => {
  it('renders an accessible button with native title fallback and passes through clicks', async () => {
    const onClick = vi.fn();
    render(
      <IconButton label="Delete" onClick={onClick} variant="destructive">
        <TrashIcon />
      </IconButton>,
    );

    const button = screen.getByTitle('Delete');
    expect(button).toHaveAttribute('aria-label', 'Delete');
    expect(button).toHaveAttribute('type', 'button');

    fireEvent.click(button);
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  // NOTE: Base UI's tooltip popup does not mount under jsdom (floating
  // positioning APIs are unavailable there). Tooltip open/focus behavior is
  // verified in the browser via the contrast-interactive E2E suite instead.
  it('supports disabled state', () => {
    render(
      <IconButton label="Save" disabled>
        <span>x</span>
      </IconButton>,
    );
    expect(screen.getByTitle('Save')).toBeDisabled();
  });
});
