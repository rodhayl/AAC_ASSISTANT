import { describe, it, expect } from 'vitest'
import '../i18n/index'
import { render } from '@testing-library/react'
import { LanguageSwitcher } from '../components/LanguageSwitcher'
import { I18nextProvider } from 'react-i18next'
import i18n from './index'
import { useLocaleStore } from '../store/localeStore'

describe('i18n initialization', () => {
  it('loads Spanish strings from common namespace', () => {
    i18n.changeLanguage('es')
    expect(i18n.t('notifications.title')).toBe('Notificaciones')
  })

  it('switches language via LanguageSwitcher', async () => {
    localStorage.setItem('aac_assistant_locale', 'es')
    i18n.changeLanguage('es')
    useLocaleStore.getState().setLocale('es-ES')
    const { getByLabelText } = render(
      <I18nextProvider i18n={i18n}>
        <LanguageSwitcher />
      </I18nextProvider>
    )
    const select = getByLabelText('Idioma') as HTMLSelectElement
    expect(select.value).toBe('es-ES')
  })
})
