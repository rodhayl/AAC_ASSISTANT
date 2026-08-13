import { fireEvent, render, screen } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { ResetPasswordModal } from '../src/components/common/ResetPasswordModal';
import type { User } from '../src/types';

const user = {
  id: 7,
  username: 'student1',
  display_name: 'Student One',
  user_type: 'student',
} as User;

const t = ((key: string, options?: { defaultValue?: string; name?: string }) => {
  if (key === 'resetPasswordTitle') return `Reset Password for ${options?.name}`;
  return options?.defaultValue ?? key;
}) as never;

function renderModal(overrides: Partial<ComponentProps<typeof ResetPasswordModal>> = {}) {
  return render(
    <ResetPasswordModal
      user={user}
      value=""
      loading={false}
      error={null}
      t={t}
      onChange={vi.fn()}
      onClose={vi.fn()}
      onSubmit={vi.fn((event) => event.preventDefault())}
      {...overrides}
    />,
  );
}

describe('ResetPasswordModal', () => {
  it('exposes an accessible dialog and associated password field', () => {
    renderModal();

    const dialog = screen.getByRole('dialog', { name: 'Reset Password for Student One' });
    expect(dialog).toBeInTheDocument();
    expect(screen.getByLabelText('New Password')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'cancel' })).toBeInTheDocument();
  });

  it('renders errors as an alert associated with the password field', () => {
    renderModal({ error: 'Password is too weak' });

    const alert = screen.getByRole('alert');
    const input = screen.getByLabelText('New Password');
    expect(alert).toHaveTextContent('Password is too weak');
    expect(input).toHaveAttribute('aria-describedby', alert.id);
  });

  it('forwards password changes, submit, and close interactions', () => {
    const onChange = vi.fn();
    const onSubmit = vi.fn((event) => event.preventDefault());
    const onClose = vi.fn();
    renderModal({ onChange, onSubmit, onClose });

    fireEvent.change(screen.getByLabelText('New Password'), { target: { value: 'NewPass123!' } });
    fireEvent.submit(screen.getByRole('button', { name: 'Reset Password' }).closest('form')!);
    fireEvent.click(screen.getByRole('button', { name: 'cancel' }));

    expect(onChange).toHaveBeenCalledWith('NewPass123!');
    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('disables actions while saving', () => {
    renderModal({ loading: true });

    expect(screen.getByRole('button', { name: 'cancel' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Saving...' })).toBeDisabled();
  });
});
