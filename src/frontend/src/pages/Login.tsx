import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router';
import { useAuthStore } from '../store/authStore';
import { User, Lock, Loader2, ShieldAlert } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import api from '../lib/api';
import { Button } from '../components/ui/button';
import { StatusMessage } from '../components/ui/StatusMessage';

export function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [setupRequired, setSetupRequired] = useState(false);
  const login = useAuthStore(state => state.login);
  const isLoading = useAuthStore(state => state.isLoading);
  const error = useAuthStore(state => state.error);
  const navigate = useNavigate();
  const { t } = useTranslation('login');

  useEffect(() => {
    let isMounted = true;
    api.get('/auth/setup-status')
      .then(res => {
        if (isMounted && res.data.setup_required) {
          setSetupRequired(true);
          navigate('/setup', { replace: true });
        }
      })
      .catch(() => {
        // Silently ignore if offline
      });
    return () => {
      isMounted = false;
    };
  }, [navigate]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      // Force update from DOM values
      const form = e.target as HTMLFormElement;
      const userField = form.querySelector('input[type="text"]') as HTMLInputElement;
      const passField = form.querySelector('input[type="password"]') as HTMLInputElement;
      
      const finalUser = userField?.value || username;
      const finalPass = passField?.value || password;

      await login(finalUser, finalPass);
      navigate('/');
    } catch {
      console.error('Login failed');
    }
  };

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4 transition-colors duration-200">
      <div className="max-w-md w-full bg-surface rounded-xl shadow-lg p-8">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-brand mb-2">{t('title')}</h1>
          <p className="text-muted-foreground">{t('subtitle')}</p>
        </div>

        {setupRequired && (
          <div className="bg-brand/10 border border-brand/20 rounded-lg p-3 mb-6 text-sm text-brand flex items-center justify-between">
            <div className="flex items-center gap-2">
              <ShieldAlert className="w-4 h-4 text-brand shrink-0" />
              <span>{t('setupNotice')}</span>
            </div>
            <a
              href="/setup"
              className="ml-2 font-semibold underline text-brand hover:text-brand shrink-0"
            >
              {t('setupButton')}
            </a>
          </div>
        )}

        {error && (<StatusMessage variant="error" className="mb-6">{error}</StatusMessage>
        )}

        <form onSubmit={handleSubmit} className="space-y-6">
          <div>
            <label htmlFor="username" className="block text-sm font-medium text-foreground mb-2">{t('username')}</label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <User className="h-5 w-5 text-muted-foreground" />
              </div>
              <input
                id="username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="block w-full pl-10 pr-3 py-2 border border-border rounded-lg focus:ring-brand focus:border-brand bg-surface text-foreground"
                placeholder={t('placeholderUser')}
                required
                autoComplete="username"
              />
            </div>
          </div>

          <div>
            <label htmlFor="password" className="block text-sm font-medium text-foreground mb-2">{t('password')}</label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <Lock className="h-5 w-5 text-muted-foreground" />
              </div>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="block w-full pl-10 pr-3 py-2 border border-border rounded-lg focus:ring-brand focus:border-brand bg-surface text-foreground"
                placeholder={t('placeholderPass')}
                required
                autoComplete="current-password"
              />
            </div>
          </div>

          <Button
            type="submit"
            loading={isLoading}
            className="w-full shadow-sm"
            aria-label={t('login')}
          >
            {isLoading ? (
              <Loader2 className="w-5 h-5 animate-spin" />
            ) : (
              t('login')
            )}
          </Button>
          
          <div className="mt-4 text-center text-sm text-muted-foreground">
            <p>{t('defaults.title')}</p>
            <p>{t('defaults.student')}</p>
            <p>{t('defaults.teacher')}</p>
            <p>{t('defaults.admin')}</p>
            <div className="mt-2">
              <a href="/register" className="text-brand text-brand hover:text-brand">{t('register')}</a>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
