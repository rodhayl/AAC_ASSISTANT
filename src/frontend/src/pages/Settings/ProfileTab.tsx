import { useEffect, useState } from 'react';
import { AlertCircle, Check, Edit2, Save, User } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '../../store/authStore';
import { useAutoHide } from '../../hooks/useAutoHide';
import api, { extractError } from '../../lib/api';
import { Button } from '../../components/ui/button';

export function ProfileTab() {
  const user = useAuthStore(state => state.user);
  const { t } = useTranslation('settings');
  const [editingProfile, setEditingProfile] = useState(false);
  const [profileForm, setProfileForm] = useState({ display_name: '', email: '' });
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileSuccess, setProfileSuccess] = useState(false);
  const [profileError, setProfileError] = useState<string | null>(null);

  useEffect(() => {
    if (user) {
      setProfileForm({
        display_name: user.display_name || '',
        email: user.email || '',
      });
    }
  }, [user, editingProfile]);

  useAutoHide(profileSuccess, () => setProfileSuccess(false));

  const handleSaveProfile = async () => {
    setProfileSaving(true);
    setProfileError(null);
    try {
      // A blank email must be sent as null, not an empty string: the backend
      // schema types email as EmailStr | None, so '' fails validation and
      // blocks saving even when the user only changed their display name.
      const displayName = profileForm.display_name.trim();
      if (!displayName) {
        setProfileError(t('profile.displayNameRequired'));
        return;
      }
      const res = await api.put('/auth/profile', {
        display_name: displayName,
        email: profileForm.email.trim() === '' ? null : profileForm.email.trim(),
      });
      useAuthStore.setState((state) => {
        const newUser = { ...res.data };
        if (newUser.settings === null || newUser.settings === undefined) {
          newUser.settings = state.user?.settings;
        }
        if (!newUser.user_type && state.user?.user_type) {
          newUser.user_type = state.user.user_type;
        }
        return { user: state.user ? { ...state.user, ...newUser } : newUser };
      });
      setProfileSuccess(true);
      setEditingProfile(false);
    } catch (err: unknown) {
      setProfileError(extractError(err, t('profile.saveFailed')));
    } finally {
      setProfileSaving(false);
    }
  };

  return (
    <section
      id="settings-profile"
      aria-labelledby="settings-profile-heading"
      className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden"
    >
      <div className="p-6 border-b border-gray-200 dark:border-gray-700">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <div className="h-16 w-16 bg-indigo-100 rounded-full flex items-center justify-center">
              <User className="h-8 w-8 text-indigo-600" />
            </div>
            <div>
              <h2 id="settings-profile-heading" className="text-xl font-bold text-gray-900 dark:text-gray-100">
                {user?.display_name}
              </h2>
              <p className="text-gray-500 capitalize dark:text-gray-400">{user?.user_type}</p>
            </div>
          </div>
          {!editingProfile ? (
            <button
              onClick={() => setEditingProfile(true)}
              className="flex items-center text-indigo-600 hover:text-indigo-700 dark:text-indigo-400 dark:hover:text-indigo-300"
            >
              <Edit2 className="w-4 h-4 mr-1" />
              {t('profile.edit')}
            </button>
          ) : (
            <div className="flex items-center gap-2">
              <button
                onClick={() => setEditingProfile(false)}
                className="px-3 py-1 text-gray-600 hover:bg-gray-100 rounded"
              >
                {t('profile.cancel')}
              </button>
              <Button onClick={handleSaveProfile} disabled={profileSaving} className="flex items-center" >
                <Save className="w-4 h-4 mr-1" />
                {profileSaving ? t('security.saving') : t('profile.save')}
              </Button>
            </div>
          )}
        </div>
        {profileSuccess && (
          <div className="mt-3 flex items-center text-green-600 text-sm">
            <Check className="w-4 h-4 mr-1" /> {t('profile.updated')}
          </div>
        )}
        {profileError && (
          <div className="mt-3 flex items-center text-red-600 text-sm">
            <AlertCircle className="w-4 h-4 mr-1" /> {profileError}
          </div>
        )}
      </div>
      <div className="p-6 grid grid-cols-1 md:grid-cols-2 gap-6">
        <div>
          <label htmlFor="profile-username" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            {t('profile.username')}
          </label>
          <input
            id="profile-username"
            name="username"
            type="text"
            value={user?.username || ''}
            disabled
            autoComplete="username"
            className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-gray-50 text-gray-500"
          />
        </div>
        <div className="md:col-span-2">
          <label htmlFor="profile-display-name" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            {t('profile.displayName')}
          </label>
          <input
            id="profile-display-name"
            name="display_name"
            type="text"
            value={editingProfile ? profileForm.display_name : user?.display_name || ''}
            onChange={(event) => setProfileForm((prev) => ({ ...prev, display_name: event.target.value }))}
            disabled={!editingProfile}
            autoComplete="name"
            className={`w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg ${
              !editingProfile ? 'bg-gray-50 text-gray-500 dark:bg-gray-700 dark:text-gray-300' : 'bg-white dark:bg-gray-800'
            }`}
          />
        </div>
        <div className="md:col-span-2">
          <label htmlFor="profile-email" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            {t('profile.email')}
          </label>
          <input
            id="profile-email"
            name="email"
            type="email"
            value={editingProfile ? profileForm.email : user?.email || ''}
            onChange={(event) => setProfileForm((prev) => ({ ...prev, email: event.target.value }))}
            disabled={!editingProfile}
            autoComplete="email"
            placeholder={editingProfile ? t('profile.emailPlaceholder') : t('profile.noEmail')}
            className={`w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg ${
              !editingProfile ? 'bg-gray-50 text-gray-500 dark:bg-gray-700 dark:text-gray-300' : 'bg-white dark:bg-gray-800'
            }`}
          />
        </div>
      </div>
    </section>
  );
}
