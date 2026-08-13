import { useId, useRef, type FormEvent } from 'react';
import { useModalFocusTrap } from '../../hooks/useModalFocusTrap';
import type { TFunction } from 'i18next';
import type { User } from '../../types';

interface ResetPasswordModalProps {
  user: User;
  value: string;
  loading: boolean;
  error: string | null;
  t: TFunction;
  onChange: (value: string) => void;
  onClose: () => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}

export function ResetPasswordModal({
  user,
  value,
  loading,
  error,
  t,
  onChange,
  onClose,
  onSubmit,
}: ResetPasswordModalProps) {
  const idPrefix = useId();
  const dialogRef = useRef<HTMLDivElement | null>(null);
  useModalFocusTrap(dialogRef, true, onClose);
  const titleId = `${idPrefix}-title`;
  const inputId = `${idPrefix}-input`;
  const errorId = `${idPrefix}-error`;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby={titleId}>
      <div ref={dialogRef} className="glass-card w-full max-w-md p-6" role="document">
        <h3 id={titleId} className="mb-4 text-lg font-semibold text-gray-900 dark:text-gray-100">
          {t('resetPasswordTitle', { name: user.display_name, defaultValue: `Reset Password for ${user.display_name}` })}
        </h3>
        {error && <div className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-600 dark:bg-red-900/30 dark:text-red-400" id={errorId} role="alert">{error}</div>}
        <form onSubmit={onSubmit} className="space-y-4">
          <label htmlFor={inputId} className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            {t('labels.newPassword', { defaultValue: 'New Password' })}
            <input
              id={inputId}
              aria-describedby={error ? errorId : undefined}
              type="password"
              value={value}
              onChange={(event) => onChange(event.target.value)}
              required
              minLength={8}
              autoComplete="new-password"
              className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-gray-900 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
              placeholder={t('labels.passwordHint', { defaultValue: 'Min 8 chars, 1 uppercase, 1 lowercase, 1 number' })}
            />
          </label>
          <div className="mt-6 flex justify-end gap-3">
            <button type="button" onClick={onClose} disabled={loading} className="rounded-lg px-4 py-2 text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700">
              {t('cancel')}
            </button>
            <button type="submit" disabled={loading} className="rounded-lg bg-amber-600 px-4 py-2 text-white hover:bg-amber-700 disabled:opacity-50">
              {loading ? t('security.saving', { ns: 'settings', defaultValue: 'Saving...' }) : t('actions.resetPassword', { defaultValue: 'Reset Password' })}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
