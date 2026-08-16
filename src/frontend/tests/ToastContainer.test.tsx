import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ToastContainer } from '../src/components/ui/ToastContainer';

const storeState = vi.hoisted(() => ({
  toasts: [{ id: 't1', message: 'Settings saved', type: 'success' as const }],
  removeToast: vi.fn(),
}));

vi.mock('../src/store/toastStore', () => ({
  useToastStore: (selector?: (state: typeof storeState) => unknown) =>
    selector ? selector(storeState) : storeState,
}));

describe('ToastContainer', () => {
  it('renders toast messages and routes the dismiss action', () => {
    render(<ToastContainer />);

    expect(screen.getByText('Settings saved')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button'));
    expect(storeState.removeToast).toHaveBeenCalledWith('t1');
  });
});
