import { create } from 'zustand'
import i18n, { ensureLocale } from '../i18n/index'

type LocaleState = {
  locale: string
  setLocale: (lng: string) => Promise<void>
}

export const useLocaleStore = create<LocaleState>((set) => ({
  locale: i18n.language || 'es',
  setLocale: async (lng: string) => {
    await ensureLocale(lng)
    await i18n.changeLanguage(lng)
    localStorage.setItem('aac_assistant_locale', lng)
    set({ locale: lng })
  },
}))
