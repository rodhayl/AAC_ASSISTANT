import { useState } from 'react'
import { useNavigate } from 'react-router'
import { useAuthStore } from '../store/authStore'
import { User, Lock, IdCard, CheckCircle2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Button } from '../components/ui/button'
import { StatusMessage } from '../components/ui/StatusMessage'

import { FormLabel } from '@/components/ui/FormLabel';

export function Register() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const register = useAuthStore((state) => state.register)
  const isLoading = useAuthStore((state) => state.isLoading)
  const error = useAuthStore((state) => state.error)
  const navigate = useNavigate()
  const { t } = useTranslation('register')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      await register({
        username,
        password,
        display_name: displayName,
        user_type: 'student'
      })
      navigate('/')
    } catch {
      console.error('Registration failed')
    }
  }

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4 transition-colors duration-200">
      <div className="max-w-md w-full bg-surface rounded-xl shadow-lg p-8">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-brand mb-2">{t('title')}</h1>
          <p className="text-muted-foreground">{t('subtitle')}</p>
        </div>

        {error && (
          <StatusMessage variant="error" className="mb-6">{error}</StatusMessage>
        )}

        <form onSubmit={handleSubmit} className="space-y-6">
          <div>
            <FormLabel htmlFor="username" className="mb-2">{t('username')}</FormLabel>
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
                placeholder={t('placeholders.username')}
                required
                autoComplete="username"
              />
            </div>
          </div>

          <div>
            <FormLabel htmlFor="password" className="mb-2">{t('password')}</FormLabel>
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
                placeholder={t('placeholders.password')}
                required
                autoComplete="new-password"
              />
            </div>
          </div>

          <div>
            <FormLabel htmlFor="displayName" className="mb-2">{t('displayName')}</FormLabel>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <IdCard className="h-5 w-5 text-muted-foreground" />
              </div>
              <input
                id="displayName"
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                className="block w-full pl-10 pr-3 py-2 border border-border rounded-lg focus:ring-brand focus:border-brand bg-surface text-foreground"
                placeholder={t('placeholders.displayName')}
                required
                autoComplete="name"
              />
            </div>
          </div>

          <p className="text-xs text-muted-foreground">
            {t('teacherNote')}
          </p>

          <Button
            type="submit"
            loading={isLoading}
            className="w-full justify-center shadow-sm"
          >
            <CheckCircle2 />
            {t('create')}
          </Button>
        </form>

        <div className="mt-4 text-center text-sm text-muted-foreground">
          <a href="/login" className="text-brand hover:text-brand">{t('back')}</a>
        </div>
      </div>
    </div>
  )
}
