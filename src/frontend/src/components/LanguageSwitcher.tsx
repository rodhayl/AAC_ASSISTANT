import { useTranslation } from 'react-i18next'
import { useLocaleStore } from '../store/localeStore'
import { useAuthStore } from '../store/authStore'
import api from '../lib/api'

export function LanguageSwitcher() {
  const { t } = useTranslation('common')
  const { locale, setLocale } = useLocaleStore()
  const { user } = useAuthStore()
  const selectId = 'language-switcher'

  return (
    <label htmlFor={selectId} className="flex items-center gap-2 text-sm text-secondary min-w-0">
      <span className="hidden lg:inline">{t('language.switcher.label')}</span>
      <select
        id={selectId}
        name="ui_language"
        value={locale}
        onChange={async (e) => {
          const lng = e.target.value
          setLocale(lng)
          try {
            if (user?.id) {
              await api.put('/settings/ui', { ui_language: lng })
            }
          } catch {
            /* ignore */
          }
        }}
        className="w-[8.25rem] sm:w-auto max-w-full bg-surface border border-border rounded-md px-2 py-1 text-primary"
        aria-label={t('language.switcher.label')}
      >
        <option value="es-ES">{t('language.switcher.es')} (España)</option>
        <option value="en">{t('language.switcher.en')}</option>
      </select>
    </label>
  )
}
