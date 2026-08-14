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

const ES_NAMESPACES = [
  'common',
  'dashboard',
  'learning',
  'achievements',
  'boards',
  'login',
  'register',
  'settings',
  'students',
  'symbols',
  'sidebar',
  'layout',
  'error',
  'games',
  'teachers',
  'admins',
  'setup',
]

const resources = {
  es: {
    common: esCommon,
    dashboard: esDashboard,
    learning: esLearning,
    achievements: esAchievements,
    boards: esBoards,
    login: esLogin,
    register: esRegister,
    settings: esSettings,
    students: esStudents,
    symbols: esSymbols,
    sidebar: esSidebar,
    layout: esLayout,
    error: esError,
    games: esGames,
    teachers: esTeachers,
    admins: esAdmins,
    setup: esSetup,
  },
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

// Pair each namespace with its static dynamic import so the namespace-to-file
// mapping stays adjacent (a reorder can't silently miswire a bundle).
const EN_BUNDLES: ReadonlyArray<
  readonly [string, () => Promise<{ default: Record<string, unknown> }>]
> = [
  ['common', () => import('../locales/en/common.json')],
  ['dashboard', () => import('../locales/en/pages/dashboard.json')],
  ['learning', () => import('../locales/en/pages/learning.json')],
  ['achievements', () => import('../locales/en/pages/achievements.json')],
  ['boards', () => import('../locales/en/pages/boards.json')],
  ['login', () => import('../locales/en/pages/login.json')],
  ['register', () => import('../locales/en/pages/register.json')],
  ['settings', () => import('../locales/en/pages/settings.json')],
  ['students', () => import('../locales/en/pages/students.json')],
  ['symbols', () => import('../locales/en/pages/symbols.json')],
  ['sidebar', () => import('../locales/en/pages/sidebar.json')],
  ['layout', () => import('../locales/en/pages/layout.json')],
  ['error', () => import('../locales/en/pages/error.json')],
  ['games', () => import('../locales/en/pages/games.json')],
  ['teachers', () => import('../locales/en/pages/teachers.json')],
  ['admins', () => import('../locales/en/pages/admins.json')],
  ['setup', () => import('../locales/en/pages/setup.json')],
]

let enLoaded: Promise<void> | null = null

export function ensureLocale(lng: string): Promise<void> {
  const code = (lng || '').toLowerCase().split('-')[0]
  if (code !== 'en') return Promise.resolve()

  if (!enLoaded) {
    enLoaded = (async () => {
      const loaded = await Promise.all(EN_BUNDLES.map(([, load]) => load()))
      EN_BUNDLES.forEach(([ns], i) => {
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
