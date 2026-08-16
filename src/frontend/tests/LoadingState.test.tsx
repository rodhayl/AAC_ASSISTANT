import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { LoadingState } from '../src/components/ui/LoadingState';

describe('LoadingState', () => {
  it('announces its label to assistive tech and renders a hidden spinner', () => {
    render(<LoadingState label="Loading boards" size="lg" />);

    const status = screen.getByRole('status');
    expect(status).toHaveAttribute('aria-label', 'Loading boards');
    // The visual spinner is decorative; the label is the accessible text.
    expect(status.querySelector('span[aria-hidden="true"]')).toBeInTheDocument();
    expect(screen.getByText('Loading boards')).toBeInTheDocument();
  });

  it('renders a full-height layout when requested', () => {
    const { container } = render(<LoadingState fullHeight />);
    expect(container.firstElementChild).toHaveClass('min-h-screen');
  });

  it('defaults to the medium size and a "Loading" label', () => {
    render(<LoadingState />);
    expect(screen.getByRole('status')).toHaveAttribute('aria-label', 'Loading');
    expect(screen.getByText('Loading')).toBeInTheDocument();
  });
});
