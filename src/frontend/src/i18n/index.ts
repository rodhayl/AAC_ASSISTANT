import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'

// The default locale (and fallback) is bundled eagerly: it is needed on every
// startup. The secondary locale (English) is loaded on demand via
// `ensureLocale()` below, so its translations never ship in the entry chunk.
import esCommon from '../locales/es/common.json'
import esDashboard from '../locales/es/pages/dashboard.json'
import esLearning from '../locales/es/pages/learning.json'
import esAchievements from '../locales/es/pages/achievements.json'
import esBoards from '../locales/es/pages/boards.json'
import esLogin from '../locales/es/pages/login.json'
import esRegister from '../locales/es/pages/register.json'
import esSettings from '../locales/es/pages/settings.json'
import esStudents from '../locales/es/pages/students.json'
import esSymbols from '../locales/es/pages/symbols.json'
import esSidebar from '../locales/es/pages/sidebar.json'
import esLayout from '../locales/es/pages/layout.json'
import esError from '../locales/es/pages/error.json'
import esGames from '../locales/es/pages/games.json'
import esTeachers from '../locales/es/pages/teachers.json'
import esAdmins from '../locales/es/pages/admins.json'
import esSetup from '../locales/es/pages/setup.json'

// One table per namespace: its name, the eagerly-imported Spanish bundle, and
// the lazily-imported English bundle. Everything below is derived from this
// table (the i18n ns list, the ``resources`` map, the English loader loop), so
// adding a namespace is a single-row edit and the es/en lists cannot drift
// apart. The static es imports stay put; only the mappings are derived.
export const NAMESPACE_TABLE: ReadonlyArray<{
  ns: string
  es: Record<string, unknown>
  en: () => Promise<{ default: Record<string, unknown> }>
}> = [
  { ns: 'common', es: esCommon, en: () => import('../locales/en/common.json') },
  { ns: 'dashboard', es: esDashboard, en: () => import('../locales/en/pages/dashboard.json') },
  { ns: 'learning', es: esLearning, en: () => import('../locales/en/pages/learning.json') },
  { ns: 'achievements', es: esAchievements, en: () => import('../locales/en/pages/achievements.json') },
  { ns: 'boards', es: esBoards, en: () => import('../locales/en/pages/boards.json') },
  { ns: 'login', es: esLogin, en: () => import('../locales/en/pages/login.json') },
  { ns: 'register', es: esRegister, en: () => import('../locales/en/pages/register.json') },
  { ns: 'settings', es: esSettings, en: () => import('../locales/en/pages/settings.json') },
  { ns: 'students', es: esStudents, en: () => import('../locales/en/pages/students.json') },
  { ns: 'symbols', es: esSymbols, en: () => import('../locales/en/pages/symbols.json') },
  { ns: 'sidebar', es: esSidebar, en: () => import('../locales/en/pages/sidebar.json') },
  { ns: 'layout', es: esLayout, en: () => import('../locales/en/pages/layout.json') },
  { ns: 'error', es: esError, en: () => import('../locales/en/pages/error.json') },
  { ns: 'games', es: esGames, en: () => import('../locales/en/pages/games.json') },
  { ns: 'teachers', es: esTeachers, en: () => import('../locales/en/pages/teachers.json') },
  { ns: 'admins', es: esAdmins, en: () => import('../locales/en/pages/admins.json') },
  { ns: 'setup', es: esSetup, en: () => import('../locales/en/pages/setup.json') },
]

const ES_NAMESPACES = NAMESPACE_TABLE.map(({ ns }) => ns)

const resources = {
  es: Object.fromEntries(
    NAMESPACE_TABLE.map(({ ns, es }) => [ns, es]),
  ),
}

export const DEFAULT_LOCALE = 'es'

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources,
    fallbackLng: 'es',
    supportedLngs: ['es', 'es-ES', 'en', 'en-US'],
    load: 'languageOnly',
    ns: ES_NAMESPACES,
    defaultNS: 'common',
    detection: {
      order: ['localStorage'],
      caches: ['localStorage'],
      lookupLocalStorage: 'aac_assistant_locale',
    },
    interpolation: {
      escapeValue: false,
    },
    returnEmptyString: false,
  })

// ---------------------------------------------------------------------------
// Lazy secondary locale (English).
//
// The English namespaces are code-split into chunks fetched once, on first
// use (startup when English is detected, or when the user switches to
// English). `ensureLocale()` is idempotent: subsequent calls reuse the same
// in-flight promise, and a failed load resets so the next call retries.
//
// The `languageChanged` listener below is the single choke point: any path
// that activates English -- the LanguageDetector during init, `setLocale`,
// `main.tsx`, or a direct `i18n.changeLanguage('en')` -- triggers the same
// loader, so a missing `await` can never silently strand the UI in Spanish.
// ---------------------------------------------------------------------------

let enLoaded: Promise<void> | null = null

export function ensureLocale(lng: string): Promise<void> {
  const code = (lng || '').toLowerCase().split('-')[0]
  if (code !== 'en') return Promise.resolve()

  if (!enLoaded) {
    enLoaded = (async () => {
      const loaded = await Promise.all(NAMESPACE_TABLE.map(({ en }) => en()))
      NAMESPACE_TABLE.forEach(({ ns }, i) => {
        i18n.addResourceBundle('en', ns, loaded[i].default, true, true)
      })
      // addResourceBundle emits no event react-i18next subscribes to, so if
      // English is already the active language (e.g. the detector picked it
      // during init), force a re-render with the now-available translations.
      if ((i18n.language || '').toLowerCase().startsWith('en')) {
        await i18n.changeLanguage(i18n.language)
      }
    })().catch((err: unknown) => {
      enLoaded = null // allow a retry after a transient failure
      throw err
    })
  }

  return enLoaded
}

const rtlLangs = ['ar', 'he', 'fa', 'ur']
i18n.on('languageChanged', (lng) => {
  const code = (lng || '').toLowerCase().split('-')[0]
  if (code === 'en') {
    // Safety net for any un-awaited English activation (detector at init,
    // direct changeLanguage calls, tests, future call sites).
    ensureLocale('en').catch((err: unknown) => {
      console.warn('[i18n] failed to load English translations:', err)
    })
  }
  try {
    const dir = rtlLangs.includes(code) ? 'rtl' : 'ltr'
    if (typeof document !== 'undefined') {
      document.documentElement.setAttribute('dir', dir)
    }
  } catch { /* ignore */ }
})

export default i18n
