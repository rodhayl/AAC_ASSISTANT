import { useId, type FormEvent } from 'react';
import type { TFunction } from 'i18next';
import type { User } from '../../types';
import { Button } from '../ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog';

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
  const inputId = `${idPrefix}-input`;
  const errorId = `${idPrefix}-error`;

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent showCloseButton={false} className="max-w-md p-6">
        <DialogHeader>
          <DialogTitle className="text-lg font-semibold">
            {t('resetPasswordTitle', { name: user.display_name })}
          </DialogTitle>
        </DialogHeader>
        {error && (
          <div className="rounded-lg bg-red-50 p-3 text-sm text-red-600 dark:bg-red-900/30 dark:text-red-400" id={errorId} role="alert">
            {error}
          </div>
        )}
        <form onSubmit={onSubmit} className="space-y-4">
          <label htmlFor={inputId} className="block text-sm font-medium text-foreground">
            {t('labels.newPassword')}
            <input
              id={inputId}
              aria-describedby={error ? errorId : undefined}
              type="password"
              value={value}
              onChange={(event) => onChange(event.target.value)}
              required
              minLength={8}
              autoComplete="new-password"
              className="mt-1 w-full rounded-lg border border-border bg-surface px-3 py-2 text-foreground"
              placeholder={t('labels.passwordHint')}
            />
          </label>
          <div className="flex justify-end gap-3">
            <button type="button" onClick={onClose} disabled={loading} className="rounded-lg px-4 py-2 text-foreground hover:bg-surface-hover">
              {t('cancel')}
            </button>
            <Button type="submit" variant="warning" loading={loading}>
              {loading ? t('security.saving', { ns: 'settings' }) : t('actions.resetPassword')}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
