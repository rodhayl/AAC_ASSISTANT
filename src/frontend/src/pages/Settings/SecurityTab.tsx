import { useState } from 'react';
import { Shield } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '../../store/authStore';
import api from '../../lib/api';
import { extractErrorMessage } from './error';

export function SecurityTab() {
  const { user } = useAuthStore();
  const { t } = useTranslation('settings');
  const [changeOpen, setChangeOpen] = useState(false);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [changeError, setChangeError] = useState<string | null>(null);
  const [changeLoading, setChangeLoading] = useState(false);

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
    } catch (err: unknown) {
      setChangeError(extractErrorMessage(err, 'Failed to change password'));
    } finally {
      setChangeLoading(false);
    }
  };

  return (
    <>
      <section
        id="settings-security"
        aria-labelledby="settings-security-heading"
        className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden"
      >
        <div className="p-6 border-b border-gray-200 dark:border-gray-700">
          <h3 id="settings-security-heading" className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            {t('security.title')}
          </h3>
        </div>
        <div className="p-6">
          <button
            onClick={() => {
              setChangeOpen(true);
              setChangeError(null);
            }}
            className="flex items-center text-indigo-600 hover:text-indigo-700 font-medium"
          >
            <Shield className="w-5 h-5 mr-2" />
            {t('security.change')}
          </button>
        </div>
      </section>

      {changeOpen && (
        <div className="fixed inset-0 bg-black bg-opacity-50 dark:bg-opacity-70 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-2xl w-full max-w-md p-6">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
              {t('security.change')}
            </h3>
            {changeError && <div className="mb-3 text-sm text-red-600">{changeError}</div>}
            <div className="space-y-3">
              <input
                id="current-password"
                name="current_password"
                type="password"
                value={currentPassword}
                onChange={(event) => setCurrentPassword(event.target.value)}
                placeholder={t('security.current')}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg"
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
                className="w-full px-3 py-2 border border-gray-300 rounded-lg"
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
                className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                aria-label={t('security.confirm')}
                autoComplete="new-password"
              />
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <button
                onClick={() => setChangeOpen(false)}
                className="px-4 py-2 text-gray-700 hover:bg-gray-100 rounded-lg"
              >
                {t('profile.cancel')}
              </button>
              <button
                onClick={handleChangePassword}
                disabled={changeLoading || !currentPassword || !newPassword || !confirmPassword}
                className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
              >
                {changeLoading ? t('security.saving') : t('security.save')}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
