import { useState } from 'react';
import { Shield } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '../../store/authStore';
import { useToastStore } from '../../store/toastStore';
import api, { extractError } from '../../lib/api';
import { Button } from '../../components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '../../components/ui/dialog';

export function SecurityTab() {
  const user = useAuthStore(state => state.user);
  const addToast = useToastStore(state => state.addToast);
  const { t } = useTranslation('settings');
  const [changeOpen, setChangeOpen] = useState(false);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [changeError, setChangeError] = useState<string | null>(null);
  const [changeLoading, setChangeLoading] = useState(false);

  const closeChangeDialog = () => {
    setChangeOpen(false);
    setChangeError(null);
  };

  const handleChangePassword = async () => {
    if (!user) return;
    setChangeLoading(true);
    setChangeError(null);
    try {
      await api.post('/auth/change-password', {
        username: user.username,
        current_password: currentPassword,
        new_password: newPassword,
        confirm_password: confirmPassword,
      });
      setChangeOpen(false);
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
      addToast(t('security.changeSuccess'), 'success');
    } catch (err: unknown) {
      setChangeError(extractError(err, t('security.changeFailed')));
    } finally {
      setChangeLoading(false);
    }
  };

  return (
    <>
      <section
        id="settings-security"
        aria-labelledby="settings-security-heading"
        className="bg-surface rounded-xl shadow-sm border border-border overflow-hidden"
      >
        <div className="p-6 border-b border-border">
          <h3 id="settings-security-heading" className="text-lg font-semibold text-foreground">
            {t('security.title')}
          </h3>
        </div>
        <div className="p-6">
          <button
            onClick={() => {
              setChangeOpen(true);
              setChangeError(null);
            }}
            className="flex items-center text-brand hover:text-brand text-brand hover:text-brand font-medium"
          >
            <Shield className="w-5 h-5 mr-2" />
            {t('security.change')}
          </button>
        </div>
      </section>

      {changeOpen && (
        <Dialog open onOpenChange={(open) => { if (!open) closeChangeDialog(); }}>
          <DialogContent showCloseButton={false} className="max-w-md p-6">
            <DialogHeader>
              <DialogTitle className="text-lg font-semibold text-foreground">
                {t('security.change')}
              </DialogTitle>
            </DialogHeader>
            {changeError && <div className="mb-3 text-sm text-red-600">{changeError}</div>}
            <div className="space-y-3">
              <input
                id="current-password"
                name="current_password"
                type="password"
                value={currentPassword}
                onChange={(event) => setCurrentPassword(event.target.value)}
                placeholder={t('security.current')}
                className="w-full px-3 py-2 border border-border rounded-lg"
                aria-label={t('security.current')}
                autoComplete="current-password"
              />
              <input
                id="new-password"
                name="new_password"
                type="password"
                value={newPassword}
                onChange={(event) => setNewPassword(event.target.value)}
                placeholder={t('security.new')}
                className="w-full px-3 py-2 border border-border rounded-lg"
                aria-label={t('security.new')}
                autoComplete="new-password"
              />
              <input
                id="confirm-password"
                name="confirm_password"
                type="password"
                value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)}
                placeholder={t('security.confirm')}
                className="w-full px-3 py-2 border border-border rounded-lg"
                aria-label={t('security.confirm')}
                autoComplete="new-password"
              />
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <button
                onClick={closeChangeDialog}
                className="px-4 py-2 text-foreground hover:bg-muted rounded-lg"
              >
                {t('profile.cancel')}
              </button>
              <Button onClick={handleChangePassword} disabled={changeLoading || !currentPassword || !newPassword || !confirmPassword}  >
                {changeLoading ? t('security.saving') : t('security.save')}
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      )}
    </>
  );
}
