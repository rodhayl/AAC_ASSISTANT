import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router';
import { useAuthStore } from '../store/authStore';
import { User, Lock, Mail, Shield, Check, X, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import api from '../lib/api';
import { Button } from '../components/ui/button';
import { StatusMessage } from '../components/ui/StatusMessage';

import { FormLabel } from '@/components/ui/FormLabel';
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
      <div className="min-h-screen bg-background flex items-center justify-center p-4">
        <Loader2 className="w-8 h-8 animate-spin text-brand" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4 transition-colors duration-200">
      <div className="max-w-md w-full bg-surface rounded-xl shadow-lg p-8">
        <div className="text-center mb-6">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-brand/10 text-brand mb-3">
            <Shield className="w-6 h-6" />
          </div>
          <h1 className="text-2xl font-bold text-foreground mb-1">{t('title')}</h1>
          <p className="text-sm text-muted-foreground">{t('subtitle')}</p>
        </div>

        {(error || localError) && (
          <StatusMessage variant="error" className="mb-6">
            {localError || error}
          </StatusMessage>
        )}

        {statusError && (
          <StatusMessage variant="warning" className="mb-6">
            {statusError}
          </StatusMessage>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <FormLabel htmlFor="setup-username">
              {t('username')}
            </FormLabel>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <User className="h-5 w-5 text-muted-foreground" />
              </div>
              <input
                id="setup-username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="block w-full pl-10 pr-3 py-2 border border-border rounded-lg focus:ring-brand focus:border-brand bg-surface text-foreground text-sm"
                placeholder={t('placeholderUser')}
                required
                autoComplete="username"
              />
            </div>
          </div>

          <div>
            <FormLabel htmlFor="setup-displayname">
              {t('displayName')}
            </FormLabel>
            <input
              id="setup-displayname"
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              className="block w-full px-3 py-2 border border-border rounded-lg focus:ring-brand focus:border-brand bg-surface text-foreground text-sm"
              placeholder={t('placeholderDisplay')}
              required
            />
          </div>

          <div>
            <FormLabel htmlFor="setup-email">
              {t('email')}
            </FormLabel>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <Mail className="h-5 w-5 text-muted-foreground" />
              </div>
              <input
                id="setup-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="block w-full pl-10 pr-3 py-2 border border-border rounded-lg focus:ring-brand focus:border-brand bg-surface text-foreground text-sm"
                placeholder={t('placeholderEmail')}
                autoComplete="email"
              />
            </div>
          </div>

          <div>
            <FormLabel htmlFor="setup-password">
              {t('password')}
            </FormLabel>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <Lock className="h-5 w-5 text-muted-foreground" />
              </div>
              <input
                id="setup-password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="block w-full pl-10 pr-3 py-2 border border-border rounded-lg focus:ring-brand focus:border-brand bg-surface text-foreground text-sm"
                placeholder={t('placeholderPass')}
                required
                autoComplete="new-password"
              />
            </div>
          </div>

          <div>
            <FormLabel htmlFor="setup-confirm-password">
              {t('confirmPassword')}
            </FormLabel>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <Lock className="h-5 w-5 text-muted-foreground" />
              </div>
              <input
                id="setup-confirm-password"
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="block w-full pl-10 pr-3 py-2 border border-border rounded-lg focus:ring-brand focus:border-brand bg-surface text-foreground text-sm"
                placeholder={t('placeholderConfirm')}
                required
                autoComplete="new-password"
              />
            </div>
          </div>

          <div className="p-3 bg-background/50 rounded-lg space-y-1 text-xs text-muted-foreground">
            <p className="font-semibold text-foreground mb-1">{t('requirements.title')}</p>
            <div className="flex items-center gap-1.5">
              {hasMinLength ? <Check className="w-3.5 h-3.5 text-green-500" /> : <X className="w-3.5 h-3.5 text-muted-foreground" />}
              <span>{t('requirements.minChars')}</span>
            </div>
            <div className="flex items-center gap-1.5">
              {hasUpper && hasLower ? <Check className="w-3.5 h-3.5 text-green-500" /> : <X className="w-3.5 h-3.5 text-muted-foreground" />}
              <span>{t('requirements.upperLower')}</span>
            </div>
            <div className="flex items-center gap-1.5">
              {hasNumber ? <Check className="w-3.5 h-3.5 text-green-500" /> : <X className="w-3.5 h-3.5 text-muted-foreground" />}
              <span>{t('requirements.number')}</span>
            </div>
            <div className="flex items-center gap-1.5">
              {notDefault ? <Check className="w-3.5 h-3.5 text-green-500" /> : <X className="w-3.5 h-3.5 text-red-500" />}
              <span>{t('requirements.notDefault')}</span>
            </div>
            {confirmPassword.length > 0 && (
              <div className="flex items-center gap-1.5 pt-1 border-t border-border">
                {passwordsMatch ? <Check className="w-3.5 h-3.5 text-green-500" /> : <X className="w-3.5 h-3.5 text-red-500" />}
                <span>{passwordsMatch ? t('confirmPassword') + ' ✓' : t('errors.passwordMismatch')}</span>
              </div>
            )}
          </div>

          <Button
            type="submit"
            loading={isLoading}
            disabled={!hasMinLength || !hasUpper || !hasLower || !hasNumber || !notDefault || !passwordsMatch}
            className="w-full shadow-sm"
          >
            {isLoading ? (
              <Loader2 className="w-5 h-5 animate-spin" />
            ) : (
              t('submit')
            )}
          </Button>

          <div className="text-center pt-2">
            <a href="/login" className="text-xs text-brand hover:underline">
              {t('loginLink')}
            </a>
          </div>
        </form>
      </div>
    </div>
  );
}
