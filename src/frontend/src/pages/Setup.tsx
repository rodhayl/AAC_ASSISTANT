import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router';
import { useAuthStore } from '../store/authStore';
import { User, Lock, Mail, Shield, Check, X, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import api from '../lib/api';

export function Setup() {
  const [username, setUsername] = useState('admin1');
  const [displayName, setDisplayName] = useState('Administrator');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [localError, setLocalError] = useState<string | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [checkingStatus, setCheckingStatus] = useState(true);

  const setupAdmin = useAuthStore(state => state.setupAdmin);
  const isLoading = useAuthStore(state => state.isLoading);
  const error = useAuthStore(state => state.error);
  const navigate = useNavigate();
  const { t } = useTranslation('setup');

  useEffect(() => {
    let isMounted = true;
    api.get('/auth/setup-status')
      .then(res => {
        if (isMounted) {
          if (!res.data.setup_required) {
            navigate('/login', { replace: true });
          }
          setCheckingStatus(false);
        }
      })
      .catch(() => {
        if (isMounted) {
          setStatusError(t('errors.statusCheckFailed'));
          setCheckingStatus(false);
        }
      });
    return () => {
      isMounted = false;
    };
  }, [navigate, t]);

  const hasMinLength = password.length >= 8;
  const hasUpper = /[A-Z]/.test(password);
  const hasLower = /[a-z]/.test(password);
  const hasNumber = /[0-9]/.test(password);
  const notDefault = password.toLowerCase() !== 'admin123';
  const passwordsMatch = password.length > 0 && password === confirmPassword;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLocalError(null);

    if (password !== confirmPassword) {
      setLocalError(t('errors.passwordMismatch'));
      return;
    }

    if (!hasMinLength || !hasUpper || !hasLower || !hasNumber) {
      setLocalError(t('errors.passwordTooShort'));
      return;
    }

    try {
      await setupAdmin({
        username: username.trim(),
        display_name: displayName.trim(),
        email: email.trim() || undefined,
        password,
        confirm_password: confirmPassword,
      });
      navigate('/');
    } catch {
      // Error handled by store
    }
  };

  if (checkingStatus) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center p-4">
        <Loader2 className="w-8 h-8 animate-spin text-indigo-600 dark:text-indigo-400" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center p-4 transition-colors duration-200">
      <div className="max-w-md w-full bg-white dark:bg-gray-800 rounded-xl shadow-lg p-8">
        <div className="text-center mb-6">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-indigo-100 dark:bg-indigo-900/40 text-indigo-600 dark:text-indigo-400 mb-3">
            <Shield className="w-6 h-6" />
          </div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-1">{t('title')}</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">{t('subtitle')}</p>
        </div>

        {(error || localError) && (
          <div className="bg-red-50 dark:bg-red-900/30 text-red-600 dark:text-red-400 p-3 rounded-lg mb-6 text-sm">
            {localError || error}
          </div>
        )}

        {statusError && (
          <div className="bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 p-3 rounded-lg mb-6 text-sm">
            {statusError}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="setup-username" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('username')}
            </label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <User className="h-5 w-5 text-gray-400 dark:text-gray-500" />
              </div>
              <input
                id="setup-username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="block w-full pl-10 pr-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-indigo-500 focus:border-indigo-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 text-sm"
                placeholder={t('placeholderUser')}
                required
                autoComplete="username"
              />
            </div>
          </div>

          <div>
            <label htmlFor="setup-displayname" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('displayName')}
            </label>
            <input
              id="setup-displayname"
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              className="block w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-indigo-500 focus:border-indigo-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 text-sm"
              placeholder={t('placeholderDisplay')}
              required
            />
          </div>

          <div>
            <label htmlFor="setup-email" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('email')}
            </label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <Mail className="h-5 w-5 text-gray-400 dark:text-gray-500" />
              </div>
              <input
                id="setup-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="block w-full pl-10 pr-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-indigo-500 focus:border-indigo-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 text-sm"
                placeholder={t('placeholderEmail')}
                autoComplete="email"
              />
            </div>
          </div>

          <div>
            <label htmlFor="setup-password" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('password')}
            </label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <Lock className="h-5 w-5 text-gray-400 dark:text-gray-500" />
              </div>
              <input
                id="setup-password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="block w-full pl-10 pr-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-indigo-500 focus:border-indigo-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 text-sm"
                placeholder={t('placeholderPass')}
                required
                autoComplete="new-password"
              />
            </div>
          </div>

          <div>
            <label htmlFor="setup-confirm-password" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('confirmPassword')}
            </label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <Lock className="h-5 w-5 text-gray-400 dark:text-gray-500" />
              </div>
              <input
                id="setup-confirm-password"
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="block w-full pl-10 pr-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-indigo-500 focus:border-indigo-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 text-sm"
                placeholder={t('placeholderConfirm')}
                required
                autoComplete="new-password"
              />
            </div>
          </div>

          <div className="p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg space-y-1 text-xs text-gray-600 dark:text-gray-300">
            <p className="font-semibold text-gray-700 dark:text-gray-200 mb-1">{t('requirements.title')}</p>
            <div className="flex items-center gap-1.5">
              {hasMinLength ? <Check className="w-3.5 h-3.5 text-green-500" /> : <X className="w-3.5 h-3.5 text-gray-400" />}
              <span>{t('requirements.minChars')}</span>
            </div>
            <div className="flex items-center gap-1.5">
              {hasUpper && hasLower ? <Check className="w-3.5 h-3.5 text-green-500" /> : <X className="w-3.5 h-3.5 text-gray-400" />}
              <span>{t('requirements.upperLower')}</span>
            </div>
            <div className="flex items-center gap-1.5">
              {hasNumber ? <Check className="w-3.5 h-3.5 text-green-500" /> : <X className="w-3.5 h-3.5 text-gray-400" />}
              <span>{t('requirements.number')}</span>
            </div>
            <div className="flex items-center gap-1.5">
              {notDefault ? <Check className="w-3.5 h-3.5 text-green-500" /> : <X className="w-3.5 h-3.5 text-red-500" />}
              <span>{t('requirements.notDefault')}</span>
            </div>
            {confirmPassword.length > 0 && (
              <div className="flex items-center gap-1.5 pt-1 border-t border-gray-200 dark:border-gray-600">
                {passwordsMatch ? <Check className="w-3.5 h-3.5 text-green-500" /> : <X className="w-3.5 h-3.5 text-red-500" />}
                <span>{passwordsMatch ? t('confirmPassword') + ' ✓' : t('errors.passwordMismatch')}</span>
              </div>
            )}
          </div>

          <button
            type="submit"
            disabled={isLoading || !hasMinLength || !hasUpper || !hasLower || !hasNumber || !notDefault || !passwordsMatch}
            className="w-full flex justify-center py-2.5 px-4 border border-transparent rounded-lg shadow-sm text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isLoading ? (
              <Loader2 className="w-5 h-5 animate-spin" />
            ) : (
              t('submit')
            )}
          </button>

          <div className="text-center pt-2">
            <a href="/login" className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline">
              {t('loginLink')}
            </a>
          </div>
        </form>
      </div>
    </div>
  );
}
