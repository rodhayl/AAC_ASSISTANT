import { describe, it, expect } from 'vitest'
import '../src/i18n/index'
import { render, waitFor } from '@testing-library/react'
import { LanguageSwitcher } from '../src/components/LanguageSwitcher'
import { I18nextProvider } from 'react-i18next'
import i18n, { NAMESPACE_TABLE, ensureLocale } from '../src/i18n/index'
import { useLocaleStore } from '../src/store/localeStore'

describe('i18n initialization', () => {
  it('loads Spanish strings from common namespace', () => {
    i18n.changeLanguage('es')
    expect(i18n.t('notifications.title')).toBe('Notificaciones')
  })

  it('loads English even when changeLanguage bypasses ensureLocale (choke point)', async () => {
    // Simulate LanguageDetector at init / a direct changeLanguage('en') call:
    // no ensureLocale await anywhere. The languageChanged hook must load the
    // lazy English bundle on its own, or the UI would stay in Spanish.
    localStorage.setItem('aac_assistant_locale', 'es')
    i18n.changeLanguage('es')
    i18n.changeLanguage('en')
    await waitFor(
      () => {
        expect(i18n.t('notifications.title')).toBe('Notifications')
      },
      { timeout: 5000 }
    )
  })

  it('derives es, en and i18next resources from one namespace table', async () => {
    const nsNames = NAMESPACE_TABLE.map(({ ns }) => ns)
    // The i18next ns option and the es resources map come from the same rows.
    expect(i18n.options.ns).toEqual(nsNames)
    const esKeys = Object.keys(i18n.options.resources?.es ?? {})
    expect(esKeys).toEqual(nsNames)
    expect(new Set(esKeys).size).toBe(nsNames.length)

    // Every English bundle exposes the same top-level keys as its Spanish
    // sibling, so no namespace can silently ship a partial file.
    for (const row of NAMESPACE_TABLE) {
      const enBundle = await row.en()
      expect(Object.keys(enBundle.default).sort()).toEqual(
        Object.keys(row.es).sort(),
      )
    }
  })

  it('ensureLocale is idempotent for the English locale', async () => {
    const first = ensureLocale('en')
    const second = ensureLocale('en')
    // Same in-flight promise is reused; no duplicate bundle loading.
    expect(first).toBe(second)
    await Promise.all([first, second])
    expect(i18n.t('notifications.title')).toBe('Notifications')
  })

  it('ensureLocale no-ops for non-English locales', async () => {
    await expect(ensureLocale('es')).resolves.toBeUndefined()
    await expect(ensureLocale('fr-FR')).resolves.toBeUndefined()
  })

  it('switches language via LanguageSwitcher', async () => {
    localStorage.setItem('aac_assistant_locale', 'es')
    i18n.changeLanguage('es')
    await useLocaleStore.getState().setLocale('es-ES')
    const { getByLabelText } = render(
      <I18nextProvider i18n={i18n}>
        <LanguageSwitcher />
      </I18nextProvider>
    )
    const select = getByLabelText('Idioma') as HTMLSelectElement
    expect(select.value).toBe('es-ES')
  })
})
