import { create } from 'zustand'
import i18n from '../i18n/index'

type LocaleState = {
  locale: string
  setLocale: (lng: string) => void
  initFromDetected: () => void
}

export const useLocaleStore = create<LocaleState>((set) => ({
  locale: i18n.language || 'es',
  setLocale: (lng: string) => {
    i18n.changeLanguage(lng)
    localStorage.setItem('aac_assistant_locale', lng)
    set({ locale: lng })
  },
  initFromDetected: () => {
    const lng = i18n.language || localStorage.getItem('aac_assistant_locale') || 'es'
    i18n.changeLanguage(lng)
    set({ locale: lng })
  },
}))
