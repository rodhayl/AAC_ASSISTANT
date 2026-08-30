import { useEffect, useState } from 'react';
import { AlertCircle, Check, Edit2, Save, User } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '../../store/authStore';
import { useAutoHide } from '../../hooks/useAutoHide';
import api, { extractError } from '../../lib/api';
import { Button } from '../../components/ui/button';

import { FormLabel } from '@/components/ui/FormLabel';
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
      className="bg-surface rounded-xl shadow-sm border border-border overflow-hidden"
    >
      <div className="p-6 border-b border-border">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <div className="h-16 w-16 bg-brand/10 rounded-full flex items-center justify-center">
              <User className="h-8 w-8 text-brand" />
            </div>
            <div>
              <h2 id="settings-profile-heading" className="text-xl font-bold text-foreground">
                {user?.display_name}
              </h2>
              <p className="text-muted-foreground capitalize">{user?.user_type}</p>
            </div>
          </div>
          {!editingProfile ? (
            <button
              onClick={() => setEditingProfile(true)}
              className="flex items-center text-brand hover:text-brand"
            >
              <Edit2 className="w-4 h-4 mr-1" />
              {t('profile.edit')}
            </button>
          ) : (
            <div className="flex items-center gap-2">
              <button
                onClick={() => setEditingProfile(false)}
                className="px-3 py-1 text-muted-foreground hover:bg-muted rounded"
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
          <FormLabel htmlFor="profile-username">
            {t('profile.username')}
          </FormLabel>
          <input
            id="profile-username"
            name="username"
            type="text"
            value={user?.username || ''}
            disabled
            autoComplete="username"
            className="w-full px-3 py-2 border border-border rounded-lg bg-background text-muted-foreground"
          />
        </div>
        <div className="md:col-span-2">
          <FormLabel htmlFor="profile-display-name">
            {t('profile.displayName')}
          </FormLabel>
          <input
            id="profile-display-name"
            name="display_name"
            type="text"
            value={editingProfile ? profileForm.display_name : user?.display_name || ''}
            onChange={(event) => setProfileForm((prev) => ({ ...prev, display_name: event.target.value }))}
            disabled={!editingProfile}
            autoComplete="name"
            className={`w-full px-3 py-2 border border-border rounded-lg ${
              !editingProfile ? 'bg-background text-muted-foreground' : 'bg-surface'
            }`}
          />
        </div>
        <div className="md:col-span-2">
          <FormLabel htmlFor="profile-email">
            {t('profile.email')}
          </FormLabel>
          <input
            id="profile-email"
            name="email"
            type="email"
            value={editingProfile ? profileForm.email : user?.email || ''}
            onChange={(event) => setProfileForm((prev) => ({ ...prev, email: event.target.value }))}
            disabled={!editingProfile}
            autoComplete="email"
            placeholder={editingProfile ? t('profile.emailPlaceholder') : t('profile.noEmail')}
            className={`w-full px-3 py-2 border border-border rounded-lg ${
              !editingProfile ? 'bg-background text-muted-foreground' : 'bg-surface'
            }`}
          />
        </div>
      </div>
    </section>
  );
}
