import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'

import esCommon from '../locales/es/common.json'
import enCommon from '../locales/en/common.json'
import esDashboard from '../locales/es/pages/dashboard.json'
import enDashboard from '../locales/en/pages/dashboard.json'
import esLearning from '../locales/es/pages/learning.json'
import enLearning from '../locales/en/pages/learning.json'
import esAchievements from '../locales/es/pages/achievements.json'
import enAchievements from '../locales/en/pages/achievements.json'
import esBoards from '../locales/es/pages/boards.json'
import enBoards from '../locales/en/pages/boards.json'
import esLogin from '../locales/es/pages/login.json'
import enLogin from '../locales/en/pages/login.json'
import esRegister from '../locales/es/pages/register.json'
import enRegister from '../locales/en/pages/register.json'
import esSettings from '../locales/es/pages/settings.json'
import enSettings from '../locales/en/pages/settings.json'
import esStudents from '../locales/es/pages/students.json'
import enStudents from '../locales/en/pages/students.json'
import esSymbols from '../locales/es/pages/symbols.json'
import enSymbols from '../locales/en/pages/symbols.json'
import esSidebar from '../locales/es/pages/sidebar.json'
import enSidebar from '../locales/en/pages/sidebar.json'
import esLayout from '../locales/es/pages/layout.json'
import enLayout from '../locales/en/pages/layout.json'
import esError from '../locales/es/pages/error.json'
import enError from '../locales/en/pages/error.json'
import esGames from '../locales/es/pages/games.json'
import enGames from '../locales/en/pages/games.json'
import esTeachers from '../locales/es/pages/teachers.json'
import enTeachers from '../locales/en/pages/teachers.json'
import esAdmins from '../locales/es/pages/admins.json'
import enAdmins from '../locales/en/pages/admins.json'

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
  },
  en: {
    common: enCommon,
    dashboard: enDashboard,
    learning: enLearning,
    achievements: enAchievements,
    boards: enBoards,
    login: enLogin,
    register: enRegister,
    settings: enSettings,
    students: enStudents,
    symbols: enSymbols,
    sidebar: enSidebar,
    layout: enLayout,
    error: enError,
    games: enGames,
    teachers: enTeachers,
    admins: enAdmins,
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
    ns: ['common', 'dashboard', 'learning', 'achievements', 'boards', 'login', 'register', 'settings', 'students', 'symbols', 'sidebar', 'layout', 'error', 'games', 'teachers', 'admins'],
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

const rtlLangs = ['ar', 'he', 'fa', 'ur']
i18n.on('languageChanged', (lng) => {
  try {
    const code = (lng || '').split('-')[0]
    const dir = rtlLangs.includes(code) ? 'rtl' : 'ltr'
    if (typeof document !== 'undefined') {
      document.documentElement.setAttribute('dir', dir)
    }
  } catch { /* ignore */ }
})

export default i18n
